"""Declarative base and metadata.

Kept deliberately free of any import of app.config / app.db so that Alembic's
env.py can pull in the full metadata without constructing Settings (a migration
does not need SECRET_KEY). The engine lives in app.db; the schema lives here.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable constraint/index names so migrations stay deterministic and downgrades
# can reference constraints by name. The four bonus indexes and the schema's
# named CHECK constraints override this with explicit names of their own.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
