"""Shared test fixtures and environment defaults.

``app.config`` requires DATABASE_URL and SECRET_KEY at import time. CI provides
real values; locally we fall back to placeholders here. ``setdefault`` means a
real environment (CI, or a developer's shell) always wins — these are only a
floor so imports don't explode in a bare checkout.

The DATABASE_URL placeholder is never connected to by the health test:
importing the engine does not open a socket, and /healthz has no DB dependency.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://slottracker:test@127.0.0.1:5432/slottracker",
)
os.environ.setdefault("SECRET_KEY", "test-only-not-a-real-secret")
