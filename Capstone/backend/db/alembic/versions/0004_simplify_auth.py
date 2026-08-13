"""simplify Google SSO role resolution and session metadata

Revision ID: 0004_simplify_auth
Revises: 0003_message_answer_metadata
Create Date: 2026-08-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_simplify_auth"
down_revision: Union[str, None] = "0003_message_answer_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the existing value so sessions signed before deployment remain valid.
    op.execute(
        """
        INSERT INTO app.app_state_meta (key, value)
        SELECT 'session_signing_secret', value
        FROM app.app_state_meta
        WHERE key = 'admin_session_secret'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute("DELETE FROM app.app_state_meta WHERE key = 'admin_session_secret'")
    op.drop_column("admin_accounts", "password", schema="app")


def downgrade() -> None:
    op.add_column(
        "admin_accounts",
        sa.Column("password", sa.String(), nullable=False, server_default=""),
        schema="app",
    )
    op.execute(
        """
        INSERT INTO app.app_state_meta (key, value)
        SELECT 'admin_session_secret', value
        FROM app.app_state_meta
        WHERE key = 'session_signing_secret'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute("DELETE FROM app.app_state_meta WHERE key = 'session_signing_secret'")
