# Zetaris Unified Semantic Layer (USL): `nfl_usl`

This folder is a five-table USL model over our seven NFLVERSE tables. It is built and
active on the Zetaris cluster, at `lightning.metastore.nfl_usl_ns.nfl_usl`, and follows
Zetaris's own examples in
[zetaris/getting-started](https://github.com/zetaris/getting-started)
(`open_data/usl/sql/01_*.sql`, `02_sic_edgar_usl_*.sql`, and section 8 of the SQL
companion guide).

**The USL is built alongside the app.** The app's agents still query the `NFLVERSE`
tables directly, and no app code changed for this work. The reasons are in
[05-reflection.md](05-reflection.md).

| File | Criterion | What it is |
|---|---|---|
| [01-use-case-and-sources.md](01-use-case-and-sources.md) | 1a | The use case and the 7 sources: contents, grain, keys, and which agent factor uses each |
| [02-exploratory-queries.sql](02-exploratory-queries.sql) / [results](02-exploratory-queries.md) | 1b | 31 live queries: a row count, a sample row and 2–3 exploratory queries per table |
| [03-nfl-usl.sql](03-nfl-usl.sql) / [results](03-nfl-usl-results.md) | 1c | The lifecycle: namespace, `COMPILE USL` (5 tables, PKs, 6 FKs), descriptions, `ACTIVATE`, 3 custom DQ rules, `RUN DQ`, `SHOW DQ` |
| [04-usl-queries.sql](04-usl-queries.sql) / [results](04-usl-queries.md) | 1c | 5 live queries that read only the USL: row counts, player_week → player → game, the week-7 opponent, an injury_report join, the FK check |
| [05-reflection.md](05-reflection.md) | 2a–2c | Time saved, how the USL would and wouldn't help us, and a product requirement with mock DDL |
| [run_usl.py](run_usl.py) | | The one-off runner that ran every `.sql` file live and wrote the results |

**Model.**

| Table | Primary key | Foreign keys | Source table |
|---|---|---|---|
| `team` | `team` | none | `schedules` |
| `player` | `gsis_id` | `team` → `team` | `rosters` |
| `game` | `game_id` | `home_team` → `team`, `away_team` → `team` | `schedules` |
| `player_week` | `player_game_id` | `player_id` → `player`, `game_id` → `game` | `player_stats` |
| `injury_report` | `injury_id` | `gsis_id` → `player` | `injuries` |

**Data-quality results** (live, `RUN DQ TABLE`):

| Table | Rows | Rules that found invalid rows |
|---|---|---|
| `player_week` | 6,488 | FK `player_id`: 6 rows with no player ID (6,482 valid) |
| `player` | 3,054 | Custom `gsis_id_format`: 1 roster row with no GSIS ID (3,053 valid) |

Every other PK, FK and custom rule passed with 0 invalid rows: `target_share_range`,
`report_status_known`, and the keys of `game` and `injury_report`.

**How the multi-table compile was run.** The app's `run_sql()` accepts one statement
per call, and a multi-table `COMPILE USL` needs `;` between its `CREATE TABLE`s.
`run_usl.py` therefore sends the whole compile as one request through the same Zetaris
UI-proxy route and settings as the app, using the adapter's internal `_run_live()`.
That worked on the first try. Tables were not compiled one at a time, and no FK had to
be replaced by a DQ rule.

**What was changed on the cluster.** Only the new namespace
`lightning.metastore.nfl_usl_ns` and the `nfl_usl` model in it. `ACTIVATE` only reads
the `NFLVERSE` tables, and none of them was changed. `MATERIALIZE` was not run, because
no storage target is configured.

**Rerun everything:**

```bash
.venv/Scripts/python docs/zetaris-usl/run_usl.py docs/zetaris-usl/02-exploratory-queries.sql --out docs/zetaris-usl/02-exploratory-queries.md
# 03 creates the model; to rebuild it, first run the REMOVE USL line in the file's teardown block
.venv/Scripts/python docs/zetaris-usl/run_usl.py docs/zetaris-usl/03-nfl-usl.sql --out docs/zetaris-usl/03-nfl-usl-results.md
.venv/Scripts/python docs/zetaris-usl/run_usl.py docs/zetaris-usl/04-usl-queries.sql --out docs/zetaris-usl/04-usl-queries.md
```

`run_usl.py` uses the live settings in `.env` (`SAMPLE_MODE=false`). It never uses
cached results, and it removes the cluster URL and credentials from any error it
writes. One cluster outage (Thrift `TTransportException`) interrupted the 03 run after
statement 24; statements 25–28 were rerun with `--from 25`, and the results file
records both runs.
