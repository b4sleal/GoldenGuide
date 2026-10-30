"""Tables built from retrieved records and placed in the answer by the model.

Why: when an answer lists many sections, the LLM retyping them as a Markdown table is slow and
expensive (output tokens), and it can drop, merge or mistype rows. Instead:

    1. build_tables()       groups records that carry a TableRow into tables (exact database values)
    2. table_catalog_text()  lists them in the context: "{{TABLE:1}}: CP220 sections — Winter 2027"
    3. prompt_records()     tabled records reach the model as their short `table_content`, enough to
                            summarize and recommend but not a listing to retype
    4. the model writes the marker where the table belongs
    5. TableMarkerParser     swaps each marker in the stream for one {"type": "table", ...} event
    6. remaining()           unplaced tables the student asked for are appended after the text

The model decides WHERE a table goes; the data decides WHAT is in it.
"""
import re

from backend.domain.entities.retrieval import Evidence, EvidenceTable

# A table is only worth it from this many rows; one section reads better as a sentence.
MIN_TABLE_ROWS = 2

# Heading the generation prompt refers to (configs/base/ai_behavior.yml, rule 15).
SECTION_HEADING = "AVAILABLE TABLES"

MARKER_PATTERN = re.compile(r"\{\{TABLE:(\d+)\}\}")
# Any prefix of a marker ("{", "{{TA", "{{TABLE:1", "{{TABLE:1}") that might complete in the next chunk.
_POSSIBLE_MARKER = re.compile(r"\{(?:\{(?:T(?:A(?:B(?:L(?:E(?::\d*\}?)?)?)?)?)?)?)?\Z")


def marker(table: EvidenceTable) -> str:
    return f"{{{{TABLE:{table.table_id}}}}}"


def build_tables(
        records: list[Evidence], requested_ids: set[str], min_rows: int = MIN_TABLE_ROWS,
) -> list[EvidenceTable]:
    """Group records by TableRow.group, in first-seen order, keeping groups with at least `min_rows` rows.

    A table holding any record from `requested_ids` (a planned request) is appended if unplaced.
    """
    # Step 1: collect records per group (dicts preserve insertion order, so tables follow retrieval order).
    groups: dict[str, list[Evidence]] = {}
    for record in records:
        if record.table_row is not None:
            groups.setdefault(record.table_row.group, []).append(record)

    # Step 2: one table per large-enough group. Columns are the union of row keys in first-seen
    # order, so a row missing a column gets an empty cell instead of shifting the others.
    tables = []
    for title, group in groups.items():
        if len(group) < min_rows:
            continue
        rows = [record.table_row.cells for record in group if record.table_row is not None]
        columns = list(dict.fromkeys(column for row in rows for column in row))
        tables.append(EvidenceTable(
            table_id=str(len(tables) + 1),
            title=title,
            columns=columns,
            rows=[[row.get(column, "") for column in columns] for row in rows],
            append_if_unplaced=any(record.source_id in requested_ids for record in group),
        ))
    return tables


def prompt_records(records: list[Evidence], tables: list[EvidenceTable]) -> list[Evidence]:
    """Records shown in one of `tables` use their `table_content` in the prompt (when they define one)."""
    tabled_groups = {table.title for table in tables}
    return [
        record.model_copy(update={"content": record.table_content})
        if record.table_content and record.table_row and record.table_row.group in tabled_groups
        else record
        for record in records
    ]


def table_catalog_text(tables: list[EvidenceTable]) -> str:
    """The context block telling the model which markers exist ('' when there are none)."""
    if not tables:
        return ""
    lines = [f"- {marker(table)}: {table.title} ({len(table.rows)} rows)" for table in tables]
    return (
        f"\n\n{SECTION_HEADING} (complete tables of records above; the app shows each one where you write its marker):\n"
        + "\n".join(lines)
        + "\nTo show one, write its marker exactly, on its own line. Never retype its rows."
    )


def table_event(table: EvidenceTable) -> dict:
    """Stream event for the browser (see src/frontend/script.js)."""
    return {"type": "table", "title": table.title, "columns": table.columns, "rows": table.rows}


class TableMarkerParser:
    """Turns {{TABLE:n}} markers in streamed text into table events, across chunk boundaries.

    Same approach as CitationStreamParser: text that might be the start of a marker is held back
    until the next chunk shows whether it completes. Each table is shown at most once; markers for
    unknown or already-shown tables are dropped (never shown to the student as raw text).
    """

    def __init__(self, tables: list[EvidenceTable]):
        self.tables = {table.table_id: table for table in tables}
        self.placed: set[str] = set()
        self.buffer = ""

    def feed(self, text: str) -> list[dict]:
        self.buffer += text
        events: list[dict] = []

        # Step 1: emit text before each complete marker, then the table itself.
        while match := MARKER_PATTERN.search(self.buffer):
            if match.start():
                events.append({"type": "text", "text": self.buffer[:match.start()]})
            table_id = match.group(1)
            if table_id in self.tables and table_id not in self.placed:
                self.placed.add(table_id)
                events.append(table_event(self.tables[table_id]))
            self.buffer = self.buffer[match.end():]

        # Step 2: hold back a trailing partial marker; release everything before it.
        hold_from = len(self.buffer)
        for index in range(len(self.buffer)):
            if self.buffer[index] == "{" and _POSSIBLE_MARKER.match(self.buffer, index):
                hold_from = index
                break
        if hold_from:
            events.append({"type": "text", "text": self.buffer[:hold_from]})
            self.buffer = self.buffer[hold_from:]

        return events

    def flush(self) -> list[dict]:
        """End of stream: whatever is held back was not a marker after all, so release it as text."""
        events = self.feed("")
        if self.buffer:
            events.append({"type": "text", "text": self.buffer})
            self.buffer = ""
        return events

    def remaining(self) -> list[dict]:
        """Table events for requested tables the model never placed (appended after the answer text).

        Tables from automatic lookups are left out: the model didn't place them because the answer
        isn't about those records (e.g. sections in a prerequisites answer).
        """
        return [
            table_event(table) for table_id, table in self.tables.items()
            if table_id not in self.placed and table.append_if_unplaced
        ]
