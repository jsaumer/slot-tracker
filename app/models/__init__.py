"""SQLAlchemy models.

Importing this package registers every mapped class on ``Base.metadata`` — which
is what Alembic's env.py imports as its target metadata, and what makes the
string-named relationships resolve.
"""

from __future__ import annotations

from app.models.base import Base
from app.models.bonus import Bonus
from app.models.game import Game, GameAlias
from app.models.hunt import Hunt
from app.models.session import PlaySession

__all__ = [
    "Base",
    "Bonus",
    "Game",
    "GameAlias",
    "Hunt",
    "PlaySession",
]
