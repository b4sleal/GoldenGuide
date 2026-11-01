"""Tables come from records; the model only places them with {{TABLE:n}} markers."""
import json
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from backend.application.services.router.evidence.course_term_evidence import (
    meeting_days,
    meeting_time,
)
from backend.application.use_cases.chatbot.evidence_tables import (
    SECTION_HEADING,
    TableMarkerParser,
    build_tables,
    prompt_records,
    table_catalog_text,
)
from backend.application.use_cases.chatbot.rag_chatbot import RagChatbot
from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.domain.entities.conversations import (
    ChatTurnContext,
    ConversationMemory,
    MessageStatus,
)
from backend.domain.entities.retrieval import Evidence, EvidenceTable, TableRow
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.entities.wlu.loris_registration import (
    CourseMeetingTime,
)
from backend.domain.settings.ai_behavior import ResolvedRAGContext


def record(group: str, section: str, extra: dict | None = None, table_content: str | None = None) -> Evidence:
    return Evidence(
        source_id=f"course_term:{group}:{section}",
        title=section,
        content="...",
        table_row=TableRow(group=group, cells={"Section": section, **(extra or {})}),
        table_content=table_content,
    )


TABLE = EvidenceTable(table_id="1", title="CP220 sections — Winter 2027", columns=["Section"], rows=[["A"], ["B"]])
# Built from an automatic lookup: shown only where the model places it.
AUTOMATIC_TABLE = TABLE.model_copy(update={"append_if_unplaced": False})


# ---- building -----------------------------------------------------------------------------------

def test_groups_become_tables_in_order_and_singletons_are_skipped():
    tables = build_tables([
        record("CP220 — Winter", "A"),
        record("CP104 — Winter", "X"),            # only one row: no table
        record("CP220 — Winter", "B", {"Seats": "3"}),
    ], requested_ids=set())
    assert [t.title for t in tables] == ["CP220 — Winter"]
    # Column union: a row without "Seats" gets an empty cell instead of shifting columns.
    assert tables[0].columns == ["Section", "Seats"]
    assert tables[0].rows == [["A", ""], ["B", "3"]]


def test_a_table_is_appended_if_unplaced_only_when_a_planned_request_returned_its_records():
    a, b, x, y = record("CP220", "A"), record("CP220", "B"), record("CP104", "X"), record("CP104", "Y")
    requested, automatic = build_tables([a, b, x, y], requested_ids={a.source_id})
    assert requested.append_if_unplaced is True
    assert automatic.append_if_unplaced is False


def test_tabled_records_reach_the_prompt_as_their_table_content():
    tabled = [record("CP220", "A", table_content="Section: A | Open"), record("CP220", "B", table_content="Section: B")]
    lone = record("CP104", "X", table_content="Section: X")      # one row: no table, keeps its full text
    plain = record("CP220", "C")                                   # no table_content: keeps its full text
    tables = build_tables([*tabled, lone, plain], requested_ids=set())

    prompt = prompt_records([*tabled, lone, plain], tables)

    assert [item.content for item in prompt] == ["Section: A | Open", "Section: B", "...", "..."]


def test_catalog_lists_markers_and_is_empty_without_tables():
    assert table_catalog_text([]) == ""
    text = table_catalog_text([TABLE])
    assert SECTION_HEADING in text and "{{TABLE:1}}: CP220 sections — Winter 2027 (2 rows)" in text


def test_meeting_cells_are_readable():
    meeting = CourseMeetingTime(beginTime="1000", endTime="1120", monday=True, wednesday=True)
    assert meeting_days(meeting) == "Mon/Wed"
    assert meeting_time(meeting) == "10:00–11:20"
    assert meeting_days(CourseMeetingTime()) == "—"


# ---- parsing the stream --------------------------------------------------------------------------

def collect(parser: TableMarkerParser, chunks: list[str]) -> list[dict]:
    events = [event for chunk in chunks for event in parser.feed(chunk)]
    return events + parser.flush()


def test_marker_split_across_chunks_becomes_one_table_event():
    parser = TableMarkerParser([TABLE])
    events = collect(parser, ["Sections:\n{{TA", "BLE:1}}\nThe A section is open."])
    assert [e["type"] for e in events] == ["text", "table", "text"]
    assert events[1]["rows"] == [["A"], ["B"]]
    assert parser.remaining() == []


