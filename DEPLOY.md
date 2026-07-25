# Deploying slot-tracker

What the application requires of its environment, and the traps worth knowing before you run it.
Application design is out of scope here — see [`docs/build-brief.md`](docs/build-brief.md).

> [!IMPORTANT]
> **The app has no authentication.** Access control is network position. Run it on a private network
> (LAN, VPN) or behind an authenticating reverse proxy. Never expose it directly to the internet.

## What the app expects

| | |
|---|---|
| **Listen address** | `0.0.0.0:8000`, fixed. No published host port needed if a proxy shares its network. |
| **Database** | PostgreSQL 18, reachable via `DATABASE_URL`. A dedicated instance is recommended. |
| **Config** | Environment variables only — see the table in [`README.md`](README.md). |
| **Health check** | `GET /healthz`, 200 with no database dependency. |
| **User** | Runs as UID/GID 1000, non-root. Writes nothing outside `/tmp`. |
| **State** | Stateless. Everything persistent lives in PostgreSQL. |
| **Migrations** | Run at startup by the entrypoint when `RUN_MIGRATIONS_ON_STARTUP=true`. |
| **Platform** | `linux/amd64`. |

[`deploy/compose.yaml`](deploy/compose.yaml) is a working Docker Swarm stack you can adapt — app,
PostgreSQL, an internal overlay network, and reverse-proxy labels.

## Single replica, stop-first

**Deploy at one replica with stop-first updates.** Migrations run from the entrypoint before the app
serves traffic, and the app carries no locking to coordinate concurrent migrations — it doesn't need
any, provided the old task stops before the new one starts. Raising the replica count means two
instances could migrate the same database simultaneously.

## Health checks without curl

The runtime image is slim and contains **no `curl` and no `wget`**. A health check that assumes
either will fail. Use something already present — Python's standard library, for example:

```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)\""]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 45s
```

## Secrets

Only two values are secret: `DATABASE_URL`'s password and `SECRET_KEY`. Generate both with
`openssl rand -hex 32`.

**Use hex, not base64.** `DATABASE_URL` is parsed as a URL, and base64 output contains `/`, `+`, and
`=`, which break URL-form connection strings. This failure looks like an authentication error and
wastes an afternoon.

Assemble `DATABASE_URL` in your deployment configuration from the password variable rather than
storing the whole connection string as a secret — only the password is sensitive; host, port, user,
and database name are ordinary config and benefit from being version-controlled.

### Rotating the database password

`POSTGRES_PASSWORD` is **only read when the cluster is initialized.** Changing it later does nothing
to an existing database — the app simply starts failing authentication. To rotate:

```bash
docker exec -it <postgres-container> \
  psql -U <user> -d <dbname> \
  -c "ALTER USER <user> WITH PASSWORD 'newvalue';"
```

…then update the secret and redeploy. Alternatively, wipe and re-import — cheap here, because the
importer is idempotent.

## PostgreSQL storage

### The PG18 volume path trap

From PostgreSQL 18, the official image sets `PGDATA=/var/lib/postgresql/18/docker` and declares its
volume at **`/var/lib/postgresql`**, not `/var/lib/postgresql/data`. Mount the parent. Mounting the
old path silently produces a broken or empty cluster — the app comes up healthy against nothing.

### Local volume vs. network storage

Both work; the trade-off is worth making deliberately.

**A local volume** is the safer default for PostgreSQL, but on a multi-node cluster it pins the
database to one node. If you use one, **also pin the service to that node.** A named local volume
without a placement constraint is the worst case: the scheduler moves PostgreSQL to another node,
creates a fresh empty volume there, and the app comes up healthy against an empty database — silent
data loss with no error.

**Network storage (NFS)** makes the volume portable across nodes, at the cost of two hazards:

- **Split-brain.** Two postmasters against one data directory corrupts it. Single replica with
  stop-first updates covers the normal update path; the residual risk is a node partition, where the
  scheduler may start a replacement while the original is unreachable but still running. Pinning the
  service to one node eliminates this entirely, if you can accept manual failover.
- **fsync durability.** `fsync()` over NFS is only as safe as the export. Use a synchronous export
  and a `hard` client mount; an `async` export can acknowledge writes that aren't durable.

If PostgreSQL runs against network storage, it will likely need to run as the UID owning the share
(`user: "1000:1000"`), and that directory must exist and be owned correctly **before** first start.

Sizing is not a concern: a database of ~13,000 bonuses plus indexes is well under 100 MB.

## Backups

Two layers, because they fail differently:

- **Logical dumps** (`pg_dump`, or any scheduled backup tool) — the primary recovery path, and the
  only one that survives volume corruption.
- **Volume or VM snapshots** — fast whole-cluster restore. Make sure your snapshot actually covers
  wherever the data directory lives; moving PostgreSQL from a local volume to network storage moves
  it out of a host-level snapshot's scope.

Verify a restore before trusting either. For hand-entered data, the realistic loss window is
whatever has been typed since the last dump.

## Building and publishing the image

- Built by GitHub Actions on `v*` tags; CI runs lint, tests, a from-empty migration check, and a
  no-push image build on every pull request.
- Tags are full semantic versions plus `X.Y` and the short SHA. **Never `:latest`** — every consumer
  pins an exact version, so a rollback is a pin change rather than a registry race.
