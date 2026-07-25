"""Test helpers.

An in-memory SQLite database created from the model metadata. Recent SQLite
supports STORED generated columns, CHECK constraints, and partial indexes, so
the schema — including bonus.multiplier and session.net — materializes and the
loader's real code path runs without Postgres. Exact NUMERIC/Decimal arithmetic
still belongs in Postgres-backed CI and in the pure-Python aggregation tests;
here we assert structure, idempotency, and counts.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


def make_sessionmaker() -> sessionmaker:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
