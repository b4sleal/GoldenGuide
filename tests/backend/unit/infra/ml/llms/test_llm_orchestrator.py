"""Fallback is shared policy: providers must never concatenate two different answers."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from backend.domain.ports.providers.llm import LLM
from backend.domain.settings.llm import OpenAILLMSettings
from backend.domain.settings.profiles import LLMProfile
from backend.infra.ml.llms.standard_orchestrator import StandardLLMOrchestrator


class Answer(BaseModel):
    course: str


def profile(*names: str) -> LLMProfile:
    targets = [
        OpenAILLMSettings(
            name=name,
            provider="openai",
            model_name="test",
            api_key="unused",
        )
        for name in names
    ]
    return LLMProfile(primary=targets[0], fallback=targets[1:])


async def request(service, operation, settings):
    if operation == "generate_structured":
        return await service.generate_structured("question", settings, Answer)
    return await service.generate("question", settings)


@pytest.mark.parametrize("operation", ["generate", "generate_structured"])
async def test_success_does_not_contact_fallback(operation):
    primary, backup = AsyncMock(spec=LLM), AsyncMock(spec=LLM)
    expected = Answer(course="CP104") if operation == "generate_structured" else "CP104"
    getattr(primary, operation).return_value = expected
    service = StandardLLMOrchestrator({"primary": primary, "backup": backup})

    assert await request(service, operation, profile("primary", "backup")) == expected
    if operation == "generate_structured":
        primary.generate_structured.assert_awaited_once_with(
            prompt="question", response_model=Answer
        )
    else:
        primary.generate.assert_awaited_once_with("question")
    getattr(backup, operation).assert_not_awaited()


@pytest.mark.parametrize("operation", ["generate", "generate_structured"])
async def test_fallback_order_skips_missing_targets_and_stops_at_success(operation):
    calls = []
    providers = {
        name: AsyncMock(spec=LLM) for name in ("first", "second", "last", "unused")
    }

    for name, provider in providers.items():

        async def respond(*args, target=name, **kwargs):
            calls.append(target)
            if target != "last":
                raise ConnectionError(target)
            return (
                Answer(course="CP104")
                if operation == "generate_structured"
                else "CP104"
            )

        getattr(provider, operation).side_effect = respond

    result = await request(
        StandardLLMOrchestrator(providers),
        operation,
        profile("missing", "first", "second", "last", "unused"),
    )

    assert result == (
        Answer(course="CP104") if operation == "generate_structured" else "CP104"
    )
    assert calls == ["first", "second", "last"]


@pytest.mark.parametrize("operation", ["generate", "generate_structured"])
async def test_exhausted_fallback_preserves_the_last_failure(operation):
    first, last = AsyncMock(spec=LLM), AsyncMock(spec=LLM)
    failure = TimeoutError("last target timed out")
    getattr(first, operation).side_effect = ConnectionError("first target unavailable")
    getattr(last, operation).side_effect = failure

    with pytest.raises(RuntimeError, match="All .*targets failed") as caught:
        await request(
            StandardLLMOrchestrator({"first": first, "last": last}),
            operation,
            profile("first", "last"),
        )

    assert caught.value.__cause__ is failure


@pytest.mark.parametrize("operation", ["generate", "generate_structured"])
async def test_no_configured_targets_fails_clearly(operation):
    with pytest.raises(RuntimeError, match="targets failed"):
        await request(StandardLLMOrchestrator({}), operation, profile("missing"))


@pytest.mark.parametrize("operation", ["generate", "generate_structured"])
async def test_cancellation_does_not_start_fallback(operation):
    primary, backup = AsyncMock(spec=LLM), AsyncMock(spec=LLM)
    getattr(primary, operation).side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await request(
            StandardLLMOrchestrator({"primary": primary, "backup": backup}),
            operation,
            profile("primary", "backup"),
        )
    getattr(backup, operation).assert_not_awaited()


class StreamProvider:
    """A port fake that can fail before or after delivering text, without an SDK."""

    def __init__(self, chunks=(), failure=None):
        self.chunks, self.failure, self.prompts = chunks, failure, []

    async def generate_stream(self, prompt):
        self.prompts.append(prompt)
        for chunk in self.chunks:
            yield chunk
        if self.failure is not None:
            raise self.failure


async def test_stream_preserves_chunk_order_without_starting_fallback():
    primary = StreamProvider(["first ", "second", "\n"])
    backup = StreamProvider(["different answer"])
    service = StandardLLMOrchestrator({"primary": primary, "backup": backup})

    assert [
        chunk
        async for chunk in service.generate_stream(
            "question",
            profile("primary", "backup"),
        )
    ] == ["first ", "second", "\n"]
    assert primary.prompts == ["question"]
    assert backup.prompts == []


async def test_all_stream_targets_failing_preserves_last_cause():
    failure = TimeoutError("backup unavailable")
    service = StandardLLMOrchestrator(
        {
            "primary": StreamProvider(failure=ConnectionError("primary unavailable")),
            "backup": StreamProvider(failure=failure),
        }
    )

    with pytest.raises(RuntimeError) as caught:
        _ = [
            chunk
            async for chunk in service.generate_stream(
                "q", profile("primary", "backup")
            )
        ]
    assert caught.value.__cause__ is failure


async def test_stream_cancellation_does_not_start_fallback():
    backup = StreamProvider(["backup"])
    service = StandardLLMOrchestrator(
        {
            "primary": StreamProvider(failure=asyncio.CancelledError()),
            "backup": backup,
        }
    )

    with pytest.raises(asyncio.CancelledError):
        _ = [
            chunk
            async for chunk in service.generate_stream(
                "q", profile("primary", "backup")
            )
        ]
    assert backup.prompts == []
