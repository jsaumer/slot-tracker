# slot-tracker

A self-hosted web app for tracking slot bonuses, bonus hunts, and play sessions — built to replace a
sprawling multi-sheet spreadsheet with something usable one-handed on a phone during play.

Server-rendered Python. No JavaScript build step, no frontend framework, no CDN dependencies.

> [!IMPORTANT]
> **There is no authentication.** Access control is network position — this app is designed to run on
> a private network (LAN, VPN, or behind an authenticating reverse proxy). Do not expose it directly
> to the internet.

## Features

| Surface | What it does |
|---|---|
| **Add bonus** | The hot path, designed for one-handed phone use. Game autocomplete, bet defaulting to the last used value, live multiplier as you type the win, and typo correction via an alias table. |
| **Log** | Search by game or notes; filter by date range, bet, multiplier band, notable, has-replay, or suspect date. Click any column to sort. Inline edit and delete. Summary aggregates for the current filter. |
| **Dashboard** | Headline counts, total winnings, mean/median/best multiplier, distribution bands, and by-year / by-bet-size breakdowns. |
| **Game stats** | Per-game count, total win, mean/best/worst multiplier, first and last played. Searchable, sortable, paginated, with a detail page per game. Includes tools to merge duplicate games and manage spelling aliases. |
| **Hunt mode** | Open a hunt with a start balance, add bonuses as they're opened, close with an end balance and a convention; reports cost, net, and ROI. |
| **Sessions** | Deposit, cashout, net, and a running total — the only place real profit or loss is tracked. Bonuses can be attached to a session for per-session P&L. |
| **Export** | CSV of the bonus log, so the data is never trapped in the container. |
| **`/healthz`** | Liveness probe. Returns 200 with no database dependency. |

## Stack

- **Python 3.14**, FastAPI, served by uvicorn
- **SQLAlchemy 2** (sync) with the psycopg 3 driver, **Alembic** for migrations
- **PostgreSQL 18**
- **Jinja2** templates with **HTMX** for interactivity (vendored, no CDN)
- **uv** for dependency management; **ruff** for lint and format; **pytest** for tests

Money and multipliers are `Decimal` throughout — never float. `bonus.multiplier` and `session.net`
are database-generated columns, so they can't drift from their inputs.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and a PostgreSQL instance. A throwaway local database is
included via Docker Compose.

```bash
uv sync
cp .env.example .env
docker compose -f compose.dev.yaml up -d      # local postgres on 127.0.0.1:5432
uv run alembic upgrade head
uv run uvicorn app.main:app --reload          # http://127.0.0.1:8000
```

## Configuration

All configuration comes from environment variables. The two secrets have **no defaults** — the app
fails loudly at startup if they're missing rather than coming up half-configured.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | **yes** | — | Read whole, e.g. `postgresql+psycopg://user:pass@host:5432/dbname`. Assembled by the deployer; the app never reparses it. |
| `SECRET_KEY` | **yes** | — | Session/cookie signing. Generate with `openssl rand -hex 32`. |
| `APP_URL` | no | `http://localhost:8000` | Public base URL. |
| `LOG_LEVEL` | no | `info` | |
| `TZ` | no | `America/Chicago` | Timestamps are stored in UTC and rendered in this zone. |
| `RUN_MIGRATIONS_ON_STARTUP` | no | `true` | Runs `alembic upgrade head` from the container entrypoint before serving. |

If a password is interpolated into `DATABASE_URL`, use a URL-safe value — hex is a good choice, since
base64 output can contain `/`, `+`, and `=`, which break URL-form connection strings.

## Importing an existing spreadsheet

The project ships an importer for the `.ods` workbook it was built to replace. It reads the main
bonus log and the per-hunt tabs as a **union** (not a deduplication), seeds the game and alias
tables, flags implausibly old dates as suspect rather than silently correcting them, and is
**idempotent** — safe to re-run against a populated database.

```bash
uv run slot-tracker-import path/to/Slots.ods
```

In a container, it's exposed as a console script:

```bash
docker exec <container> slot-tracker-import /import/Slots.ods
```

See [`docs/build-brief.md`](docs/build-brief.md) for the data model and the source-data findings the
importer is built around.

## Development

```bash
uv run ruff check --fix . && uv run ruff format .
uv run pytest
uv run alembic revision --autogenerate -m "description"
```

Tests run against an in-memory SQLite database built from the model metadata, so no PostgreSQL is
needed locally. Continuous integration additionally asserts that migrations apply cleanly from an
empty PostgreSQL database and that the container image builds.

### Project layout

```
app/
  main.py         app factory, router registration
  config.py       env-based settings
  db.py           engine and session dependency
  models/         SQLAlchemy models
  routers/        one module per surface — kept thin
  services/       query and aggregation logic
  templates/      Jinja2, with partials for HTMX swaps
  static/         vendored CSS and JS
  importer/       .ods importer (slot-tracker-import)
alembic/versions/ migrations
tests/
```

Routers parse input, call a service, and render. Aggregation and business rules live in
`app/services/`. Schema changes go through Alembic — never `create_all()` outside tests.

## Deployment

The container image is built by GitHub Actions on `v*` tags and published to a container registry
with full semantic version tags (never `:latest`).

Operational characteristics:

- Listens on `0.0.0.0:8000`
- Runs as a non-root user (UID/GID 1000); the app is stateless, with all persistent state in PostgreSQL
- Migrations run at startup via the entrypoint, so deploy at a single replica with stop-first updates
- `GET /healthz` for health checks — note the runtime image contains no `curl` or `wget`, so probes
  should use something already present (for example, Python's `urllib`)

[`deploy/compose.yaml`](deploy/compose.yaml) is a working Docker Swarm stack — a reference example
including PostgreSQL, an internal overlay network, and reverse-proxy labels. Expect to adapt the
hostnames, volumes, and placement constraints to your own environment.

## Documentation

| File | What it is |
|---|---|
| [`docs/build-brief.md`](docs/build-brief.md) | Data model, schema, and source-data analysis. The functional specification. |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Current state and the enhancement backlog. |
| [`CLAUDE.md`](CLAUDE.md) | Repository conventions and hard constraints, written for AI coding assistants. |
| [`DEPLOY.md`](DEPLOY.md) | Deployment notes for the environment this was originally built for. Specific to that setup; useful as a worked example. |

## License

MIT.
