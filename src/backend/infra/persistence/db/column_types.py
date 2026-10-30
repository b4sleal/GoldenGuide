"""Portable column types shared by the table definitions."""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Portable JSON document column: JSONB on PostgreSQL, the dialect's native JSON elsewhere.
JsonDoc = JSON().with_variant(JSONB(), "postgresql")
