"""add bonus cost, bought flag, and generated cost_multiplier

The schema recorded what a bonus *paid* (``bet``, ``win``) but never what it
*cost*, so ``multiplier`` conflated a cheap natural trigger with an expensive
bonus buy and per-bonus return was not derivable.

- ``cost`` — the buy price. NULL when the bonus was not bought, or when the price
  is unknown. Independent of ``bet``.
- ``bought`` — deliberately **nullable**, giving three states. NULL means
  "unknown", which is the honest value for every row imported from the original
  data set; True/False are only ever written by the application. Defaulting the
  existing rows to false would assert something untrue about them, the same
  reasoning that made ``played_on`` nullable rather than inventing dates.
- ``cost_multiplier`` — generated, ``win * 1.0 / NULLIF(cost, 0)``. Generated for
  the same reason as ``multiplier``: it cannot drift from its inputs. NULLIF guards
  a zero cost. The ``* 1.0`` forces exact division: SQLite (used by the test suite)
  does integer division when both operands are whole numbers, so ``250 / 20`` would
  yield 12 rather than 12.5 and the tests would disagree with PostgreSQL. The
  literal is numeric on PostgreSQL, so no floating-point error is introduced.

Additive and fully reversible.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bonus", sa.Column("cost", sa.Numeric(12, 2), nullable=True))
    op.add_column("bonus", sa.Column("bought", sa.Boolean(), nullable=True))
    op.add_column(
        "bonus",
        sa.Column(
            "cost_multiplier",
            sa.Numeric(14, 4),
            sa.Computed("win * 1.0 / NULLIF(cost, 0)", persisted=True),
            nullable=True,
        ),
    )
    op.create_check_constraint("cost_nonneg", "bonus", "cost IS NULL OR cost >= 0")


def downgrade() -> None:
    op.drop_constraint("cost_nonneg", "bonus", type_="check")
    op.drop_column("bonus", "cost_multiplier")
    op.drop_column("bonus", "bought")
    op.drop_column("bonus", "cost")
