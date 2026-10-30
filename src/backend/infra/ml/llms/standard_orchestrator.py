"""LLM orchestrator: run a request on the profile's primary model, falling back to its fallback models.

Each failure is logged here once (provider, target, error); adapters let errors propagate. When every
target fails, RuntimeError is raised with the last error as its cause.
"""
from collections.abc import Mapping

import structlog
from pydantic import BaseModel

from backend.domain.ports.providers.llm import LLM
from backend.domain.settings.profiles import LLMProfile

logger = structlog.get_logger()


class StandardLLMOrchestrator:

    def __init__(
            self,
            llm_providers: Mapping[str, LLM],
    ):
        self.llm_providers = llm_providers

    def _targets(self, profile: LLMProfile):
        """(target settings, adapter) in fallback order; targets without a configured adapter are skipped."""
        for target in [profile.primary, *(profile.fallback or [])]:
            llm = self.llm_providers.get(target.name)
            if llm is None:
                logger.warning("llm_provider_missing", target=target.name)
                continue
            yield target, llm

    async def generate_stream(
            self,
            prompt: str,
            profile: LLMProfile,
    ):
        last_error = None

        for target, llm in self._targets(profile):
            started = False
            try:
                async for chunk in llm.generate_stream(prompt):
                    started = True
                    yield chunk

                return
            except Exception as e:
                logger.warning(
                    "llm_stream_failed",
                    provider=target.provider,
                    target=target.name,
                    after_partial_output=started,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                # Text already reached the student: a fallback would start a second answer after the
                # partial first one. Fail the stream instead; the API reports it as a stream error.
                if started:
                    raise

                last_error = e

        raise RuntimeError("All LLM targets failed") from last_error

    async def generate(
            self,
            prompt: str,
            profile: LLMProfile,
    ):
        last_error = None

        for target, llm in self._targets(profile):
            try:
                return await llm.generate(prompt)
            except Exception as e:
                logger.warning(
                    "llm_generate_failed",
                    provider=target.provider,
                    target=target.name,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                last_error = e

        raise RuntimeError("All LLM targets failed") from last_error

    async def generate_structured[T: BaseModel = BaseModel](
            self,
            prompt: str,
            profile: LLMProfile,
            response_model: type[T] = BaseModel,
    ) -> T:
        last_error = None

        for target, llm in self._targets(profile):
            try:
                return await llm.generate_structured(
                    prompt=prompt,
                    response_model=response_model,
                )

            except Exception as exc:
                logger.warning(
                    "llm_structured_failed",
                    provider=target.provider,
                    target=target.name,
                    schema=response_model.__name__,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                last_error = exc

        raise RuntimeError(
            "All structured LLM targets failed"
        ) from last_error
