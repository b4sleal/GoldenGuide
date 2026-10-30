"""Qdrant deletes refuse an empty filter, which would otherwise match the whole collection."""
import pytest

from backend.infra.persistence.vectors.qdrant.store import QDrantStore


class RecordingClient:
    def __init__(self):
        self.deleted = []

    async def delete(self, collection_name, points_selector, wait):
        self.deleted.append(points_selector)


def store():
    instance = QDrantStore.__new__(QDrantStore)  # No connection needed: only the filter logic runs.
    instance.client = RecordingClient()
    return instance


@pytest.mark.parametrize("filters", [{}, None, {"source_id": None}])
async def test_delete_without_a_usable_filter_is_refused(filters):
    qdrant = store()

    with pytest.raises(ValueError, match="Refusing to delete"):
        await qdrant.delete("collection", filters)

    assert qdrant.client.deleted == []


async def test_delete_with_a_filter_goes_through():
    qdrant = store()

    await qdrant.delete("collection", {"source_id": "page_1"})

    assert len(qdrant.client.deleted) == 1
