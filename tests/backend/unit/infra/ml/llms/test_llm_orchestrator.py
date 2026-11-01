"""Fallback is shared policy: providers must never concatenate two different answers."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from backend.domain.entities.llm import LLMRequest
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


QUESTION = LLMRequest.single_turn("question")


async def request(service, settings):
    return await service.generate_structured(QUESTION, settings, Answer)


async def test_success_does_not_contact_fallback():
    primary, backup = AsyncMock(spec=LLM), AsyncMock(spec=LLM)
    expected = Answer(course="CP104")
    primary.generate_structured.return_value = expected
    service = StandardLLMOrchestrator({"primary": primary, "backup": backup})

    assert await request(service, profile("primary", "backup")) == expected
    primary.generate_structured.assert_awaited_once_with(QUESTION, Answer)
    backup.generate_structured.assert_not_awaited()


async def test_fallback_order_skips_missing_targets_and_stops_at_success():
    calls = []
    providers = {
        name: AsyncMock(spec=LLM) for name in ("first", "second", "last", "unused")
    }

    for name, provider in providers.items():

        async def respond(*args, target=name, **kwargs):
            calls.append(target)
            if target != "last":
                raise ConnectionError(target)
            return Answer(course="CP104")

        provider.generate_structured.side_effect = respond

    result = await request(
        StandardLLMOrchestrator(providers),
        profile("missing", "first", "second", "last", "unused"),
    )

    assert result == Answer(course="CP104")
    assert calls == ["first", "second", "last"]


async def test_exhausted_fallback_preserves_the_last_failure():
    first, last = AsyncMock(spec=LLM), AsyncMock(spec=LLM)
    failure = TimeoutError("last target timed out")
    first.generate_structured.side_effect = ConnectionError("first target unavailable")
    last.generate_structured.side_effect = failure

    with pytest.raises(RuntimeError, match="All .*targets failed") as caught:
        await request(
            StandardLLMOrchestrator({"first": first, "last": last}),
                profile("first", "last"),
        )

    assert caught.value.__cause__ is failure


async def test_no_configured_targets_fails_clearly():
    with pytest.raises(RuntimeError, match="targets failed"):
        await request(StandardLLMOrchestrator({}), profile("missing"))


async def test_cancellation_does_not_start_fallback():
    primary, backup = AsyncMock(spec=LLM), AsyncMock(spec=LLM)
    primary.generate_structured.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await request(
            StandardLLMOrchestrator({"primary": primary, "backup": backup}),
                profile("primary", "backup"),
        )
    backup.generate_structured.assert_not_awaited()


class StreamProvider:
    """A port fake that can fail before or after delivering text, without an SDK."""

    def __init__(self, chunks=(), failure=None):
        self.chunks, self.failure, self.requests = chunks, failure, []

    async def generate_stream(self, request):
        self.requests.append(request)
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
        async for chunk in service.generate_stream(QUESTION,
            profile("primary", "backup"),
        )
    ] == ["first ", "second", "\n"]
    assert primary.requests == [QUESTION]
    assert backup.requests == []


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
            async for chunk in service.generate_stream(QUESTION, profile("primary", "backup")
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
            async for chunk in service.generate_stream(QUESTION, profile("primary", "backup")
            )
        ]
    assert backup.requests == []


async def test_failure_after_partial_text_does_not_start_a_second_answer():
    backup = StreamProvider(["second answer"])
    service = StandardLLMOrchestrator(
        {
            "primary": StreamProvider(["Hello "], failure=ConnectionError("stream dropped")),
            "backup": backup,
        }
    )
    received = []

    with pytest.raises(ConnectionError):
        async for chunk in service.generate_stream(QUESTION, profile("primary", "backup")):
            received.append(chunk)

    assert received == ["Hello "]
    assert backup.requests == []
