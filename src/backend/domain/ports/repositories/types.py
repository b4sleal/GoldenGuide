"""Shared repository type aliases."""
from uuid import UUID

type PrimaryKey = int | str | UUID | tuple[int | str | UUID, ...]