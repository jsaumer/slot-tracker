"""add partial index bonus_session_idx

Supports the per-session P&L query (bonuses attached to a play session). Partial
— indexes only the rows that carry a session_id, mirroring bonus_hunt_idx. The
vast majority of historical rows import with session_id NULL and are excluded.

Additive, cheap (largest table ~13k rows), and fully reversible.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "bonus_session_idx",
        "bonus",
        ["session_id"],
        postgresql_where="session_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("bonus_session_idx", table_name="bonus")
