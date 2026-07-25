# CLAUDE.md

Instructions for working in this repository.

Read `DEPLOY.md` before changing anything that touches configuration, the Dockerfile, the workflows,
or the database schema. It defines the deployment envelope and is not negotiable from inside this
repo. Read `docs/build-brief.md` for the data model and source-data findings — that is the functional
specification.

## What this is

A single-user web app that replaces a 30-sheet slot-tracking spreadsheet. It records slot bonuses,
bonus hunts, and play sessions, and reports on them. It runs as a container on a private network
behind a reverse proxy. It is never exposed to the internet.

## What already exists

Do not recreate or restructure these. Extend them if needed, and say so in the commit message.

```
.dockerignore          .env.example           .gitignore
CLAUDE.md              DEPLOY.md              README.md
Dockerfile             docker-entrypoint.sh   compose.dev.yaml
renovate.json
.github/workflows/ci.yml
.github/workflows/build.yml
deploy/compose.yaml    ← example swarm stack; adapt per environment
docs/build-brief.md    ← functional spec
```

The Dockerfile expects `pyproject.toml`, `uv.lock`, and an importable `app` package with
`app.main:app`. It expects `alembic` on `PATH` inside the venv. Build these to fit it.

## Stack

- Python 3.14 (`python:3.14.6-slim-trixie`; fall back to `3.13.11-slim-trixie` and note it in the
  commit if a dependency genuinely does not support 3.14)
- FastAPI, served by uvicorn
- SQLAlchemy 2.x (sync), psycopg 3 driver — `postgresql+psycopg://`
- Alembic for migrations
- Jinja2 templates, HTMX for interactivity
- PostgreSQL 18
- `uv` for dependency management; `pyproject.toml` and `uv.lock` are committed
- ruff for lint and format; pytest for tests

Do not add a JavaScript build step. Do not add a frontend framework. Do not add Node to the image.

## Layout to create

```
app/
  main.py            FastAPI app factory, router registration
  config.py          pydantic-settings; ALL config from env, no defaults for secrets
  db.py              engine, session dependency
  models/            SQLAlchemy models, one module per table group
  routers/           one module per surface: dashboard, bonuses, hunts, sessions, games, export
  services/          query and aggregation logic — keep routers thin
  templates/         Jinja2; base.html plus per-surface partials for HTMX swaps
  static/            vendored CSS/JS assets
  importer/          .ods importer — development-only, excluded from the image
alembic/
  versions/
tests/
```

The importer is **development-only**: no `[project.scripts]` entry point, and `app/importer/` is
excluded from the container image via `.dockerignore`. Nothing under `app/` may import it — shared
name normalization lives in `app/services/naming.py`. Do not reintroduce an entry point for it; the
built image must expose no undocumented commands.

## Commands

```
uv sync                                    install
uv run uvicorn app.main:app --reload       dev server on :8000
uv run alembic revision --autogenerate -m "…"
uv run alembic upgrade head
uv run pytest
uv run ruff check --fix . && uv run ruff format .
docker compose -f compose.dev.yaml up -d   local postgres on 127.0.0.1:5432
```

## Hard constraints

These come from the deployment envelope. Violating them breaks the deploy.

1. **No authentication, no user model, no registration, no password handling, no login sessions.**
   Access control is network position. If auth is ever added it will be forward-auth at the reverse
   proxy, above this app. Do not write header-trust logic in anticipation.
2. **Listen on `0.0.0.0:8000`.** Not configurable.
3. **`GET /healthz`** returns 200 with no database dependency. Swarm's healthcheck calls it with
   stdlib `urllib` — the runtime image has no curl or wget, so do not add a healthcheck that assumes
   they exist.
4. **All configuration from environment variables.** No config files, no CLI flags for deployment
   settings, no baked defaults for `DATABASE_URL` or `SECRET_KEY` — fail loudly at startup if they
   are missing. Read `DATABASE_URL` whole; the deployer assembles it.
