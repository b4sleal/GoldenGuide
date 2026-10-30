"""Retrieval results: Evidence records (three detail levels), table rows, and per-request outcomes.

RetrievalStatus keeps "completed" (possibly with zero records), "unsupported" and "failed" distinct,
so a failed lookup is never reported as "no such information".
"""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.entities.retrieval_plan import RetrievalRequest


class RetrievalStatus(StrEnum):
    COMPLETED = "completed"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class TableRow(BaseModel):
    """Display cells for one record, so the answer can show it in a table built from data, not by the LLM.

    Rows with the same `group` form one table (e.g. every CP220 section in Winter 2027).
    `cells` maps column name -> display text; its insertion order is the column order.
    """
    model_config = ConfigDict(frozen=True)

    group: str
    cells: dict[str, str]


class EvidenceTable(BaseModel):
    """A table the answer model can place with a marker; sent to the browser as one `table` stream event."""
    model_config = ConfigDict(frozen=True)

    table_id: str
    title: str
    columns: list[str]
    rows: list[list[str]]
    # True when the student asked for these records (a planned request): the table is shown after
    # the answer if the model didn't place it. False for automatic lookups: shown only where placed.
    append_if_unplaced: bool = True


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    title: str
    url: str = ""
    content: str
    primary: bool = True

    compact_content: str | None = None
    minimal_content: str | None = None

    external_links: list[str] = Field(default_factory=list)

    # Optional tabular view of this record (see TableRow). Kept at full detail even when
    # `content` is trimmed to a compact tier for the prompt.
    table_row: TableRow | None = None
    # Prompt text used instead of `content` when this record is shown in a table: short enough
    # that the model refers to the table rather than retyping it. None keeps `content`.
    table_content: str | None = None

class RetrievalOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: RetrievalRequest
    status: RetrievalStatus
    count: int | None = Field(default=None, ge=0)
    error: str | None = None
    # Set when more records matched than were retrieved: the limit that cut the results off.
    truncated_at: int | None = Field(default=None, gt=0)