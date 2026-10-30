"""Course cache on the shared byte store (namespaced keys)."""
from backend.domain.ports.providers.caching.key_value_store import KeyValueStore
from ..base import ByteCache

class CourseCache(ByteCache):
    def __init__(self, store: KeyValueStore):
        super().__init__(store, "school:course")