5. **Migrations run at startup** via `docker-entrypoint.sh` when `RUN_MIGRATIONS_ON_STARTUP=true`.
   The app runs at `replicas: 1` with stop-first updates, so concurrent migration is not a concern —
   do not add locking complexity for it, and do not assume more than one replica anywhere.
6. **Container runs as UID/GID 1000, non-root.** No writes outside `/tmp`. The app is stateless;
   everything persistent goes to Postgres.
7. **`linux/amd64` only.** Do not add multi-arch or QEMU steps.
8. **Never `:latest`** — not in the Dockerfile, not in compose, not in workflows. Full semver
   everywhere, including base images.
9. **Vendor static assets into `app/static/`.** No CDN references.
10. **Timezone `America/Chicago`.** Store `TIMESTAMPTZ` in UTC, render local.
11. **Money and multipliers are `Decimal`, never `float`.** Match the column types in the brief
    exactly. `bonus.multiplier` and `session.net` are generated columns — never write to them from
    Python, never recompute them in application code.

## Database conventions

- Schema changes go through Alembic. Never `create_all()` outside tests.
- CI asserts migrations apply cleanly from an empty database. Keep that true.
- Reversible migrations where reasonable. If a downgrade is genuinely impossible, say so in the
  migration docstring **and** the commit message — production rollback is image-revert plus
  dump-restore, so a destructive migration has real cost.
- Do not change existing column types or drop columns without noting it in `DEPLOY.md`; database
  dumps are the recovery path.
- Index additions are cheap; the largest table is ~13k rows.

## The importer

Development-only tooling, retained for its tests and because it records how the original data set was
interpreted. It is not shipped in the image and has no entry point — run
`app.importer.cli:main` directly from a checkout. If it ever changes, these rules still hold:

- Reads `Slots.ods` directly. `pandas.read_excel(..., engine="odf")` for cells; `odfpy` walking
  `odf.text.A` elements for embedded hyperlinks.
- odfpy normalizes `https://` to `https:/` — repair with a regex before storing.
- **Must be idempotent.** Safe to re-run against a populated database.
- Import is a **union** of the main log and the hunt tabs, not a dedup — the sets are disjoint and
  the ~63 apparent collisions are coincidence at this volume.
- Flag, never silently correct: rows dated before 2021 get `date_suspect = true`.
- Seed `game_alias` from the map in the brief before importing bonuses.
- Set `end_convention = 'spin_end'` for hunt 27 only; everything else defaults to `after_opening`.
- Print a summary at the end (rows inserted, games created, hunts created, suspects flagged) so a run
  can be checked against expected figures.
- Never write to the source workbook path.

## Application surface

Build in this order — each should be usable before starting the next.

1. **Add bonus** — the hot path, used one-handed on a phone during play. Minimal fields, game
   autocomplete off `game` + `game_alias`, bet defaulting to last used, live multiplier as the win
   is typed.
2. **Log** — searchable, filterable by game / date range / bet / multiplier band.
3. **Dashboard** — headline counts, total bonus winnings, mean/median multiplier, distribution
   bands, by-year and by-bet-size breakdowns.
4. **Game stats** — count, total win, mean/best/worst multiplier, first and last played, per game.
5. **Hunt mode** — open with a start balance, add bonuses as opened, close with an end balance and a
   convention, show cost / net / ROI per the formulas in the brief.
6. **Sessions** — deposit, cashout, net, running total. The only place real profit or loss comes
   from; the spreadsheet never tracked it.
7. **Export** — CSV of the bonus log, so the data is never trapped in the container.

## Style

- Type hints everywhere. ruff config is the source of truth; don't argue with it in code.
- Routers stay thin — parse, call a service, render. Aggregation lives in `app/services/`.
- Templates return partials for HTMX requests and full pages otherwise; branch on the `HX-Request`
  header in one place, not per-route.
- Tests cover the importer's alias handling and idempotency, the hunt cost/net formulas, and the
  dashboard aggregations. Those are where correctness actually matters.
- Commit messages: imperative mood, one logical change per commit. Flag any change that requires a
  matching edit to the deployed stack definition.
