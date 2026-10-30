"""LLM fallback never duplicates a partially streamed answer; embeddings are normalized per vector."""
from types import SimpleNamespace

import numpy as np
import pytest

from backend.infra.ml.embeddings.gemini import normalize_rows
from backend.infra.ml.llms.standard_orchestrator import StandardLLMOrchestrator


class StreamingLLM:
    def __init__(self, chunks, fail_after=None):
        self.chunks, self.fail_after, self.calls = chunks, fail_after, 0

    async def generate_stream(self, prompt):
        self.calls += 1
        for index, chunk in enumerate(self.chunks):
            if index == self.fail_after:
                raise ConnectionError("stream dropped")
            yield chunk


def target(name):
    return SimpleNamespace(name=name, provider="test")


PROFILE = SimpleNamespace(primary=target("primary"), fallback=[target("backup")])


async def collect(orchestrator):
    return [chunk async for chunk in orchestrator.generate_stream("q", PROFILE)]


async def test_failure_before_any_text_falls_back():
    backup = StreamingLLM(["fine"])
    orchestrator = StandardLLMOrchestrator({"primary": StreamingLLM(["x"], fail_after=0), "backup": backup})

    assert await collect(orchestrator) == ["fine"]


async def test_failure_after_partial_text_does_not_start_a_second_answer():
    backup = StreamingLLM(["second answer"])
    orchestrator = StandardLLMOrchestrator({"primary": StreamingLLM(["Hello ", "wor"], fail_after=1), "backup": backup})
    received = []

    with pytest.raises(ConnectionError):
        async for chunk in orchestrator.generate_stream("q", PROFILE):
            received.append(chunk)

    assert received == ["Hello "]
    assert backup.calls == 0


def test_each_vector_is_normalized_on_its_own():
    rows = normalize_rows([[3.0, 4.0], [0.0, 10.0], [0.0, 0.0]])

    assert np.allclose(np.linalg.norm(rows[:2], axis=1), 1.0)
    assert rows[2] == [0.0, 0.0]  # A zero vector stays zero instead of dividing by zero.
