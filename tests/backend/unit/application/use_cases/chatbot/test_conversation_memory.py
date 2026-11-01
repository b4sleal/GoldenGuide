"""What a new question inherits: completed pairs (most recent, cut to length) and carried entities."""
from datetime import UTC, datetime
from uuid import uuid4

from backend.application.use_cases.chatbot.chat_turn import conversation_memory
from backend.domain.entities.conversations import ChatMessageRead, MessageStatus
from backend.domain.entities.llm import MessageRole
from backend.domain.entities.question import CourseEntity
from backend.domain.settings.chat import ConversationHistorySettings

CONVERSATION = uuid4()
CP264 = CourseEntity(raw="cp264", normalized="CP264")


def conversation(*turns):
    """(question, answer, answer status, carried entities) as stored messages, in order."""
    messages = []
    for question, answer, status, carried in turns:
        for role, content, message_status, entities in (
            (MessageRole.USER, question, MessageStatus.COMPLETE, None), (MessageRole.ASSISTANT, answer, status, carried),
        ):
            position = len(messages) + 1
            messages.append(ChatMessageRead(
                id=position, position=position, conversation_id=CONVERSATION, role=role, content=content,
                status=message_status, carried_entities=entities, created_at=datetime.now(UTC),
                error_type="Failure" if message_status is MessageStatus.ERROR else None,
            ))
    return messages


def turn(question, answer, status=MessageStatus.COMPLETE, carried=None):
    return question, answer, status, carried


def contents(memory):
    return [message.content for message in memory.earlier]


def settings(max_turns=3, max_chars=1500):
    return ConversationHistorySettings(max_turns=max_turns, max_chars_per_message=max_chars)


def test_failed_and_interrupted_turns_are_left_out_with_their_question():
    history = conversation(
        turn("q1", "a1"), turn("q2", "partial", MessageStatus.ERROR),
        turn("q3", "cut off", MessageStatus.INTERRUPTED), turn("q4", "a4"),
    )

    assert contents(conversation_memory(history, settings())) == ["q1", "a1", "q4", "a4"]


def test_only_the_most_recent_turns_are_kept_oldest_first():
    history = conversation(*[turn(f"q{n}", f"a{n}") for n in range(1, 6)])

    assert contents(conversation_memory(history, settings(max_turns=2))) == ["q4", "a4", "q5", "a5"]


def test_zero_turns_disables_history():
    assert conversation_memory(conversation(turn("q", "a")), settings(max_turns=0)).earlier == ()


def test_each_message_is_cut_to_the_configured_length():
    memory = conversation_memory(conversation(turn("question", "a long answer")), settings(max_chars=6))

    assert contents(memory) == ["questi", "a long"]


def test_a_question_without_an_answer_yet_is_left_out():
    assert conversation_memory(conversation(turn("q1", "a1"))[:1], settings()).earlier == ()


def test_entities_come_from_the_latest_completed_answer():
    stored = {"[COURSE1]": CP264.model_dump(mode="json")}
    history = conversation(turn("CP264 prereqs?", "CP164.", carried=stored), turn("q2", "partial", MessageStatus.ERROR))

    assert conversation_memory(history, settings()).carried_entities == {"[COURSE1]": CP264}


def test_unreadable_carried_entities_are_dropped_not_fatal():
    history = conversation(turn("q", "a", carried={"[COURSE1]": {"type": "no-longer-a-type"}}))

    memory = conversation_memory(history, settings())

    assert memory.carried_entities == {}
    assert contents(memory) == ["q", "a"]
