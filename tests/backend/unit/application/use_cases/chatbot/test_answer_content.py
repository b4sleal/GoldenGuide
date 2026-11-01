"""Stored display content retains stream order and partial answers without saving token-sized blocks."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.domain.entities.answer_content import StoredAnswerContent
from backend.domain.entities.conversations import (
    ChatMessageRead,
    ChatTurnContext,
    MessageStatus,
)

CONTEXT = ChatTurnContext(client_id_hash="device")
TABLE = {"type": "table", "title": "CP264 sections", "columns": ["Section", "Meetings"],
         "rows": [["A", "Monday\nWednesday"], ["B", "Friday"]]}


@pytest.mark.parametrize("status", list(MessageStatus))
def test_display_blocks_survive_every_terminal_status_and_keep_memory_text(status):
    recorder = TurnRecorder()
    recorder.record_answer_event({"type": "status", "stage": "writing"})
    recorder.record_answer_event({"type": "text", "text": "CP264 "})
    recorder.record_answer_event({"type": "text", "text": "sections"})
    citation = {"type": "citation", "source_nums": [1], "urls": ["https://loris.wlu.ca"]}
    recorder.record_answer_event(citation)
    recorder.record_answer_event(TABLE)
    recorder.record_answer_event({"type": "text", "text": "Partial tail"})
    error = TimeoutError("internal detail") if status is MessageStatus.ERROR else None

    saved = recorder.answer_message(uuid4(), CONTEXT, status, error)

    assert saved.content == "CP264 sectionsPartial tail"  # Existing follow-up memory representation.
    assert saved.status is status
    assert saved.answer_content.model_dump() == {"version": 1, "blocks": [
        {"type": "text", "text": "CP264 sections"}, citation, TABLE,
        {"type": "text", "text": "Partial tail"},
    ]}
    # Serialization uses the same domain shape a repository reads back from JSONB.
    assert StoredAnswerContent.model_validate_json(saved.answer_content.model_dump_json()) == saved.answer_content


def test_a_snapshot_does_not_change_if_the_recorder_receives_more_events():
    recorder = TurnRecorder()
    recorder.record_answer_event(TABLE)
    saved = recorder.answer_message(uuid4(), CONTEXT, MessageStatus.INTERRUPTED)
    recorder.record_answer_event({"type": "text", "text": "later"})
    recorder.answer_message(uuid4(), CONTEXT, MessageStatus.COMPLETE)
    assert len(saved.answer_content.blocks) == 1


def test_transient_and_terminal_events_are_not_saved_as_display_content():
    recorder = TurnRecorder()
    for event in [
        {"type": "status", "stage": "writing"}, {"type": "ok"},
        {"type": "error", "error": {"message": "private detail"}},
    ]:
        recorder.record_answer_event(event)
    saved = recorder.answer_message(uuid4(), CONTEXT, MessageStatus.INTERRUPTED)
    assert saved.answer_content is None


def test_unknown_block_types_and_misaligned_citation_urls_are_rejected():
    with pytest.raises(ValidationError):
        StoredAnswerContent.model_validate({"blocks": [{"type": "error", "detail": "internal"}]})
    with pytest.raises(ValidationError, match="corresponding URL"):
        StoredAnswerContent.model_validate({"blocks": [{"type": "citation", "source_nums": [1, 2], "urls": [None]}]})


def test_legacy_database_messages_default_to_text_only():
    saved = ChatMessageRead(
        id=1, position=1, conversation_id=uuid4(), role="assistant", content="Old answer", created_at=datetime.now(UTC),
    )
    assert saved.answer_content is None
