#!/bin/sh
set -eu

# Migrations run before the app accepts traffic. Safe because the service runs at
# replicas: 1 with stop-first updates — there is never a second instance migrating
# concurrently. See CLAUDE.md constraint 5.
if [ "${RUN_MIGRATIONS_ON_STARTUP:-true}" = "true" ]; then
    echo "[entrypoint] running alembic upgrade head"
    alembic upgrade head
    echo "[entrypoint] migrations complete"
else
    echo "[entrypoint] RUN_MIGRATIONS_ON_STARTUP is not 'true' — skipping migrations"
fi

exec "$@"
