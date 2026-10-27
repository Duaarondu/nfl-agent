-- =============================================================================
-- USL: nfl_usl -- a five-table Unified Semantic Layer model over the NFLVERSE
-- filestore tables (criterion 1c). Built alongside the app: the app's agents
-- still query NFLVERSE.* directly (see 05-reflection.md), and nothing here
-- changes an NFLVERSE table -- ACTIVATE only reads them.
--
-- Follows Zetaris's own examples in github.com/zetaris/getting-started:
-- open_data/usl/sql/01_sic_usl_create.sql, 02_sic_edgar_usl_create.sql and
-- docs/guides/zetaris-lightning-sql-companion.md section 8.
--
-- Run with: .venv/Scripts/python docs/zetaris-usl/run_usl.py
--   docs/zetaris-usl/03-nfl-usl.sql --out docs/zetaris-usl/03-nfl-usl-results.md
-- run_usl.py sends the multi-table COMPILE USL as ONE request (run_sql in the
-- app rejects more than one statement, and the SQL Workspace splits at ";").
--
-- Model (one season, 2026):
--   team          (team PK)
--   player        (gsis_id PK, team FK -> team)
--   game          (game_id PK, home_team FK -> team, away_team FK -> team)
--   player_week   (player_game_id PK, player_id FK -> player, game_id FK -> game)
--   injury_report (injury_id PK, gsis_id FK -> player)
-- =============================================================================

-- Step 0: the namespace. The parent lightning.metastore must exist first (companion guide section 8.4).
CREATE NAMESPACE IF NOT EXISTS lightning.metastore;

-- Step 0: the namespace for this model.
CREATE NAMESPACE IF NOT EXISTS lightning.metastore.nfl_usl_ns;

-- Step 1: design and deploy the model: five tables, their primary keys and six foreign keys, in one COMPILE USL statement.
COMPILE USL IF NOT EXISTS nfl_usl DEPLOY NAMESPACE lightning.metastore.nfl_usl_ns DDL
CREATE TABLE team (
    team varchar(3) NOT NULL PRIMARY KEY,
    games_scheduled int
);
CREATE TABLE player (
    gsis_id varchar(40) NOT NULL PRIMARY KEY,
    full_name varchar(100),
    position varchar(5),
    team varchar(3) NOT NULL FOREIGN KEY REFERENCES team(team),
    roster_status varchar(5)
);
CREATE TABLE game (
    game_id varchar(20) NOT NULL PRIMARY KEY,
    season int,
    week int,
    game_type varchar(4),
    home_team varchar(3) NOT NULL FOREIGN KEY REFERENCES team(team),
    away_team varchar(3) NOT NULL FOREIGN KEY REFERENCES team(team),
    home_score int,
    away_score int
);
CREATE TABLE player_week (
    player_game_id varchar(64) NOT NULL PRIMARY KEY,
    player_id varchar(40) NOT NULL FOREIGN KEY REFERENCES player(gsis_id),
    game_id varchar(20) NOT NULL FOREIGN KEY REFERENCES game(game_id),
    week int,
    targets int,
    carries int,
    target_share double,
    fantasy_points_ppr double
);
CREATE TABLE injury_report (
    injury_id varchar(64) NOT NULL PRIMARY KEY,
    gsis_id varchar(40) NOT NULL FOREIGN KEY REFERENCES player(gsis_id),
    week int,
    team varchar(3),
    report_status varchar(20),
    report_primary_injury varchar(100)
);

-- Step 2: document the model.
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl SET DESCRIPTION NFL fantasy semantic model over the NFLVERSE tables (nflverse, CC-BY 4.0), 2026 season: teams, players, games, player-game stats and the weekly injury report, with declared keys and foreign keys. Built alongside the NFL Fantasy Agent. The app still queries NFLVERSE directly.;

-- Step 2: document the team table.
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.team SET TABLE DESCRIPTION One row per NFL team code (SF, GB, ...), from NFLVERSE.schedules home and away teams, with the number of scheduled games.;

-- Step 2: document the player table.
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.player SET TABLE DESCRIPTION One row per player, from NFLVERSE.rosters (the latest week each player was rostered). gsis_id is the GSIS player ID shared by player_stats, pbp, injuries and depth_charts.;

-- Step 2: document the game table.
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.game SET TABLE DESCRIPTION One row per game, from NFLVERSE.schedules. game_id is season_week_away_home; scores are null for games not played yet.;

-- Step 2: document the player_week table.
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.player_week SET TABLE DESCRIPTION One row per player per game, from NFLVERSE.player_stats: targets, carries, target share (a fraction 0-1) and PPR fantasy points. player_game_id is player_id + game_id.;

-- Step 2: document the injury_report table.
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.injury_report SET TABLE DESCRIPTION One row per player per week on the injury report, from NFLVERSE.injuries. report_status is Out, Doubtful, Questionable or null.;

