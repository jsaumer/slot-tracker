"""Game catalogue and the alias map that normalizes spellings on import."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Game(Base):
    __tablename__ = "game"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    aliases: Mapped[list[GameAlias]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class GameAlias(Base):
    """Drives both import normalization and typo-correction in the entry form.

    ``alias`` is the natural primary key — a misspelling maps to exactly one game.
    """

    __tablename__ = "game_alias"

    alias: Mapped[str] = mapped_column(Text, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id", ondelete="CASCADE"), nullable=False)

    game: Mapped[Game] = relationship(back_populates="aliases")
