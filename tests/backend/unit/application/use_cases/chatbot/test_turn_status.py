"""Progress streams before the answer: understanding, each searched source once, then writing."""
import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest

from backend.application.use_cases.chatbot.rag_chatbot import RagChatbot
from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.domain.entities.conversations import ConversationMemory
from backend.domain.entities.retrieval_plan import RetrievalSource
from backend.domain.entities.turn_status import TurnStage, TurnStatus
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.settings.ai_behavior import ResolvedRAGContext


def searching(source):
    return TurnStatus(stage=TurnStage.SEARCHING, source=source)


class Retrieval:
    """Reports progress as the real orchestrator does, with a pause between stages, or fails."""

    def __init__(self, failure=None):
        self.failure = failure

    async def resolve_context(self, question, recorder, earlier, top_k):
        for source in (RetrievalSource.COURSES, RetrievalSource.COURSE_TERMS, RetrievalSource.COURSES):
            recorder.report(searching(source))
            await asyncio.sleep(0)
        if self.failure:
            raise self.failure
        return ResolvedRAGContext.model_construct(
            context_text="records", sources=[], links={}, llm_profile=None, profile_name="t", tables=[],
        )


class Settings:
    async def get(self):
        return SimpleNamespace(version=25, generation_llm=SimpleNamespace(system="rules", turn="{context_text}\n{question}"))


class LLM:
    async def generate_stream(self, request, profile):
        yield "CP264 is offered."


def chatbot(retrieval) -> RagChatbot:
    return RagChatbot(
        context_resolver=retrieval, llm_strategy=LLM(), settings_service=Settings(),
        term_resolver=AcademicTermResolver(clock=lambda: date(2026, 11, 1)),
    )


async def events(bot):
    return [json.loads(line) async for line in bot.ask("Is CP264 offered?", TurnRecorder(), ConversationMemory())]


async def test_statuses_stream_in_order_before_the_answer_text():
    streamed = await events(chatbot(Retrieval()))

    statuses = [event for event in streamed if event["type"] == "status"]
    assert statuses == [
        {"type": "status", "stage": "understanding"},
        {"type": "status", "stage": "searching", "source": "courses"},       # Reported twice, shown once.
        {"type": "status", "stage": "searching", "source": "course_terms"},
        {"type": "status", "stage": "writing"},
    ]
    first_text = next(index for index, event in enumerate(streamed) if event["type"] == "text")
    assert all(event["type"] == "status" for event in streamed[:first_text])


async def test_retrieval_failure_still_raises_after_its_progress():
    stream = chatbot(Retrieval(failure=ConnectionError("database down"))).ask(
        "Is CP264 offered?", TurnRecorder(), ConversationMemory(),
    )
    seen = []

    with pytest.raises(ConnectionError):
        async for line in stream:
            seen.append(json.loads(line))

    assert {"type": "status", "stage": "understanding"} in seen
    assert not any(event["type"] == "text" for event in seen)
