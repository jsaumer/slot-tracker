"""Database engine and session plumbing.

Sync SQLAlchemy 2.x over the psycopg 3 driver. The engine is created once at
import; ``create_engine`` does not open a connection, so importing this module
never touches the database — which is what keeps ``/healthz`` DB-independent.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    # Long-lived container against a separate Postgres — validate connections
    # before use so a Postgres restart doesn't hand out dead ones.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with SessionLocal() as session:
        yield session
