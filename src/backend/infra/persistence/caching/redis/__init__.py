"""Redis transport: connection factory, byte store, and the generic cache adapter used by AppCache."""
from .legacy import RedisCache

__all__ = ["RedisCache"]
