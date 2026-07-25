"""add import_ref to bonus and hunt

Adds a nullable, unique ``import_ref`` to ``bonus`` and ``hunt`` giving each
imported source row a stable, non-content identity so the importer is idempotent
(CLAUDE.md / build-brief: "safe to re-run against a populated database").

A content key (game, date, bet, win) cannot serve this purpose: the source has
documented coincidental collisions that the brief requires be kept as distinct
rows ("import is a union, not a dedup"). Rows entered through the app leave
import_ref NULL; UNIQUE permits many NULLs in PostgreSQL.

Deviation from the original build-brief schema — recorded in DEPLOY.md.
Additive and fully reversible.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bonus", sa.Column("import_ref", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_bonus_import_ref", "bonus", ["import_ref"])
    op.add_column("hunt", sa.Column("import_ref", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_hunt_import_ref", "hunt", ["import_ref"])


def downgrade() -> None:
    op.drop_constraint("uq_hunt_import_ref", "hunt", type_="unique")
    op.drop_column("hunt", "import_ref")
    op.drop_constraint("uq_bonus_import_ref", "bonus", type_="unique")
    op.drop_column("bonus", "import_ref")
