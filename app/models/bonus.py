"""The bonus record — one table for everything.

``hunt_id IS NULL`` means an ordinary logged bonus; a non-null ``hunt_id`` ties
it to a hunt. ``multiplier`` is a generated column so X can never drift from
win/bet the way it did in the later hunt tabs of the source workbook.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    column,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.hunt import Hunt
    from app.models.session import PlaySession


class Bonus(Base):
    __tablename__ = "bonus"
    __table_args__ = (
        CheckConstraint("bet > 0", name="bet_positive"),
        CheckConstraint("win >= 0", name="win_nonneg"),
        CheckConstraint("cost IS NULL OR cost >= 0", name="cost_nonneg"),
        # The four indexes from the brief, with their exact names.
        Index("bonus_game_idx", "game_id"),
        Index("bonus_played_on_idx", column("played_on").desc()),
        Index(
            "bonus_hunt_idx",
            "hunt_id",
            postgresql_where=text("hunt_id IS NOT NULL"),
        ),
        # Added in migration 0004 for the per-session P&L query.
        Index(
            "bonus_session_idx",
            "session_id",
            postgresql_where=text("session_id IS NOT NULL"),
        ),
        Index("bonus_multiplier_idx", column("multiplier").desc()),
    )

    # BIGSERIAL on Postgres; INTEGER on SQLite so the test DB's rowid
    # autoincrement kicks in (SQLite only auto-assigns INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("game.id"), nullable=False)
    # Nullable: hunt and notable source rows carry no per-bonus date. App-entered
    # bonuses always set it. See migration 0003 and DEPLOY.md.
    played_on: Mapped[date | None] = mapped_column(Date)
    bet: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    win: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Generated column — never written from Python, never recomputed here.
    multiplier: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), Computed("win / bet", persisted=True)
    )
    # What was paid to trigger this bonus — a bonus-buy price. NULL when the bonus
    # was not bought, or when the cost is unknown. Independent of `bet`: a buy is
    # typically 75-100x the spin stake, but neither derives from the other.
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Deliberately three-state. NULL means "unknown", which is the honest value for
    # every historically imported row; True/False are only ever set by the app. See
    # migration 0005 and DEPLOY.md.
    bought: Mapped[bool | None] = mapped_column(Boolean)
    # Generated column — how many times a buy paid for itself. NULLIF guards a zero
    # cost. The `* 1.0` is load-bearing for portability: SQLite performs integer
    # division when both operands are whole numbers (250 / 20 -> 12, not 12.5),
    # which would make the test database disagree with PostgreSQL. Multiplying by a
    # decimal literal forces exact division on both, and stays numeric on
    # PostgreSQL so no float error is introduced.
    cost_multiplier: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), Computed("win * 1.0 / NULLIF(cost, 0)", persisted=True)
    )
    notes: Mapped[str | None] = mapped_column(Text)
    replay_url: Mapped[str | None] = mapped_column(Text)
    notable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hunt_id: Mapped[int | None] = mapped_column(ForeignKey("hunt.id", ondelete="SET NULL"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("session.id", ondelete="SET NULL"))
    date_suspect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Stable source-row identity for idempotent import (sheet + row coordinate).
    # NULL for rows entered through the app. See docs/build-brief.md import notes
    # and DEPLOY.md — added in migration 0002, not part of the original brief
    # schema. Content-based keys can't be used: the source has documented
    # coincidental (game, date, bet, win) collisions that must NOT be deduped.
    import_ref: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    game: Mapped[Game] = relationship()
    hunt: Mapped[Hunt | None] = relationship(back_populates="bonuses")
    session: Mapped[PlaySession | None] = relationship()
