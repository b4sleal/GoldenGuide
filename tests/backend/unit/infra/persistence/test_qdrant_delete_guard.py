"""Qdrant deletes and payload changes refuse an empty filter, which would match the whole collection."""
import pytest

from backend.infra.persistence.vectors.qdrant.store import QDrantStore


class RecordingClient:
    def __init__(self):
        self.calls = []

    async def delete(self, collection_name, points_selector, wait):
        self.calls.append(("delete", points_selector))

    async def set_payload(self, collection_name, payload, points, wait):
        self.calls.append(("set_payload", payload))

    async def delete_payload(self, collection_name, keys, points, wait):
        self.calls.append(("delete_payload", keys))


def store():
    instance = QDrantStore.__new__(QDrantStore)  # No connection needed: only the filter logic runs.
    instance.client = RecordingClient()
    return instance


@pytest.mark.parametrize("filters", [{}, None, {"source_id": None}])
async def test_delete_without_a_usable_filter_is_refused(filters):
    qdrant = store()

    with pytest.raises(ValueError, match="Refusing to change points"):
        await qdrant.delete("collection", filters)

    assert qdrant.client.calls == []


async def test_delete_with_a_filter_goes_through():
    qdrant = store()

    await qdrant.delete("collection", {"source_id": "page_1"})

    assert [name for name, _ in qdrant.client.calls] == ["delete"]


@pytest.mark.parametrize("filters", [{}, None, {"source_id": None}])
async def test_payload_change_without_a_usable_filter_is_refused(filters):
    qdrant = store()

    with pytest.raises(ValueError, match="Refusing to change points"):
        await qdrant.set_payload("collection", filters, {"academic_level": "graduate"}, [])

    assert qdrant.client.calls == []


async def test_payload_change_sets_values_and_removes_keys():
    qdrant = store()

    await qdrant.set_payload("collection", {"source_id": "page_1"}, {"academic_level": "graduate"}, ["title"])

    assert qdrant.client.calls == [("set_payload", {"academic_level": "graduate"}), ("delete_payload", ["title"])]
