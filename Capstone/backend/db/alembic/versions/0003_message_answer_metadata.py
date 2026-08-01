"""keep answer provenance on conversation messages

Adds the columns needed to re-render a stored assistant turn exactly as it
looked when it was live: the answer-source badge ("Model" / "Hit cache") and a
working feedback row. Before this, app.conversation_messages held only
role/content/created_at, so reopening a conversation dropped both.

All columns are nullable: user turns never carry them, and rows written before
this migration have no source to backfill from.

Revision ID: 0003_message_answer_metadata
Revises: 0002_analytics_schema
Create Date: 2026-08-01

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_message_answer_metadata"
down_revision: Union[str, None] = "0002_analytics_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("answer_source", sa.String(), nullable=True),
        schema="app",
    )
    op.add_column(
        "conversation_messages",
        sa.Column("feedback_id", sa.BigInteger(), nullable=True),
        schema="app",
    )
    op.add_column(
        "conversation_messages",
        sa.Column("feedback_token", sa.String(), nullable=True),
        schema="app",
    )
    op.add_column(
        "conversation_messages",
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        schema="app",
    )
    op.add_column(
        "conversation_messages",
        sa.Column("citations_json", postgresql.JSONB(), nullable=True),
        schema="app",
    )
    op.add_column(
        "conversation_messages",
        sa.Column("form_downloads_json", postgresql.JSONB(), nullable=True),
        schema="app",
    )


def downgrade() -> None:
    op.drop_column("conversation_messages", "form_downloads_json", schema="app")
    op.drop_column("conversation_messages", "citations_json", schema="app")
    op.drop_column("conversation_messages", "duration_ms", schema="app")
    op.drop_column("conversation_messages", "feedback_token", schema="app")
    op.drop_column("conversation_messages", "feedback_id", schema="app")
    op.drop_column("conversation_messages", "answer_source", schema="app")
