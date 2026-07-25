"""initial schema

Creates game, game_alias, session, hunt, bonus exactly as specified in
docs/build-brief.md — including the two generated columns (session.net,
bonus.multiplier), the CHECK constraints, and the four bonus indexes.

Fully reversible: downgrade drops everything in reverse dependency order.

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_game"),
        sa.UniqueConstraint("name", name="uq_game_name"),
    )

    op.create_table(
        "session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deposit", sa.Numeric(12, 2), nullable=True),
        sa.Column("cashout", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "net",
            sa.Numeric(12, 2),
            sa.Computed(
                "COALESCE(cashout, 0) - COALESCE(deposit, 0)", persisted=True
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_session"),
    )

    op.create_table(
        "game_alias",
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("alias", name="pk_game_alias"),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["game.id"],
            name="fk_game_alias_game_id_game",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "hunt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("hunt_date", sa.Date(), nullable=True),
        sa.Column("start_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column("end_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "end_convention",
            sa.Text(),
            server_default="after_opening",
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hunt"),
        sa.CheckConstraint(
            "end_convention IN ('after_opening', 'spin_end')",
            name="end_convention",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed')",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
            name="fk_hunt_session_id_session",
            ondelete="SET NULL",
        ),
    )

    op.create_table(
        "bonus",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("played_on", sa.Date(), nullable=False),
        sa.Column("bet", sa.Numeric(10, 4), nullable=False),
        sa.Column("win", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "multiplier",
            sa.Numeric(14, 4),
            sa.Computed("win / bet", persisted=True),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("replay_url", sa.Text(), nullable=True),
        sa.Column(
            "notable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("hunt_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column(
            "date_suspect",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bonus"),
        sa.CheckConstraint("bet > 0", name="bet_positive"),
        sa.CheckConstraint("win >= 0", name="win_nonneg"),
        sa.ForeignKeyConstraint(
            ["game_id"], ["game.id"], name="fk_bonus_game_id_game"
        ),
        sa.ForeignKeyConstraint(
            ["hunt_id"],
            ["hunt.id"],
            name="fk_bonus_hunt_id_hunt",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
            name="fk_bonus_session_id_session",
            ondelete="SET NULL",
        ),
    )
    op.create_index("bonus_game_idx", "bonus", ["game_id"])
    op.create_index("bonus_played_on_idx", "bonus", [sa.text("played_on DESC")])
    op.create_index(
        "bonus_hunt_idx",
        "bonus",
        ["hunt_id"],
        postgresql_where=sa.text("hunt_id IS NOT NULL"),
    )
    op.create_index(
        "bonus_multiplier_idx", "bonus", [sa.text("multiplier DESC")]
    )


def downgrade() -> None:
    op.drop_index("bonus_multiplier_idx", table_name="bonus")
    op.drop_index("bonus_hunt_idx", table_name="bonus")
    op.drop_index("bonus_played_on_idx", table_name="bonus")
    op.drop_index("bonus_game_idx", table_name="bonus")
    op.drop_table("bonus")
    op.drop_table("hunt")
    op.drop_table("game_alias")
    op.drop_table("session")
    op.drop_table("game")
