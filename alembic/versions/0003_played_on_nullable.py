"""make bonus.played_on nullable

The build-brief schema declared ``bonus.played_on DATE NOT NULL``, but the source
workbook's hunt tabs and notable-hits sheet carry **no per-bonus date** — only the
main log does. Those ~623 hunt bonuses (and any unmatched notable rows) must still
import (they make up the ~13,095 total), so played_on is relaxed to nullable.

App-entered bonuses always set played_on (the form defaults it to today), so nulls
only ever come from the historical import.

Deviation from the original brief schema — recorded in DEPLOY.md.

**Downgrade is destructive-capable:** restoring NOT NULL fails if any null-dated
rows exist (they will, after import). Rollback in production is image-revert plus
a database dump restore, not an Alembic downgrade — see DEPLOY.md.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("bonus", "played_on", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    # Will fail if null-dated rows exist. Intentional — see docstring.
    op.alter_column("bonus", "played_on", existing_type=sa.Date(), nullable=False)
