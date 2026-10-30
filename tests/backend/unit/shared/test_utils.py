"""Pure helpers in backend.shared.utils."""
from datetime import datetime

import pytest
from pydantic import BaseModel

from backend.shared.utils.academic_year import get_current_academic_year
from backend.shared.utils.deep_merge import deep_merge_dicts
from backend.shared.utils.frag_reducer import dedupe_fragments
from backend.shared.utils.hashing import compute_uuid
from backend.shared.utils.size_batching import batch_by_size


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        (datetime(2026, 3, 15), "2025/2026"),
        (datetime(2026, 8, 31), "2025/2026"),
        (datetime(2026, 9, 1), "2026/2027"),
        (datetime(2026, 12, 31), "2026/2027"),
    ],
)
def test_academic_year_rolls_over_in_september(date, expected):
    assert get_current_academic_year(date) == expected


def test_deep_merge_keeps_sibling_keys_and_does_not_mutate():
    base = {"llm": {"model": "a", "temp": 0}, "tags": [1]}
    merged = deep_merge_dicts(base, {"llm": {"temp": 1}, "tags": [2]})
    assert merged == {"llm": {"model": "a", "temp": 1}, "tags": [2]}
    assert base == {"llm": {"model": "a", "temp": 0}, "tags": [1]}


class Fragment(BaseModel):
    code: str
    description: str | None = None
    prerequisites: str | None = None


def test_fragments_merge_without_none_erasing_values():
    merged = dedupe_fragments(
        Fragment,
        [
            Fragment(code="CP317", description="Software Engineering"),
            Fragment(code="CP317", prerequisites="CP213"),
            Fragment(code="CP104"),
        ],
        fields=["code"],
    )
    assert merged == [
        Fragment(code="CP317", description="Software Engineering", prerequisites="CP213"),
        Fragment(code="CP104"),
    ]


def test_uuid_is_deterministic():
    assert compute_uuid("same text") == compute_uuid("same text") != compute_uuid("other")


def test_batches_respect_limit_and_order():
    batches = list(batch_by_size([4, 4, 4, 9], max_bytes=10, size_of=lambda n: n, overhead=1))
    assert batches == [[4, 4], [4], [9]]


def test_oversized_item_is_rejected_not_dropped():
    with pytest.raises(ValueError, match="exceeds"):
        list(batch_by_size([11], max_bytes=10, size_of=lambda n: n))
