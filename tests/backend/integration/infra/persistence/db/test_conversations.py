"""Real PostgreSQL: message order under concurrency, cascading deletes, owner scoping, retention, feedback."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.application.use_cases.chatbot.conversation_history import (
    ConversationHistory,
)
from backend.domain.entities.answer_content import (
    AnswerCitationBlock,
    AnswerTableBlock,
    AnswerTextBlock,
    StoredAnswerContent,
)
from backend.domain.entities.conversations import (
    ChatMessageCreate,
    ConversationCreate,
    FeedbackRating,
    FeedbackReason,
    MessageFeedbackCreate,
    MessageStatus,
)
from backend.domain.entities.llm import MessageRole
from backend.domain.errors import InvalidInputError, NotFoundError
from backend.domain.ports.repositories.app.query_types import (
    ChatMessagePageParams,
    ConversationPageParams,
)
from backend.domain.ports.repositories.filters import (
    ChatMessageFilter,
    ConversationFilter,
)
from backend.infra.persistence.db.app.app_tables import AppBaseTable, ConversationTable
from backend.infra.persistence.db.app.base.conversation_repo import (
    SqlConversationRepository,
)
from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps
from tests.backend.unit.application.services.router.factories import INSTITUTION


@pytest.fixture
async def db(test_database_url):
    # A unique schema prevents interference with any other tests in the disposable DB.
    schema = f"conversations_{uuid4().hex}"
    engine = create_async_engine(
        test_database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.run_sync(AppBaseTable.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def start():
        async with sessions.begin() as session:
            yield SimpleNamespace(
                conversations=SqlConversationRepository(session, PostgresDialectOps()), session=session
            )

    try:
        yield SimpleNamespace(start=start)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


def question(conversation_id, content="Is CP264 offered in winter?"):
    return ChatMessageCreate(conversation_id=conversation_id, role=MessageRole.USER, content=content)


async def new_conversation(db, **fields):
    async with db.start() as repos:
        return await repos.conversations.create_conversation(ConversationCreate(**fields))


async def messages_of(db, conversation_id):
    async with db.start() as repos:
        return await repos.conversations.fetch_messages(
            ChatMessagePageParams(), ChatMessageFilter(conversation_id=conversation_id)
        )


async def test_concurrent_appends_get_distinct_consecutive_positions(db):
    conversation_id = await new_conversation(db, client_id_hash="device")

    async def append(index):
        async with db.start() as repos:
            return await repos.conversations.append_message(question(conversation_id, f"question {index}"))

    await asyncio.gather(*(append(index) for index in range(10)))

    assert [message.position for message in await messages_of(db, conversation_id)] == list(range(1, 11))


async def test_assistant_diagnostics_and_generation_error_round_trip(db):
    conversation_id = await new_conversation(db)
    answer = ChatMessageCreate(
        conversation_id=conversation_id, role=MessageRole.ASSISTANT, content="CP264 is offered",
        status=MessageStatus.ERROR,
        query_plan={"requests": [{"source": "course_terms", "operation": "lookup"}]},
        retrieval_outcomes=[{"status": "completed", "count": 2}],
        sources=[{"title": "CP264", "url": "https://academic-calendar.wlu.ca/course.php?c=1"}],
        profile_name="default", settings_version=16, timings={"retrieval_ms": 420, "first_chunk_ms": None},
        trace_id="a" * 32, request_id="req-1",
        error_type="TimeoutError", error_code="dependency_unavailable", error_message="LLM stream timed out",
    )

    async with db.start() as repos:
        stored = await repos.conversations.append_message(answer)

    [fetched] = await messages_of(db, conversation_id)
    assert fetched == stored
    assert fetched.model_dump(exclude={"id", "position", "created_at"}) == answer.model_dump()


async def test_saved_answer_content_round_trips_through_database_and_owned_public_history(db):
    conversation_id = await new_conversation(db, client_id_hash="device")
    content = StoredAnswerContent(blocks=[
        AnswerTextBlock(text="CP264 sections"),
        AnswerCitationBlock(source_nums=[1], urls=["https://loris.wlu.ca"]),
        AnswerTableBlock(title="Sections", columns=["Section", "Meetings"], rows=[["A", "Monday\nWednesday"]]),
    ])
    async with db.start() as repos:
        await repos.conversations.append_message(ChatMessageCreate(
            conversation_id=conversation_id, role=MessageRole.ASSISTANT, content="CP264 sections",
            answer_content=content, sources=[{"title": "LORIS", "url": "https://loris.wlu.ca"}],
            query_plan={"private": "diagnostic"},
        ))

    [stored] = await messages_of(db, conversation_id)
    assert stored.answer_content == content
    [public] = await ConversationHistory(db, INSTITUTION).messages("device", conversation_id, 200, 0)
    assert public.answer_content == content
    assert public.sources[0].title == "LORIS"
    assert "query_plan" not in public.model_dump()
    with pytest.raises(NotFoundError):
        await ConversationHistory(db, INSTITUTION).messages("other-device", conversation_id, 200, 0)


async def test_append_to_unknown_conversation_is_not_found(db):
    async with db.start() as repos:
        with pytest.raises(NotFoundError):
            await repos.conversations.append_message(question(uuid4()))


async def test_legacy_registration_sources_are_compact_in_history_without_rewriting_the_database(db):
    conversation_id = await new_conversation(db, client_id_hash="device")
    url = str(INSTITUTION.registration_url)
    calendar = "https://academic-calendar.wlu.ca/cp264"
    snapshot = StoredAnswerContent(blocks=[AnswerCitationBlock(source_nums=[2, 3], urls=[url, calendar])])
    async with db.start() as repos:
        await repos.conversations.append_message(ChatMessageCreate(
            conversation_id=conversation_id, role=MessageRole.ASSISTANT, content="CP264 sections",
            answer_content=snapshot, sources=[
                {"title": "Section A", "url": url, "source_type": "course_terms"},
                {"title": "Section B", "url": url, "source_type": "course_terms"},
                {"title": "CP264", "url": calendar, "source_type": "courses"},
            ],
        ))

    [public] = await ConversationHistory(db, INSTITUTION).messages("device", conversation_id, 200, 0)
    assert [source.title for source in public.sources] == ["LORIS - Registration", "CP264"]
    assert public.answer_content.blocks[0].source_nums == [1, 2]
    assert public.answer_content.blocks[0].urls == [url, calendar]
    [stored] = await messages_of(db, conversation_id)
    assert len(stored.sources) == 3
    assert stored.answer_content == snapshot


async def test_appending_marks_the_conversation_recently_active(db):
    conversation_id = await new_conversation(db)
    async with db.start() as repos:
        await repos.session.execute(
            update(ConversationTable).values(updated_at=datetime.now(UTC) - timedelta(days=30))
        )

    async with db.start() as repos:
        await repos.conversations.append_message(question(conversation_id))
        [conversation] = await repos.conversations.fetch_conversations(
            ConversationPageParams(), ConversationFilter(id=conversation_id)
        )

    assert conversation.updated_at > datetime.now(UTC) - timedelta(minutes=5)


async def test_owner_scoped_listing_and_delete_never_touch_other_owners(db):
    mine = await new_conversation(db, client_id_hash="my-device")
    theirs = await new_conversation(db, client_id_hash="their-device")
    for conversation_id in (mine, theirs):
        async with db.start() as repos:
            await repos.conversations.append_message(question(conversation_id))

    async with db.start() as repos:
        listed = await repos.conversations.fetch_conversations(
            ConversationPageParams(), ConversationFilter(client_id_hash="my-device")
        )
        # Someone else's conversation ID under my device: nothing is deleted.
        assert await repos.conversations.delete_conversations(
            ConversationFilter(id=theirs, client_id_hash="my-device")
        ) == 0
        assert await repos.conversations.delete_conversations(ConversationFilter(id=mine, client_id_hash="my-device")) == 1

    assert [conversation.id for conversation in listed] == [mine]
    assert await messages_of(db, mine) == []
    assert len(await messages_of(db, theirs)) == 1


async def test_delete_without_a_filter_is_refused(db):
    await new_conversation(db)
    async with db.start() as repos:
        with pytest.raises(InvalidInputError):
            await repos.conversations.delete_conversations(ConversationFilter())
        assert len(await repos.conversations.fetch_conversations(ConversationPageParams())) == 1


async def test_retention_deletes_only_inactive_conversations_with_their_messages_and_feedback(db):
    stale, active = await new_conversation(db), await new_conversation(db)
    async with db.start() as repos:
        stale_message = await repos.conversations.append_message(question(stale))
        await repos.conversations.upsert_feedback(
            MessageFeedbackCreate(message_id=stale_message.id, rating=FeedbackRating.UP)
        )
        await repos.conversations.append_message(question(active))
        await repos.session.execute(
            update(ConversationTable)
            .where(ConversationTable.id == stale)
            .values(updated_at=datetime.now(UTC) - timedelta(days=400))
        )

    async with db.start() as repos:
        deleted = await repos.conversations.delete_conversations(
            ConversationFilter(updated_before=datetime.now(UTC) - timedelta(days=365))
        )
        remaining = await repos.conversations.fetch_conversations(ConversationPageParams())
        feedback = await repos.conversations.fetch_feedback([stale_message.id])

    assert deleted == 1
    assert [conversation.id for conversation in remaining] == [active]
    assert await messages_of(db, stale) == []
    assert feedback == []


async def test_new_feedback_replaces_the_earlier_rating(db):
    conversation_id = await new_conversation(db)
    async with db.start() as repos:
        message = await repos.conversations.append_message(question(conversation_id))
        first_id = await repos.conversations.upsert_feedback(
            MessageFeedbackCreate(message_id=message.id, rating=FeedbackRating.UP)
        )
    async with db.start() as repos:
        second_id = await repos.conversations.upsert_feedback(MessageFeedbackCreate(
            message_id=message.id, rating=FeedbackRating.DOWN,
            reason=FeedbackReason.OUTDATED, comment="That's last year's schedule.",
        ))
        [feedback] = await repos.conversations.fetch_feedback([message.id])

    assert second_id == first_id
    assert (feedback.rating, feedback.reason, feedback.comment) == (
        FeedbackRating.DOWN, FeedbackReason.OUTDATED, "That's last year's schedule.",
    )
    assert feedback.updated_at >= feedback.created_at