def test_unknown_and_repeated_markers_are_dropped_not_shown():
    parser = TableMarkerParser([TABLE])
    events = collect(parser, ["{{TABLE:1}} again {{TABLE:1}} and {{TABLE:9}} end"])
    assert [e["type"] for e in events].count("table") == 1
    assert "{{" not in "".join(e.get("text", "") for e in events)


def test_braces_that_are_not_markers_are_released_as_text():
    parser = TableMarkerParser([TABLE])
    events = collect(parser, ["set {a, b} and a trailing {"])
    assert "".join(e["text"] for e in events) == "set {a, b} and a trailing {"


def test_unplaced_tables_are_returned_for_the_fallback():
    parser = TableMarkerParser([TABLE])
    collect(parser, ["No marker here."])
    assert [e["type"] for e in parser.remaining()] == ["table"]


def test_unplaced_automatic_tables_are_not_returned():
    parser = TableMarkerParser([AUTOMATIC_TABLE])
    collect(parser, ["CP220 requires CP104."])
    assert parser.remaining() == []


def test_placed_automatic_tables_are_shown():
    parser = TableMarkerParser([AUTOMATIC_TABLE])
    events = collect(parser, ["CP220 is offered this term:\n{{TABLE:1}}\n"])
    assert [e["type"] for e in events].count("table") == 1


# ---- full chatbot stream ------------------------------------------------------------------------

class FakeRetrieval:
    def __init__(self, table: EvidenceTable = TABLE):
        self.table = table

    async def resolve_context(self, question, recorder, earlier, top_k):
        return ResolvedRAGContext.model_construct(
            context_text="records", sources=[], links={}, llm_profile=None, profile_name="t", tables=[self.table],
        )


class FakeSettings:
    async def get(self):
        return SimpleNamespace(
            version=16,
            generation_llm=SimpleNamespace(system="rules", turn="{context_text}\n{question}"),
        )


def chatbot(chunks: list[str], table: EvidenceTable = TABLE) -> RagChatbot:
    class FakeLLM:
        async def generate_stream(self, request, profile):
            for chunk in chunks:
                yield chunk

    return RagChatbot(
        context_resolver=FakeRetrieval(table), llm_strategy=FakeLLM(), settings_service=FakeSettings(),
        term_resolver=AcademicTermResolver(clock=lambda: date(2026, 10, 27)),
    )


async def stream_types(bot: RagChatbot) -> list[str]:
    return [json.loads(line)["type"] async for line in bot.ask("cp220 in winter?", TurnRecorder(), ConversationMemory())]


async def test_model_placed_table_streams_in_place():
    types = await stream_types(chatbot(["CP220 has 2 sections:\n{{TAB", "LE:1}}\nSection A is open."]))
    assert types[types.index("table") - 1] == "text"            # text before the table
    assert "text" in types[types.index("table") + 1:]           # text continues after it
    assert types[-1] == "sources" and types.count("table") == 1


async def test_unplaced_table_is_appended_before_sources():
    types = await stream_types(chatbot(["CP220 has 2 sections in Winter 2027."]))
    assert types[-2:] == ["table", "sources"]


async def test_unplaced_automatic_table_is_not_appended():
    types = await stream_types(chatbot(["CP220 requires CP104."], table=AUTOMATIC_TABLE))
    assert "table" not in types and types[-1] == "sources"


async def test_placed_table_and_surrounding_text_are_recorded_after_marker_resolution():
    recorder = TurnRecorder()
    bot = chatbot(["Details:\n{{TAB", "LE:1}}\nAfter."])
    events = [json.loads(line) async for line in bot.ask("cp220 in winter?", recorder, ConversationMemory())]
    # The snapshot must contain resolved table data, never the model's placement marker.
    saved = recorder.answer_message(uuid4(), ChatTurnContext(client_id_hash="device"), MessageStatus.COMPLETE)
    blocks = saved.answer_content.model_dump()["blocks"]
    assert [block["type"] for block in blocks] == ["text", "table", "text"]
    assert blocks[0]["text"] == "Details:\n"
    assert blocks[1] == next(event for event in events if event["type"] == "table")
    assert blocks[2]["text"] == "\nAfter."


async def test_unplaced_appended_table_is_also_recorded():
    recorder = TurnRecorder()
    bot = chatbot(["CP220 has two sections."])
    _events = [line async for line in bot.ask("cp220 in winter?", recorder, ConversationMemory())]
    saved = recorder.answer_message(uuid4(), ChatTurnContext(client_id_hash="device"), MessageStatus.COMPLETE)
    assert [block.type for block in saved.answer_content.blocks] == ["text", "table"]
