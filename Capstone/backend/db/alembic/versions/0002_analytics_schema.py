"""create simplified analytics schema (canonical_interactions + daily aggregate)

Revision ID: 0002_analytics_schema
Revises: 0001_app_schema
Create Date: 2026-07-31

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_analytics_schema"
down_revision: Union[str, None] = "0001_app_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    op.create_table(
        "canonical_interactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("activity_log_id", sa.BigInteger(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("pseudonymous_user_id", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_status", sa.String(), nullable=False),
        sa.Column("answer_source", sa.String(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("form_count", sa.Integer(), nullable=True),
        sa.Column("feedback_rating", sa.String(), nullable=True),
        sa.Column(
            "topic_code", sa.String(), nullable=False, server_default="unclassified"
        ),
        sa.Column("topic_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "activity_log_id", name="uq_canonical_interactions_activity_log_id"
        ),
        schema="analytics",
    )
    op.create_index(
        "idx_canonical_interactions_occurred_at",
        "canonical_interactions",
        [sa.text("occurred_at DESC"), sa.text("id DESC")],
        schema="analytics",
    )
    op.create_index(
        "idx_canonical_interactions_topic",
        "canonical_interactions",
        ["topic_code", sa.text("occurred_at DESC")],
        schema="analytics",
    )
    op.create_index(
        "idx_canonical_interactions_user",
        "canonical_interactions",
        ["pseudonymous_user_id", sa.text("occurred_at DESC")],
        schema="analytics",
    )

    op.create_table(
        "daily_topic_aggregates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bucket_date", sa.Date(), nullable=False),
        sa.Column("topic_code", sa.String(), nullable=False),
        sa.Column("interaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "negative_feedback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "error_or_fallback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "bucket_date", "topic_code", name="uq_daily_topic_aggregates_bucket_topic"
        ),
        schema="analytics",
    )
    op.create_index(
        "idx_daily_topic_aggregates_date",
        "daily_topic_aggregates",
        ["bucket_date"],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_table("daily_topic_aggregates", schema="analytics")
    op.drop_table("canonical_interactions", schema="analytics")
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
