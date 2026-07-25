# Slot Tracker — Handoff to Planning (Enhancements)

_Date: 2026-07-25. Written at the end of the v1 application build, for the planning
chat that will scope enhancements. Read alongside `CLAUDE.md`, `DEPLOY.md`, and
`docs/build-brief.md`._

## Status

v1 application is **built, tested, merged to `main`, and pushed**. Importer validated
against the real `Slots.ods`. Not yet deployed. Confirm CI on the
`main` push is green — the checks not runnable on the build machine were `docker build`
and the from-empty Postgres migration.

## Where things are

- **Repo:** `main`. Feature branch merged & deleted.
- **Stack:** Python 3.14, FastAPI + uvicorn, SQLAlchemy 2 (sync, psycopg 3), Alembic,
  Jinja2 + HTMX (vendored, no CDN), Postgres 18. `uv` for deps. No JS build step, no
  frontend framework.
- **Layout:** `app/{config,db,main,templating}.py`, `app/models/`, `app/routers/` (thin),
  `app/services/` (all aggregation + formulas), `app/templates/`, `app/static/`,
  `app/importer/` (development-only, excluded from the image). Migrations `0001`–`0003`.
  Tests in `tests/` (59, all SQLite/pure — no Postgres needed).

## Built surfaces (v1 scope — all done)

Add-bonus (fast-entry hot path, live multiplier, alias-corrected), Log
(search/filter/paginate), Dashboard (counts, total, mean/median/best X, distribution
bands, by-year, by-bet), Game stats, Hunt mode (open/add/close, cost/net/ROI), Sessions
(deposit/cashout/net/running total), CSV export, `/healthz`.

## Key decisions & deviations (recorded in DEPLOY.md §3)

- **`import_ref`** (unique, nullable; migration `0002`) on bonus/hunt — stable source
  identity for idempotent import as a *union, not dedup*.
- **`bonus.played_on` relaxed to nullable** (migration `0003`) — hunt tabs and notable
  sheet carry no per-bonus date (~647 null rows). Downgrade is destructive-capable.
- **No auth by design** — network position only; forward-auth planned at the reverse
  proxy (compose label commented out). Do not add header-trust logic in-app.
- Alias correction on entry is driven by the DB `game_alias` table (seeded from the
  brief's 38-entry map).

## Validated import result (vs DEPLOY step 7)

13,121 bonuses, 27 hunts, 5 date-suspect, 24 notable — all match. **Games 624 vs
expected 572** — the brief's alias map only cleaned the main log; hunt/notable sheets add
uncovered spelling variants. Mean X ≈ 118 (main-log-only ≈ 116, matching the sheet).

## Known gaps / open items

- **CI** result to confirm.
- **Games 624→572**: extend `app/importer/aliases.py` after cross-checking
  `Slots_rebuilt.xlsx`.
- `game.provider` column exists but **is never populated** (no provider data in source).
- ~~Bonuses are add-only~~ — **done in v0.2.0**: edit/delete UI on the Log.
- ~~Sessions aren't linked to bonuses~~ — **done in v0.2.0**: session detail page attaches
  bonuses by date window (reconcile model) and shows per-session net + bonus winnings. Hunt↔session
  rollup still deferred. Deeper base-game stake inference needs a per-bonus buy-cost column not yet
  captured.
- In-app **game merge / alias management** shipped in v0.2.0 (Games page). It fixes live data and
  entry-form correction but not the importer's own `ALIAS_MAP` — see DEPLOY.md §3.
- Cosmetic: starlette `httpx`/`httpx2` TestClient deprecation warning.
- Deployment runbook (secrets, image publish and visibility, stack creation, backups,
  monitoring, dependency-update scope) — environment-specific operator tasks.

## Enhancement candidates to discuss

**Data / P&L**
- Wire **sessions ↔ bonuses/hunts** (attach entries to an open session; true profit/loss
  — the thing the spreadsheet never tracked).
- Populate `game.provider` (manual tagging UI, or a provider lookup) → provider
  breakdowns on the dashboard.

**Entry & correctness**
- Edit/delete bonuses; in-app **game merge / alias management** (fixes the 624 drift
  permanently and stops future variants).
- Notable / replay-URL management surface.

**Reporting**
- ~~Richer dashboard, dashboard SQL push-down, hunt/session export~~ — **done in
  v0.4.0.** Remaining reporting ideas: provider cross-tabs (needs `game.provider`
  populated first) and per-game bought/natural splits.

**Shipped in v0.4.0**
- Hunt edit / reopen / delete (delete detaches bonuses), real validation errors on the
  hunt entry form, and form parity with the main one. Closing a hunt is no longer a
  one-way door.
- `/export` honours the log's filters via shared `LogFilters` + `log_conditions`;
  added `/export/hunts` and `/export/sessions`.
- `/games/merges` — guided duplicate detection (difflib, two confidence tiers) with a
  sequel guard so numbered entries in a series are never suggested. This is the tool
  for finally closing the game-count drift; the cleanup itself is an operator pass.
- **Bonus cost tracking** (migration `0005`): `cost`, three-state `bought`, and
  generated `cost_multiplier`. Log columns + provenance filter, export columns, and a
  bought/natural/unknown split on the dashboard.
- Dashboard aggregates moved into SQL, plus date-range filter and monthly trend.

**Still open / notable gaps**
- `game.provider` remains unpopulated — blocks provider breakdowns.
- Hunt↔session linking still has no UI (`hunt.session_id` exists).
- Base-game stake inference: `bonus.cost` covers bonus *buys*, but the spend between
  natural triggers is still only visible at session level.
- The pre-existing `bonus.multiplier` generated column shares the SQLite
  integer-division quirk documented on `cost_multiplier`. Harmless in production
  (PostgreSQL is exact); left alone because altering a generated column means
  dropping and re-adding it.

**Shipped in v0.3.0**
- Click-to-sort on every table column (both directions) via `app/services/sorting.py`
  plus the `sortable` macro in `app/templates/_macros.html`. Whitelisted keys, nulls
  last, stable `id` tiebreaker so offset paging can't repeat rows.
- Log: notes column, notes-aware search, `notable` / `has_replay` / `suspect` filters,
  and a summary line aggregating the whole filtered set.
- Games: search, sort, pagination, and a per-game detail page at `/games/{id}`. Now
  outer-joined, so games with zero bonuses (seeded alias targets) are no longer hidden.

**Platform**
- Forward-auth cutover when that middleware exists — app needs only a proxy label, no code.

**Nice-to-haves**
- Alias-gap backfill/repair tooling; a `--dry-run` import mode; import-summary diff
  against `Slots_rebuilt.xlsx`.

## Constraints the planning chat must respect (non-negotiable)

No auth/user model in-app · listen `0.0.0.0:8000` · `/healthz` DB-free · all config from
env, no baked secret defaults · Decimal for money/multipliers · `bonus.multiplier` /
`session.net` are generated columns (never write) · `replicas: 1`, no locking · never
`:latest` · vendor static assets · migrations via Alembic (CI asserts from-empty apply) ·
TZ America/Chicago.