- `linux/amd64` only. Add other platforms only if you actually run them; QEMU-emulated builds are slow.
- Build provenance and an SBOM are attested and pushed alongside the image.
- **Registry visibility.** A public image needs no credentials anywhere. A private one needs
  authentication on every node that pulls — see below.

### Pulling from a private registry

Keeping the image private is the right default for a personal deployment; it costs one piece of
setup. Note that **repository visibility and package visibility are separate settings** — a private
source repository does not make its published packages private, or vice versa.

1. **Create a read-only token.** For GitHub Container Registry, a personal access token with
   **`read:packages`** scope and nothing else. Treat it as a credential: store it in your secret
   manager, and pass it via `--password-stdin` rather than as a command-line argument so it stays out
   of shell history.

2. **Give the cluster the credential.** Either configure a registry account in your deployment
   tooling — preferable, since it re-authenticates on every deploy — or authenticate on the manager
   and distribute it with the stack:

   ```bash
   docker login ghcr.io -u <username> --password-stdin
   docker stack deploy -c compose.yaml <stack-name> --with-registry-auth
   ```

   **`--with-registry-auth` is the part that matters.** It encrypts the manager's credential and
   pushes it to every node. Without it, workers still cannot pull and tasks fail with
   `No such image` — which is misleading, since the image exists and the real cause is authorization.

3. **Plan for expiry.** The credential is stored with the service. When the token expires or is
   rotated, subsequent pulls fail — including reschedules that would otherwise be automatic. Re-run
   the login and redeploy with `--with-registry-auth` to refresh it. Prefer a long-lived token, or
   registry-account support in your deployment tool, so this isn't a surprise months later.

Dependency-update tooling that watches your own image tags also needs `read:packages`, or it silently
stops detecting new versions.

## Deploy and rollback

Deploying is a pin change: tag a version, let the image publish, then update the image reference in
your stack definition and apply it.

**Rollback** is reverting the pin. If a migration has already altered the schema, revert the image
**and** restore the most recent dump — Alembic downgrades are not guaranteed to be written, and one
is explicitly destructive (see below). Any destructive migration must say so in its docstring and its
commit message.

## Schema notes — deviations from the build brief

Three deliberate, data-driven changes beyond the schema in `docs/build-brief.md`. Recorded here
because dumps are the recovery path and these affect restores.

**`bonus.import_ref` / `hunt.import_ref`** (nullable, `UNIQUE`, migration `0002`). Each imported
source row gets a stable, non-content identity (`main:<row>`, `hunt:<n>:<row>`, `notable:<row>`) so
the importer is idempotent while still importing the log and hunt tabs as a **union**. A content key
can't serve this purpose: the source contains coincidental `(game, date, bet, win)` collisions that
must be preserved as distinct rows. App-entered rows leave it `NULL` (`UNIQUE` permits many NULLs in
PostgreSQL). Additive and reversible.

**`bonus.played_on` relaxed to nullable** (migration `0003`). The brief declared it `NOT NULL`, but
the hunt tabs and the notable-hits sheet carry **no per-bonus date** — only the main log does, so
roughly 647 rows import without one. App-entered bonuses always set it. **The downgrade re-adds
`NOT NULL` and will fail while null-dated rows exist** — rollback here is image-revert plus a dump
restore, not an Alembic downgrade.

**`bonus_session_idx`** (partial index, migration `0004`). Indexes `bonus(session_id) WHERE
session_id IS NOT NULL` for the per-session P&L query, mirroring `bonus_hunt_idx`. Additive and
reversible.

**`bonus.cost` / `bonus.bought` / `bonus.cost_multiplier`** (migration `0005`). Records what a bonus
cost to trigger, not just what it paid. `cost` is the buy price, independent of `bet`. **`bought` is
nullable on purpose** — three states, where `NULL` means "unknown", the honest value for every row
imported from the original data set; only the application ever writes `true`/`false`. Defaulting
existing rows to `false` would assert something untrue about them, the same reasoning that made
`played_on` nullable. `cost_multiplier` is generated as `win * 1.0 / NULLIF(cost, 0)`; the `* 1.0` is
load-bearing, because SQLite (the test database) performs integer division on whole numbers and would
otherwise disagree with PostgreSQL. Additive and fully reversible.

## First-run checklist

1. **Secrets** — generate the database password and `SECRET_KEY` (hex), and make them available to
   the stack.
2. **Storage** — decide local volume vs. network storage, create the data directory with correct
   ownership if required, and mount at `/var/lib/postgresql` (not `.../data`).
3. **Image** — tag a release, confirm the image published, and make sure every node can pull it.
4. **Deploy** — apply the stack. Confirm PostgreSQL reports ready and the app logs
   `Running upgrade` followed by a successful startup.
5. **Verify** — `GET /healthz` returns 200 and the app answers over your proxy.
6. **Backups** — configure dumps *and* verify a restore before entering data you can't retype.
7. **Confirm a redeploy preserves data** — pull a new image and check the database survives. This is
   the step that catches a misconfigured volume path or ownership, and it is much cheaper to discover
   now than after a month of entries.

## Deliberate non-goals

- No in-application authentication.
- No `:latest` tag anywhere, including first-party images.
- No multi-architecture builds.
- No CI-driven deployment — CI publishes an image; deployment is a separate, explicit action.
- No automatic image updating. Version pins move by an intentional commit.
