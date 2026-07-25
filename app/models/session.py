"""Play sessions — deposit / cashout / net. The only source of real P/L.

Named ``PlaySession`` to avoid shadowing ``sqlalchemy.orm.Session`` anywhere the
two might be imported together; the table is ``session`` per the brief.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Computed, DateTime, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlaySession(Base):
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deposit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cashout: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Generated column — never written from Python, never recomputed here.
    net: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("COALESCE(cashout, 0) - COALESCE(deposit, 0)", persisted=True),
    )
    notes: Mapped[str | None] = mapped_column(Text)
