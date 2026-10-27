# 2. Reflection: what the USL would and would not do for this app

**Plainly first:** the app's agents still query the raw `NFLVERSE.*` tables. The
`nfl_usl` model in [03-nfl-usl.sql](03-nfl-usl.sql) is built and active on the cluster
next to the app. Nothing in `app/` reads it. There are three reasons:

- **Timing:** the app was built (22–26 October 2026) before we tried the USL.
- **Freeze:** the code was frozen at 6 PM on 26 October; the USL work was done after the
  freeze and is docs and cluster only.
- **Sample mode:** the no-credentials mode (Docker, CI, the judges' quick try) runs the
  same SQL on DuckDB over `data/sample/` Parquet files. DuckDB has no USL. Moving the app
  to the USL would also mean building a local mirror of the five USL tables.

Every number below comes from this repository or from the live results in this folder.

## 2a. Time saved compared with hand-coding

### One query, both ways

**Through the USL** ([04-usl-queries.md](04-usl-queries.md), query 3): Christian
Watson's week-7 opponent and his PPR points per game.
- **Size:** 10 lines of SQL with 2 joins, both on declared keys (`player.team` → `game`,
  `player.gsis_id` → `player_week.player_id`).
- **Result:** GB at DET, 6 games, 19.8 PPR points per game.

**Hand-coded in the app:** the same opponent lookup is part of `matchup_query()` in
`app/agents/factor_queries.py` (lines 807–857).
- **Size:** 51 lines of Python building one SQL string.
- **Structure:** 6 CTEs (`players`, `games`, `target`, `allowed`, `avg_allowed`,
  `ranked`) and 4 LEFT JOINs.
- **Home/away unpivot:** the `games` CTE alone is a `UNION ALL` of `schedules` to turn
  home and away into one `team → opponent` row.
- **Fairness:** the app query also ranks the opponent's points allowed to the position
  and adds the injury report. So the line counts are not like for like.

The honest reading of the comparison:

- **The query text is not much shorter.** Our USL query still needs the home/away
  `CASE` (`CASE WHEN g.home_team = p.team THEN g.away_team ...`). The USL declares
  *which* columns join; it does not write the analysis for you.
- **What the USL saves is the joins we had to rediscover.** `factor_queries.py` has:
  - 16 planned queries
  - 37 references to `NFLVERSE.*` tables
  - 23 joins (9 `JOIN`, 14 `LEFT JOIN`)

  Each join restates its key by hand. Some of those keys are names, not IDs (below).
- **The Spark/DuckDB gotchas cost real time.** Our queries have to run on both engines,
  so we hit SQL that DuckDB accepts and Spark rejects:
  - **ORDER BY an aggregate:** Spark rejected `ORDER BY SUM(targets)` when
    `SUM(targets) AS targets` was selected (live run `7bfa81c3abf1`, fixed in `04025e4`).
    DuckDB accepted it, so only the live run failed. The fix needed a regression test
    over every planned query (`tests/test_factor_queries.py`).
  - **Dialect bans:** no `ILIKE`, `QUALIFY`, `::` casts or double-quoted identifiers.
    These are written into the Analyst's SQL prompt (`app/agents/analyst.py`).
  - **The Spark sweep:** a 143-line script (`scripts/check_factor_queries_live.py`) runs
    all 278 distinct planned queries live to catch the next one.
  - **What a USL changes, and what it doesn't:** activation queries, rules and USL
    queries all run in one engine, Spark, so a USL-only app would not need the
    two-dialect discipline. But our sample mode is the reason that discipline exists, so
    the USL does not remove it for us.
- **Timing of the USL build itself:** under an hour. That covered reading Zetaris's
  examples, the first compile, two failed activations, a clean rebuild and two cluster
  outages (Thrift `TTransportException`, recorded in the results). We timed this only
  roughly.
- **Timing of the hand-coded SQL:** spread over 15 commits to `factor_queries.py` from
  22 to 26 October. Two of them fix data problems that only showed up in live runs:
  - `04025e4`: the Spark `ORDER BY` bug above
  - `322d9a9`: the name-suffix mismatch below

  We did not time those separately, so we give no hours figure for them.

## 2b. How the USL would help us, and where it would not

### What it would replace

1. **Declared keys instead of name-based joins.** This is the clearest win, and the bug
   is still in the frozen app:
   - **The join:** `snap_counts` has no GSIS ID. The Opportunity and Weekly opportunity
     queries join it to `player_stats` on `game_id`, `team` **and the player's name**.
   - **How much it loses** ([02-exploratory-queries.md](02-exploratory-queries.md),
     queries 13–15):
     - Of 2,354 skill-player snap rows, 1,955 match by name and 2,059 match by ID
       (`snap_counts.pfr_player_id` → `rosters.pfr_id` → `gsis_id`).
     - That is 104 rows lost. Examples: "Deebo Samuel" vs "Deebo Samuel Sr.", "Chris
       Godwin", "Brian Thomas", "D.K. Metcalf", "Michael Pittman Jr."
   - **Deebo Samuel:** his snap share is NULL in all five of his games when joined by
     name. By ID it is 42.0%, 60.0%, 76.0%, 67.0% and 43.0%. The current 49ers examples
     quote his target share (11.1%), and none of them quotes his snap share.
   - **Earlier symptom:** smoke run `eef583ef739b` found nobody for "Deebo Samuel". We
     fixed that in code (`NAME_SUFFIX`, `name_key()` and `same_player()` in
     `factor_queries.py`).
   - **With a USL:** a `snap_week` table whose activation maps `pfr_player_id` to
     `gsis_id` once, plus a foreign key to `player`, would make the join an ID join.
     `RUN DQ` would then count the snap rows with no player, instead of losing them
     silently.
2. **Data quality before the agents see the data.** `RUN DQ` checked each table's keys
   and rules in 2.7–44.6s ([03-nfl-usl-results.md](03-nfl-usl-results.md), steps 5–6),
   with no code of ours. They found two
   things the app had never checked:
   - **player_week:** 6 rows (one per week, weeks 1–6) with no `player_id` fail the
     player FK: 6,488 total, 6,482 valid.
   - **player:** 1 roster row with no `gsis_id` (Al-Jay Henderson, NYJ practice squad)
     fails `gsis_id_format`: 3,054 total, 3,053 valid.
   - **Clean rules:** the PKs, the other FKs, `target_share_range` and
     `report_status_known` found 0 invalid rows.

   These rows are harmless today, because every app query filters by a real player ID.
   A rule that runs before the agents would still turn "harmless by luck" into checked.
3. **One place for the meaning of each table.** The Analyst's SQL prompt embeds
   `app/agents/schema.md`, a hand-maintained file generated by
   `scripts/build_schema_doc.py`. It records grains, keys and caveats. For example:
   - snap_counts has no GSIS ID
   - shares are fractions 0–1
   - the current depth chart is `MAX(dt)`

   USL table and column descriptions could be that source instead, kept next to the keys
   they describe.
4. **Snapshot and "latest" logic in one place.** `depth_charts` holds 251 snapshots, so
   every query has to filter to the team's `MAX(dt)`; `rosters` and `injuries` use a
   latest `MAX(week)`. An activated `current_depth_chart` table would hold that filter
   once. The logic moves into the model; it does not disappear.

### Where it would not help

- **The model reasoning:** the planner, the factor agents and the verdict.
- **The Critic:** its timing check (did the rise start the week the teammate got hurt?),
  the direction and matchup-label checks, the stand-in rule and the number check work on
  query results and answer text, not on table design.
- **Names typed by users:** "CMC", "Bowers", "Justin Jeffersen" and "Deebo" vs "Deebo
  Samuel Sr." come from the question, not from a join. The nickname table, the
  last-name lookup and the closest-name suggestion stay in code.
- **Speed:** queries on the active USL tables took 3.0–7.0s, with one at 41.9s
  ([04](04-usl-queries.md)). Queries on the cached NFLVERSE tables took 0.7–3.2s, with
  one at 37.3s ([02](02-exploratory-queries.md)). The cluster was unstable during the
  runs, so this is not a clean benchmark. USL tables are not cached by
  `sql/nflverse_cache.sql`, and we have no storage target for `MATERIALIZE`.

### Estimated saving for a next version

This is an estimate, not a measurement:
- **Model:** about half a day to model the remaining two tables (`snap_week` with the
  pfr → gsis mapping, and `play` from pbp) and to point the 16 planned queries at the
  USL.
- **Sample mode:** another half day to build the DuckDB mirror for sample mode.
- **Saved:** the live-only debugging cycles above and the name-join bug class. We would expect to save more time than it costs from the second
  data refresh on, because DQ catches the bad rows before an agent quotes them.
- **Not saved:** the agent and Critic work, which was most of the project.

## 2c. A product requirement to make the USL stronger

### Requirement: an agent-safe USL read path (single statement, valid rows only, cached)

**User:** a developer building an AI agent on Zetaris. The agent writes or runs SQL one
statement at a time, and must never quote a row that fails a data-quality rule.

**Problem, from our build:**

1. **Valid rows need workarounds.** `RUN DQ` tells you that 6 `player_week` rows are
   invalid. It does not stop a query from returning them. To exclude them today, the
   agent's SQL has to re-implement the foreign key as a join
   ([04-usl-queries.md](04-usl-queries.md), query 5). The alternative is
   `MATERIALIZE ... Valid Records Only`, which needs a configured cloud storage target
   (we have none). Zetaris's own notes also say the SQL form of that option is
   unconfirmed (companion guide 8.5).
2. **USL tables are not cached.** Our USL queries took 3.0–7.0s, against 0.7–3.2s on the
   cached source tables. Each side had one outlier near 40s, on an unstable cluster. We
   found no cache option for an activated USL table.
3. **The multi-table COMPILE is not one statement.** It needs `;` between the
   `CREATE TABLE`s:
   - Our adapter's one-statement guard rejects it, as any safe agent runner would.
   - The SQL Workspace splits it.
   - We had to write [run_usl.py](run_usl.py) to send it as one request.
4. **Errors and docs that cost time:**
   - **Unactivated table:** `REGISTER DQ` on a table that is not yet activated failed
     with only the table name as the message: `{"msg":"metastore.nfl_usl_ns.nfl_usl.player"}`.
   - **Credit:** the `ACTIVATE` schema-mismatch error was excellent. It named the column
     ("nullable -> NOT NULL") and suggested the `COALESCE` fix.
   - **Quotes stored in descriptions:** `SET TABLE DESCRIPTION '...'` stored the quotes
     as part of the description. The unquoted form stored clean text.
   - **Docs mismatch:** `RUN DQ TABLE <t>` with no rule name ran every rule, although the
     reference says a rule name is required.
   - **Shared rule names:** rule names are column names, so `gsis_id` is both the
     `player` PK rule and the `injury_report` FK rule in `LIST DQ USL`. `REMOVE DQ`
     removes a rule "from every table in the USL".
   - **Two output shapes:** `SHOW DQ ALL INVALID` returns JSON in a `records` column,
     but `SHOW DQ INVALID RECORD` returns ordinary columns.

**Requirement:**

- **R1:** a query can read only the rows that pass every DQ rule on a USL table, in one
  `SELECT`, without materializing to external storage.
- **R2:** an activated USL table (or its valid-rows view) can be cached on the cluster,
  with a refresh trigger. Re-running `RUN DQ` refreshes it.
- **R3:** a multi-table `COMPILE USL` can be sent as one statement with no `;` inside
  it. Alternatively, the compile can take the JSON model that `LOAD USL` returns.
- **R4:** every DQ command error names the problem (for example "table player is not
  activated; run ACTIVATE USL TABLE first"), and rule names are unique per table, not
  per USL.

**Acceptance criteria (on `nfl_usl`):**

- **Valid rows:** `SELECT COUNT(*) FROM ...player_week VALID` returns 6,482, while the
  plain `SELECT COUNT(*)` still returns 6,488.
- **Caching:** after `CACHE`, the week-7 opponent query (04, query 3) runs in under 2s.
- **Compile:** `run_sql()`'s one-statement guard accepts the whole compile from
  `03-nfl-usl.sql`.
- **Errors:** `REGISTER DQ` before `ACTIVATE` returns an error that says the table is not
  activated.

**Bonus: mock DDL for the proposal** (not valid Zetaris SQL today):

```sql
-- R3: one statement, no inner semicolons: tables as a comma-separated list
COMPILE USL nfl_usl DEPLOY NAMESPACE lightning.metastore.nfl_usl_ns DDL (
    TABLE team (team varchar(3) NOT NULL PRIMARY KEY),
    TABLE player (gsis_id varchar(40) NOT NULL PRIMARY KEY,
                  team varchar(3) NOT NULL FOREIGN KEY REFERENCES team(team))
);

-- R1 + R2: a read policy on the table: queries see valid rows, served from a cache
ALTER USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
    SET READ POLICY VALID_RECORDS_ONLY
    CACHE REFRESH ON RUN DQ;

-- R1 per query, without changing the table's policy
SELECT player_id, week, fantasy_points_ppr
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week VALID;   -- 6,482 rows

-- R4: when the rules last ran and what they found, for an agent to check before answering
SHOW DQ STATUS TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week;
--  rule        | last_run            | total | valid | invalid
--  player_id   | 2026-10-27 00:17:xx | 6488  | 6482  | 6
```

**Why it matters for agents:** a "semantic layer" is most valuable to an LLM agent when
it is also the *safe* layer. The agent should be able to trust that every row it reads
has already passed the model's keys and rules, without knowing the rules itself. Today
the USL can say which rows are bad; this requirement lets it keep them out of the
agent's answers.
