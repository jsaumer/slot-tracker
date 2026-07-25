"""Application configuration.

All settings come from environment variables (CLAUDE.md constraint 4). There are
no baked defaults for the two secrets: if ``DATABASE_URL`` or ``SECRET_KEY`` are
absent, constructing ``Settings`` raises and the process dies at startup rather
than coming up half-configured.

``DATABASE_URL`` is read whole — the deployer assembles it (DEPLOY.md section 4),
so this app never parses or reassembles its parts.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_file is a local-dev convenience only. In the container there is no
    # .env (excluded by .dockerignore); real environment variables win either
    # way and take priority over the file.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required — no default. Missing => ValidationError at startup.
    database_url: str
    secret_key: str

    # Non-secret config with sensible defaults.
    app_url: str = "http://localhost:8000"
    log_level: str = "info"
    tz: str = "America/Chicago"


settings = Settings()
"""Module-level singleton. Evaluated at import, so misconfiguration fails loudly
the moment anything imports app.config."""
