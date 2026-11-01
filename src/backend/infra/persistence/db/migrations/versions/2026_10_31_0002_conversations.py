"""conversations

Stored chat conversations, their messages with retrieval diagnostics, and per-message feedback.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations.
revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this change."""
    op.create_table('conversations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_subject', sa.String(length=255), nullable=True),
    sa.Column('client_id_hash', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_owner_subject'), 'conversations', ['owner_subject'], unique=False)
    op.create_index(op.f('ix_conversations_client_id_hash'), 'conversations', ['client_id_hash'], unique=False)
    op.create_table('chat_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('query_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('retrieval_outcomes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('profile_name', sa.String(length=128), nullable=True),
    sa.Column('settings_version', sa.Integer(), nullable=True),
    sa.Column('timings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('trace_id', sa.String(length=32), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('error_type', sa.String(length=256), nullable=True),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'position', name='uq_chat_messages_conversation_position')
    )
    op.create_index(op.f('ix_chat_messages_conversation_id'), 'chat_messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_status'), 'chat_messages', ['status'], unique=False)
    op.create_index(op.f('ix_chat_messages_trace_id'), 'chat_messages', ['trace_id'], unique=False)
    op.create_table('message_feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('message_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.String(length=8), nullable=False),
    sa.Column('reason', sa.String(length=32), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('message_id')
    )


def downgrade() -> None:
    """Undo this change (used to roll back a deploy)."""
    op.drop_table('message_feedback')
    op.drop_index(op.f('ix_chat_messages_trace_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_status'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_conversation_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_conversations_client_id_hash'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_owner_subject'), table_name='conversations')
    op.drop_table('conversations')
