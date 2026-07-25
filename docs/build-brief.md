# Slot Tracker — build brief

Handoff for continuing this build. Everything below was derived from
`Slots.ods` (a 30-sheet LibreOffice workbook, Dec 2021 – Jul 2026). Re-upload `Slots.ods` in the
project chat alongside this file — the importer needs the real thing.

---

## Decisions already made

| | |
|---|---|
| **Scope** | Full replacement for the spreadsheet — bonus entry, hunt mode, session tracking, stats |
| **Storage** | Postgres (chosen so the volume can live on network storage without SQLite's NFS locking problems) |
| **Deploy** | Docker, self-hosted on a private network |
| **Suggested stack** | FastAPI + SQLAlchemy + Alembic, server-rendered Jinja templates with HTMX. No JS build step, small image, works well on a phone during actual play. Not binding — swap if the project's conventions say otherwise. |

---

## What the source data actually looks like

Facts worth knowing before designing anything:

- **12,472 bonus records** in the main `Slot Bonuses` sheet: game, date, bet, win, X (a formula, `win/bet`), free-text notes.
- **623 more bonus records** spread across 27 separate `Bonus Hunt N` tabs, same columns plus per-hunt start/end balances.
- **These two sets are disjoint.** Only 63 of 623 hunt rows match a main-log row on (game, bet, win), which is coincidence at this volume. Import is a union, not a dedup — expect **~13,095 bonus rows**.
- **572 distinct games** after cleanup (613 raw spellings; see alias map below).
- **Bet sizes** cluster hard: 5,817 at $0.10 and 5,217 at $0.20 account for 88% of all records. Long tail out to $20.
- **X distribution:** median 48x, mean 116x. 13% pay under 10x, 1.3% pay over 1000x. Max recorded 12,625x.
- **24 notable hits** on their own sheet, each with a replay URL. 177 more replay URLs are embedded as hyperlinks in the main log.
- **No spend is recorded anywhere except hunt start/end balances.** The workbook tracks what bonuses paid, never what was staked to reach them, so profit is not derivable from it. The app should fix this at the source — hence the sessions table.

### Data quality issues to handle on import

- Five rows dated 2002 / 2011 / 2012 are almost certainly typos. Flag, don't silently correct.
- The hunt tabs drifted over time: hunts 24–27 stopped computing X, hunt 25 has no start balance, hunts 24–26 have no end balance.
- **The `End` column means two different things.** Most tabs look like *balance after every bonus was opened*; hunt 27 explicitly says `Spin end` (balance at the moment hunting stopped, before opening). This must be modeled per-hunt, not assumed — hence `end_convention` on the hunt table.

---

## Proposed schema

```sql
CREATE TABLE session (
    id          SERIAL PRIMARY KEY,
    site        TEXT,
    started_at  TIMESTAMPTZ,
    ended_at    TIMESTAMPTZ,
    deposit     NUMERIC(12,2),
    cashout     NUMERIC(12,2),
    net         NUMERIC(12,2) GENERATED ALWAYS AS
                    (COALESCE(cashout,0) - COALESCE(deposit,0)) STORED,
    notes       TEXT
);

CREATE TABLE game (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    provider    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Drives both import normalization and typo-correction in the entry form.
CREATE TABLE game_alias (
    alias    TEXT PRIMARY KEY,
    game_id  INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE
);

CREATE TABLE hunt (
    id              SERIAL PRIMARY KEY,
    label           TEXT,
    hunt_date       DATE,
    start_balance   NUMERIC(12,2),
    end_balance     NUMERIC(12,2),
    end_convention  TEXT NOT NULL DEFAULT 'after_opening'
                        CHECK (end_convention IN ('after_opening','spin_end')),
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','closed')),
    session_id      INTEGER REFERENCES session(id) ON DELETE SET NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One table for everything. hunt_id NULL = an ordinary logged bonus.
CREATE TABLE bonus (
    id            BIGSERIAL PRIMARY KEY,
    game_id       INTEGER NOT NULL REFERENCES game(id),
    played_on     DATE NOT NULL,
    bet           NUMERIC(10,4) NOT NULL CHECK (bet > 0),
    win           NUMERIC(12,2) NOT NULL CHECK (win >= 0),
    multiplier    NUMERIC(14,4) GENERATED ALWAYS AS (win / bet) STORED,
    notes         TEXT,
    replay_url    TEXT,
    notable       BOOLEAN NOT NULL DEFAULT false,
    hunt_id       INTEGER REFERENCES hunt(id) ON DELETE SET NULL,
    session_id    INTEGER REFERENCES session(id) ON DELETE SET NULL,
    date_suspect  BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX bonus_game_idx       ON bonus (game_id);
CREATE INDEX bonus_played_on_idx  ON bonus (played_on DESC);
CREATE INDEX bonus_hunt_idx       ON bonus (hunt_id) WHERE hunt_id IS NOT NULL;
CREATE INDEX bonus_multiplier_idx ON bonus (multiplier DESC);
```

Notes on the modeling:

- `multiplier` is a generated column so X can never drift from bet/win the way it did in the later hunt tabs.
- `notable` is a flag rather than a separate table — the notable-hits sheet is just a filtered view.
- `session_id` on both `bonus` and `hunt` is what eventually makes real P/L possible. Nullable, because all 13,095 historical rows import without one.

### Derived hunt result

```
cost = CASE end_convention
         WHEN 'spin_end'       THEN start_balance - end_balance
         ELSE                       start_balance
       END

net  = CASE end_convention
         WHEN 'spin_end'       THEN total_bonus_win - cost
         ELSE                       end_balance - start_balance
       END
```

Under this, the 24 hunts with complete figures come to roughly **$7,737 staked, net −$26**. Treat as
soft until the conventions are confirmed per hunt.

---

## Alias map for import

38 spellings collapse into canonical names. Sequels stay distinct — `Money Train 2/3/4`,
`Punk Rocker 2/3`, `Chaos Crew 2/3`, `Big Bass` vs `Bigger Bass` are all separate games.

```
:egacy of Dead                       -> Legacy of Dead
Boodthirst                           -> Bloodthirst
Choas Crew                           -> Chaos Crew
Chaos Crew II                        -> Chaos Crew 2
Hanf of Anubus                       -> Hand of Anubus
Hand of  Anubus                      -> Hand of Anubus
Hand of Anubis                       -> Hand of Anubus
Frutz                                -> Fruitz
Fruit Dual                           -> Fruit Duel
Myster Motel                         -> Mystery Motel
True Grit Recepmtion                 -> True Grit Redemption
San Quinin Death Row                 -> San Quentin Death Row
San Quintin Manhunt                  -> San Quentin Manhunt
Sugar RUsh                           -> Sugar Rush
Money train 2                        -> Money Train 2
Stack'Em                             -> Stack'em
Rip City                             -> RIP City
Frkn Bananas                         -> FRKN Bananas
Le Pharoh                            -> Le Pharaoh
Denscho                              -> Densho
Warrior's Way                        -> Warrior Ways
Outlaws Inc                          -> Outlaws Inc.
Outlaw Inc.                          -> Outlaws Inc.
xWays Hoarder II                     -> xWays Hoarder 2
Pray For Six                         -> Pray for Six
Hop'n'Pop                            -> Hop 'n' Pop
Cursed Sea                           -> Cursed Seas
Drac Stacks                          -> Drac's Stacks
Rich Wilde and the Book of the Dead  -> Rich Wilde and the Book of Dead
Rich Wilde Tomb of Madness           -> Rich Wilde and the Tome of Madness
Rich Wilde's Tome of Madness         -> Rich Wilde and the Tome of Madness
Punk Rockers 3                       -> Punk Rocker 3
Das xBoot                            -> Das Boot
Das X Boot                           -> Das Boot
Le Bandit – Miami Hustle             -> Le Bandit Miami Hustle
Dog House - Dog or Alive             -> Dog House Dog or Alive
Wanted Dead or a Wild                -> Wanted Dead or Wild
Wanted Dead of a Wild                -> Wanted Dead or Wild
```

Two judgement calls to confirm or reverse:

- `Denscho` (53 rows) → `Densho` (25 rows). Canonicalized to the *correct* title even though the
  misspelling was more common.
- `Wanted Dead or a Wild` (60) folded into `Wanted Dead or Wild` (1,039). The former is the real
  title; the latter is the established habit. Kept the habit.

Seed `game_alias` with all of these so the entry form auto-corrects on the way in and the problem
stops recurring.

---

## Importer requirements

Read `Slots.ods` directly — `pandas.read_excel(..., engine="odf")` handles the sheets, but embedded
hyperlinks need `odfpy` to walk the XML (`odf.text.A` elements carry the `href`). Note odfpy
normalizes `https://` to `https:/`; repair with a regex.

Order of operations:

1. Distinct canonical names → `game`; the map above → `game_alias`.
2. `Slot Bonuses` → `bonus` with `hunt_id = NULL`. Trim whitespace, apply aliases, set
   `date_suspect = true` where year < 2021, attach the 177 replay URLs from column G.
3. Each `Bonus Hunt N` tab → one `hunt` row + its bonuses with `hunt_id` set. Parse start/end by
   scanning for the literal labels, and set `end_convention = 'spin_end'` for hunt 27 only.
4. `Notable hits` → set `notable = true` on matching bonuses where one can be found; otherwise
   insert standalone rows with `notable = true` and the replay URL.
5. Idempotent — safe to re-run against a fresh volume.

---

## App surface for v1

- **Dashboard** — headline counts, total bonus winnings, mean/median X, X-distribution bands, by-year and by-bet-size breakdowns.
- **Add bonus** — the hot path. Game autocomplete backed by `game` + `game_alias`, bet defaulting to last used, X shown live as you type the win. Should be usable one-handed on a phone.
- **Log** — searchable, filterable by game / date range / bet / X band.
- **Game stats** — count, total win, mean/best/worst X, first and last played, per game.
- **Hunt mode** — open a hunt with a start balance, add bonuses to it as they're opened, close with an end balance and a convention, see cost / net / ROI.
- **Sessions** — deposit, cashout, net, running total. The only place real profit or loss ever comes from.
- **Export** — CSV of the bonus log, so the data is never trapped in the container.

Operational: non-root user, `/healthz`, config from env, multi-arch build, Alembic migrations run on
startup or as a one-shot.

---

## Open questions that need deployment context

These are why the build belongs in the project rather than here:

1. Ingress — reverse proxy in use, TLS termination, hostname.
2. Swarm stack file vs plain Compose, and how Postgres is provisioned (existing shared instance vs a dedicated one for this app).
3. Where the Postgres volume lives, and what the backup story is.
4. Secrets — how `DATABASE_URL` and friends get injected.
5. Auth — whether the app is reachable only over the private network, or needs its own login.
6. Registry and CI — where the image gets built and pushed.

---

## Attach to the project chat

- `Slots.ods` — the original, needed by the importer
- `Slots_rebuilt.xlsx` — the cleaned rebuild, useful as a reference for what the dashboard numbers should come out to
- this brief
