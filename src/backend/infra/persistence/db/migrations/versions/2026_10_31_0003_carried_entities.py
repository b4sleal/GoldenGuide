"""carried entities

Entities an answer carries forward, so the next question in the conversation can refer back to them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 18:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations.
revision: str = '0003'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this change."""
    op.add_column('chat_messages', sa.Column('carried_entities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Undo this change (used to roll back a deploy)."""
    op.drop_column('chat_messages', 'carried_entities')
