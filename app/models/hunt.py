"""Bonus hunts — open with a start balance, add bonuses, close with an end
balance and a convention. See docs/build-brief.md for the cost/net formulas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.bonus import Bonus
    from app.models.session import PlaySession


class Hunt(Base):
    __tablename__ = "hunt"
    __table_args__ = (
        CheckConstraint(
            "end_convention IN ('after_opening', 'spin_end')",
            name="end_convention",
        ),
        CheckConstraint(
            "status IN ('open', 'closed')",
            name="status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str | None] = mapped_column(Text)
    hunt_date: Mapped[date | None] = mapped_column(Date)
    start_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    end_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    end_convention: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="after_opening"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    session_id: Mapped[int | None] = mapped_column(ForeignKey("session.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    # Stable source identity ("hunt:N") for idempotent import. NULL for hunts
    # created in the app. Added in migration 0002 — see bonus.import_ref.
    import_ref: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    bonuses: Mapped[list[Bonus]] = relationship(back_populates="hunt")
    session: Mapped[PlaySession | None] = relationship()