-- Step 3: activate team from the schedules' home and away teams. COUNT is cast to int to match the declared type.
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.team AS
SELECT COALESCE(team, '') AS team, CAST(COUNT(*) AS INT) AS games_scheduled
FROM (SELECT home_team AS team FROM NFLVERSE.schedules
      UNION ALL SELECT away_team AS team FROM NFLVERSE.schedules) t
GROUP BY team;

-- Step 3: activate player from rosters (one row per player). One roster row has no gsis_id; it gets a "NO_ID <name>" key instead of '' so it cannot match the player_stats rows whose player_id is null (see Step 4).
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player AS
SELECT COALESCE(gsis_id, CONCAT('NO_ID ', full_name), '') AS gsis_id, full_name, position,
       COALESCE(team, '') AS team, status AS roster_status
FROM NFLVERSE.rosters;

-- Step 3: activate game from schedules.
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.game AS
SELECT COALESCE(game_id, '') AS game_id, season, week, game_type,
       COALESCE(home_team, '') AS home_team, COALESCE(away_team, '') AS away_team, home_score, away_score
FROM NFLVERSE.schedules;

-- Step 3: activate player_week from player_stats. The six rows with a null player_id become '' and fail the player FK.
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week AS
SELECT CONCAT(COALESCE(player_id, ''), '_', COALESCE(game_id, '')) AS player_game_id,
       COALESCE(player_id, '') AS player_id, COALESCE(game_id, '') AS game_id,
       week, targets, carries, target_share, fantasy_points_ppr
FROM NFLVERSE.player_stats;

-- Step 3: activate injury_report from injuries. injury_id is gsis_id + game type + week (unique: 2,062 rows, 2,062 distinct).
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.injury_report AS
SELECT COALESCE(CONCAT(COALESCE(gsis_id, ''), '_', COALESCE(game_type, ''), '_', CAST(week AS STRING)), '') AS injury_id,
       COALESCE(gsis_id, '') AS gsis_id, week, team, report_status, report_primary_injury
FROM NFLVERSE.injuries;

-- Step 4: custom data-quality rule: target_share is a fraction 0-1 (our app multiplies it by 100 for "%").
REGISTER DQ target_share_range TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week AS
target_share IS NULL OR (target_share >= 0 AND target_share <= 1);

-- Step 4: custom data-quality rule: a real GSIS ID looks like 00-0031408.
REGISTER DQ gsis_id_format TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player AS
gsis_id LIKE '00-%';

-- Step 4: custom data-quality rule: the report statuses the Critic's stand-in rule understands.
REGISTER DQ report_status_known TABLE lightning.metastore.nfl_usl_ns.nfl_usl.injury_report AS
report_status IS NULL OR report_status IN ('Out', 'Doubtful', 'Questionable');

-- Step 4: every key constraint and rule on the model.
LIST DQ USL lightning.metastore.nfl_usl_ns.nfl_usl;

-- Step 5: run every rule on player_week: its PK, the two FKs (player, game) and target_share_range. RUN DQ TABLE without a rule name runs them all.
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week;

-- Step 5: run every rule on player: its PK, the team FK and gsis_id_format.
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player;

-- Step 5: run every rule on injury_report: its PK, the player FK and report_status_known.
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.injury_report;

-- Step 5: run every rule on game: its PK and the home and away team FKs.
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.game;

-- Step 5: one rule by name: the player FK on player_week.
RUN DQ player_id TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week;

-- Step 6: the invalid records behind the counts. player_week: every row that fails any rule.
SHOW DQ ALL INVALID TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week;

-- Step 6: player: every row that fails any rule.
SHOW DQ ALL INVALID TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player;

-- Step 6: one rule's invalid records as ordinary columns: the player FK on player_week.
SHOW DQ INVALID RECORD player_id TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week;

-- Step 7: the namespace listing: the deployed model and each table's activation flag.
SHOW NAMESPACES OR TABLES IN lightning.metastore.nfl_usl_ns;

-- Step 7: the model's tables and their activation flags.
SHOW NAMESPACES OR TABLES IN lightning.metastore.nfl_usl_ns.nfl_usl;

-- =============================================================================
-- Not run: MATERIALIZE (no cloud storage target is configured on our cluster;
-- the app reads the NFLVERSE tables, cached with sql/nflverse_cache.sql).
-- MATERIALIZE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
--   TO STORAGE (format='parquet', path='/materialized/nfl_usl/player_week');
--
-- TEARDOWN / rebuild -- commented out. Run before re-running this file from scratch:
-- REMOVE USL nfl_usl NAMESPACE lightning.metastore.nfl_usl_ns;
-- DROP NAMESPACE lightning.metastore.nfl_usl_ns;
-- =============================================================================
