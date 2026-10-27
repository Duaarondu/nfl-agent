# nfl_usl build: live results

Live results of [`03-nfl-usl.sql`](03-nfl-usl.sql), run on 2026-10-27 00:14 UTC through the Zetaris UI-proxy route by [`run_usl.py`](run_usl.py) (no cached results). Pasted as returned; nothing edited except that long results show their first 25 rows and cells over 600 characters are cut.

## 1. Step 0: the namespace. The parent lightning.metastore must exist first (companion guide section 8.4).

```sql
CREATE NAMESPACE IF NOT EXISTS lightning.metastore
```

Columns: `Result`. No rows.

_0.1s_

## 2. Step 0: the namespace for this model.

```sql
CREATE NAMESPACE IF NOT EXISTS lightning.metastore.nfl_usl_ns
```

Columns: `Result`. No rows.

_0.1s_

## 3. Step 1: design and deploy the model: five tables, their primary keys and six foreign keys, in one COMPILE USL statement.

```sql
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
)
```

| json |
|---|
| {"namespace":["metastore","nfl_usl_ns"],"name":"nfl_usl","tables":[{"name":"team","columnSpecs":[{"name":"team","dataType":"\"varchar(3)\"","primaryKey":{"columns":[]},"notNull":{"columns":[]},"dqAnnotations":[],"acAnnotations":[]},{"name":"games_scheduled","dataType":"\"integer\"","dqAnnotations":[],"acAnnotations":[]}],"unique":[],"foreignKeys":[],"checks":[],"ifNotExit":false,"namespace":["lightning","metastore","nfl_usl_ns","nfl_usl"],"dqAnnotations":[],"acAnnotations":[]},{"name":"player","columnSpecs":[{"name":"gsis_id","dataType":"\"varchar(40)\"","primaryKey":{"columns":[]},"notNull":{ … [4,617 characters; the first 600 are shown] |

_0.2s_

## 4. Step 2: document the model.

```sql
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl SET DESCRIPTION NFL fantasy semantic model over the NFLVERSE tables (nflverse, CC-BY 4.0), 2026 season: teams, players, games, player-game stats and the weekly injury report, with declared keys and foreign keys. Built alongside the NFL Fantasy Agent. The app still queries NFLVERSE directly.
```

| updated |
|---|
| true |

_0.1s_

## 5. Step 2: document the team table.

```sql
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.team SET TABLE DESCRIPTION One row per NFL team code (SF, GB, ...), from NFLVERSE.schedules home and away teams, with the number of scheduled games.
```

| updated |
|---|
| true |

_0.1s_

## 6. Step 2: document the player table.

```sql
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.player SET TABLE DESCRIPTION One row per player, from NFLVERSE.rosters (the latest week each player was rostered). gsis_id is the GSIS player ID shared by player_stats, pbp, injuries and depth_charts.
```

| updated |
|---|
| true |

_0.1s_

## 7. Step 2: document the game table.

```sql
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.game SET TABLE DESCRIPTION One row per game, from NFLVERSE.schedules. game_id is season_week_away_home; scores are null for games not played yet.
```

| updated |
|---|
| true |

_0.1s_

## 8. Step 2: document the player_week table.

```sql
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.player_week SET TABLE DESCRIPTION One row per player per game, from NFLVERSE.player_stats: targets, carries, target share (a fraction 0-1) and PPR fantasy points. player_game_id is player_id + game_id.
```

| updated |
|---|
| true |

_0.1s_

## 9. Step 2: document the injury_report table.

```sql
UPDATE USL lightning.metastore.nfl_usl_ns.nfl_usl.injury_report SET TABLE DESCRIPTION One row per player per week on the injury report, from NFLVERSE.injuries. report_status is Out, Doubtful, Questionable or null.
```

| updated |
|---|
| true |

_0.1s_

## 10. Step 3: activate team from the schedules' home and away teams. COUNT is cast to int to match the declared type.

```sql
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.team AS
SELECT COALESCE(team, '') AS team, CAST(COUNT(*) AS INT) AS games_scheduled
FROM (SELECT home_team AS team FROM NFLVERSE.schedules
      UNION ALL SELECT away_team AS team FROM NFLVERSE.schedules) t
GROUP BY team
```

| registered |
|---|
| {"name":"team","query":"SELECT COALESCE(team, '') AS team, CAST(COUNT(*) AS INT) AS games_scheduled\nFROM (SELECT home_team AS team FROM NFLVERSE.schedules\n      UNION ALL SELECT away_team AS team FROM NFLVERSE.schedules) t\nGROUP BY team"} |

_0.3s_

## 11. Step 3: activate player from rosters (one row per player). One roster row has no gsis_id; it gets a "NO_ID <name>" key instead of '' so it cannot match the player_stats rows whose player_id is null (see Step 4).

```sql
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player AS
SELECT COALESCE(gsis_id, CONCAT('NO_ID ', full_name), '') AS gsis_id, full_name, position,
       COALESCE(team, '') AS team, status AS roster_status
FROM NFLVERSE.rosters
```

| registered |
|---|
| {"name":"player","query":"SELECT COALESCE(gsis_id, CONCAT('NO_ID ', full_name), '') AS gsis_id, full_name, position,\n       COALESCE(team, '') AS team, status AS roster_status\nFROM NFLVERSE.rosters"} |

_0.3s_

## 12. Step 3: activate game from schedules.

```sql
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.game AS
SELECT COALESCE(game_id, '') AS game_id, season, week, game_type,
       COALESCE(home_team, '') AS home_team, COALESCE(away_team, '') AS away_team, home_score, away_score
FROM NFLVERSE.schedules
```

| registered |
|---|
| {"name":"game","query":"SELECT COALESCE(game_id, '') AS game_id, season, week, game_type,\n       COALESCE(home_team, '') AS home_team, COALESCE(away_team, '') AS away_team, home_score, away_score\nFROM NFLVERSE.schedules"} |

_0.4s_

## 13. Step 3: activate player_week from player_stats. The six rows with a null player_id become '' and fail the player FK.

```sql
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week AS
SELECT CONCAT(COALESCE(player_id, ''), '_', COALESCE(game_id, '')) AS player_game_id,
       COALESCE(player_id, '') AS player_id, COALESCE(game_id, '') AS game_id,
       week, targets, carries, target_share, fantasy_points_ppr
FROM NFLVERSE.player_stats
```

| registered |
|---|
| {"name":"player_week","query":"SELECT CONCAT(COALESCE(player_id, ''), '_', COALESCE(game_id, '')) AS player_game_id,\n       COALESCE(player_id, '') AS player_id, COALESCE(game_id, '') AS game_id,\n       week, targets, carries, target_share, fantasy_points_ppr\nFROM NFLVERSE.player_stats"} |

_0.3s_

## 14. Step 3: activate injury_report from injuries. injury_id is gsis_id + game type + week (unique: 2,062 rows, 2,062 distinct).

```sql
ACTIVATE USL TABLE lightning.metastore.nfl_usl_ns.nfl_usl.injury_report AS
SELECT COALESCE(CONCAT(COALESCE(gsis_id, ''), '_', COALESCE(game_type, ''), '_', CAST(week AS STRING)), '') AS injury_id,
       COALESCE(gsis_id, '') AS gsis_id, week, team, report_status, report_primary_injury
FROM NFLVERSE.injuries
```

| registered |
|---|
| {"name":"injury_report","query":"SELECT COALESCE(CONCAT(COALESCE(gsis_id, ''), '_', COALESCE(game_type, ''), '_', CAST(week AS STRING)), '') AS injury_id,\n       COALESCE(gsis_id, '') AS gsis_id, week, team, report_status, report_primary_injury\nFROM NFLVERSE.injuries"} |

_0.3s_

## 15. Step 4: custom data-quality rule: target_share is a fraction 0-1 (our app multiplies it by 100 for "%").

```sql
REGISTER DQ target_share_range TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week AS
target_share IS NULL OR (target_share >= 0 AND target_share <= 1)
```

| json |
|---|
| {"namespace":["metastore","nfl_usl_ns"],"name":"nfl_usl","tables":[{"name":"team","columnSpecs":[{"name":"team","dataType":"\"varchar(3)\"","primaryKey":{"columns":[]},"notNull":{"columns":[]},"dqAnnotations":[],"acAnnotations":[]},{"name":"games_scheduled","dataType":"\"integer\"","dqAnnotations":[],"acAnnotations":[]}],"unique":[],"foreignKeys":[],"checks":[],"ifNotExit":false,"namespace":["lightning","metastore","nfl_usl_ns","nfl_usl"],"dqAnnotations":[],"acAnnotations":[],"activateQuery":"SELECT COALESCE(team, '') AS team, CAST(COUNT(*) AS INT) AS games_scheduled\nFROM (SELECT home_team AS … [6,991 characters; the first 600 are shown] |

_0.7s_

## 16. Step 4: custom data-quality rule: a real GSIS ID looks like 00-0031408.

```sql
REGISTER DQ gsis_id_format TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player AS
gsis_id LIKE '00-%'
```

| json |
|---|
| {"namespace":["metastore","nfl_usl_ns"],"name":"nfl_usl","tables":[{"name":"team","columnSpecs":[{"name":"team","dataType":"\"varchar(3)\"","primaryKey":{"columns":[]},"notNull":{"columns":[]},"dqAnnotations":[],"acAnnotations":[]},{"name":"games_scheduled","dataType":"\"integer\"","dqAnnotations":[],"acAnnotations":[]}],"unique":[],"foreignKeys":[],"checks":[],"ifNotExit":false,"namespace":["lightning","metastore","nfl_usl_ns","nfl_usl"],"dqAnnotations":[],"acAnnotations":[],"activateQuery":"SELECT COALESCE(team, '') AS team, CAST(COUNT(*) AS INT) AS games_scheduled\nFROM (SELECT home_team AS … [7,060 characters; the first 600 are shown] |

_0.8s_

## 17. Step 4: custom data-quality rule: the report statuses the Critic's stand-in rule understands.

```sql
REGISTER DQ report_status_known TABLE lightning.metastore.nfl_usl_ns.nfl_usl.injury_report AS
report_status IS NULL OR report_status IN ('Out', 'Doubtful', 'Questionable')
```

| json |
|---|
| {"namespace":["metastore","nfl_usl_ns"],"name":"nfl_usl","tables":[{"name":"team","columnSpecs":[{"name":"team","dataType":"\"varchar(3)\"","primaryKey":{"columns":[]},"notNull":{"columns":[]},"dqAnnotations":[],"acAnnotations":[]},{"name":"games_scheduled","dataType":"\"integer\"","dqAnnotations":[],"acAnnotations":[]}],"unique":[],"foreignKeys":[],"checks":[],"ifNotExit":false,"namespace":["lightning","metastore","nfl_usl_ns","nfl_usl"],"dqAnnotations":[],"acAnnotations":[],"activateQuery":"SELECT COALESCE(team, '') AS team, CAST(COUNT(*) AS INT) AS games_scheduled\nFROM (SELECT home_team AS … [7,192 characters; the first 600 are shown] |

_0.8s_

## 18. Step 4: every key constraint and rule on the model.

```sql
LIST DQ USL lightning.metastore.nfl_usl_ns.nfl_usl
```

| name | table | type | expression |
|---|---|---|---|
| team | team | Primary key constraints |  |
| gsis_id | player | Primary key constraints |  |
| team | player | Foreign key constraints |  |
| gsis_id_format | player | Custom Data Quality | gsis_id LIKE '00-%' |
| game_id | game | Primary key constraints |  |
| home_team | game | Foreign key constraints |  |
| away_team | game | Foreign key constraints |  |
| player_game_id | player_week | Primary key constraints |  |
| player_id | player_week | Foreign key constraints |  |
| game_id | player_week | Foreign key constraints |  |
| target_share_range | player_week | Custom Data Quality | target_share IS NULL OR (target_share >= 0 AND target_share <= 1) |
| injury_id | injury_report | Primary key constraints |  |
| gsis_id | injury_report | Foreign key constraints |  |
| report_status_known | injury_report | Custom Data Quality | report_status IS NULL OR report_status IN ('Out', 'Doubtful', 'Questionable') |

_0.3s_

## 19. Step 5: run every rule on player_week: its PK, the two FKs (player, game) and target_share_range. RUN DQ TABLE without a rule name runs them all.

```sql
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
```

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| target_share_range | player_week | Custom Data Quality | 6488 | 6488 | 0 |
| player_game_id | player_week | Primary Key Constraint | 6488 | 6488 | 0 |
| player_id | player_week | Foreign Key Constraint | 6488 | 6482 | 6 |
| game_id | player_week | Foreign Key Constraint | 6488 | 6488 | 0 |

_9.8s_

## 20. Step 5: run every rule on player: its PK, the team FK and gsis_id_format.

```sql
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player
```

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| gsis_id_format | player | Custom Data Quality | 3054 | 3053 | 1 |
| gsis_id | player | Primary Key Constraint | 3054 | 3054 | 0 |
| team | player | Foreign Key Constraint | 3054 | 3054 | 0 |

_6.9s_

## 21. Step 5: run every rule on injury_report: its PK, the player FK and report_status_known.

```sql
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.injury_report
```

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| report_status_known | injury_report | Custom Data Quality | 2062 | 2062 | 0 |
| injury_id | injury_report | Primary Key Constraint | 2062 | 2062 | 0 |
| gsis_id | injury_report | Foreign Key Constraint | 2062 | 2062 | 0 |

_44.6s_

## 22. Step 5: run every rule on game: its PK and the home and away team FKs.

```sql
RUN DQ TABLE lightning.metastore.nfl_usl_ns.nfl_usl.game
```

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| game_id | game | Primary Key Constraint | 272 | 272 | 0 |
| home_team | game | Foreign Key Constraint | 272 | 272 | 0 |
| away_team | game | Foreign Key Constraint | 272 | 272 | 0 |

_9.9s_

## 23. Step 5: one rule by name: the player FK on player_week.

```sql
RUN DQ player_id TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
```

| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| player_id | player_week | Foreign Key Constraint | 6488 | 6482 | 6 |

_2.7s_

## 24. Step 6: the invalid records behind the counts. player_week: every row that fails any rule.

```sql
SHOW DQ ALL INVALID TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
```

| records |
|---|
| {"player_game_id":"_2026_06_SEA_DEN","player_id":"","game_id":"2026_06_SEA_DEN","week":6,"targets":0,"carries":0,"target_share":0.0,"fantasy_points_ppr":0.0} |
| {"player_game_id":"_2026_02_DET_BUF","player_id":"","game_id":"2026_02_DET_BUF","week":2,"targets":0,"carries":0,"target_share":0.0,"fantasy_points_ppr":0.0} |
| {"player_game_id":"_2026_05_TB_DAL","player_id":"","game_id":"2026_05_TB_DAL","week":5,"targets":0,"carries":0,"target_share":0.0,"fantasy_points_ppr":0.0} |
| {"player_game_id":"_2026_04_PIT_CLE","player_id":"","game_id":"2026_04_PIT_CLE","week":4,"targets":0,"carries":0,"target_share":0.0,"fantasy_points_ppr":0.0} |
| {"player_game_id":"_2026_01_NE_SEA","player_id":"","game_id":"2026_01_NE_SEA","week":1,"targets":0,"carries":0,"target_share":0.0,"fantasy_points_ppr":0.0} |
| {"player_game_id":"_2026_03_ATL_GB","player_id":"","game_id":"2026_03_ATL_GB","week":3,"targets":0,"carries":0,"target_share":0.0,"fantasy_points_ppr":0.0} |

_10.7s_

## 25. Step 6: player: every row that fails any rule.

```sql
SHOW DQ ALL INVALID TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player
```

**Error:** `POST /api/proxy/sql-editor/sqls/run-query failed: HTTP 400 {"msg":"org.apache.thrift.transport.TTransportException"}`

## 26. Step 6: one rule's invalid records as ordinary columns: the player FK on player_week.

```sql
SHOW DQ INVALID RECORD player_id TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
```

**Error:** `POST /api/proxy/sql-editor/sqls/run-query failed: HTTP 400 {"msg":"org.apache.thrift.transport.TTransportException"}`

## 27. Step 7: the namespace listing: the deployed model and each table's activation flag.

```sql
SHOW NAMESPACES OR TABLES IN lightning.metastore.nfl_usl_ns
```

**Error:** `POST /api/proxy/sql-editor/sqls/run-query failed: HTTP 400 {"msg":"org.apache.thrift.transport.TTransportException"}`

## 28. Step 7: the model's tables and their activation flags.

```sql
SHOW NAMESPACES OR TABLES IN lightning.metastore.nfl_usl_ns.nfl_usl
```

**Error:** `POST /api/proxy/sql-editor/sqls/run-query failed: HTTP 400 {"msg":"org.apache.thrift.transport.TTransportException"}`

28 statements, 4 errors.

---

## Rerun from statement 25

Statements 25-28 run again on 2026-10-27 00:19 UTC, after the errors above.

## 25. Step 6: player: every row that fails any rule.

```sql
SHOW DQ ALL INVALID TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player
```

| records |
|---|
| {"gsis_id":"NO_ID Al-Jay Henderson","full_name":"Al-Jay Henderson","position":"RB","team":"NYJ","roster_status":"DEV"} |

_27.5s_

## 26. Step 6: one rule's invalid records as ordinary columns: the player FK on player_week.

```sql
SHOW DQ INVALID RECORD player_id TABLE lightning.metastore.nfl_usl_ns.nfl_usl.player_week
```

| player_game_id | player_id | game_id | week | targets | carries | target_share | fantasy_points_ppr |
|---|---|---|---|---|---|---|---|
| _2026_01_NE_SEA |  | 2026_01_NE_SEA | 1 | 0 | 0 | 0.0 | 0.0 |
| _2026_02_DET_BUF |  | 2026_02_DET_BUF | 2 | 0 | 0 | 0.0 | 0.0 |
| _2026_03_ATL_GB |  | 2026_03_ATL_GB | 3 | 0 | 0 | 0.0 | 0.0 |
| _2026_04_PIT_CLE |  | 2026_04_PIT_CLE | 4 | 0 | 0 | 0.0 | 0.0 |
| _2026_05_TB_DAL |  | 2026_05_TB_DAL | 5 | 0 | 0 | 0.0 | 0.0 |
| _2026_06_SEA_DEN |  | 2026_06_SEA_DEN | 6 | 0 | 0 | 0.0 | 0.0 |

_3.6s_

## 27. Step 7: the namespace listing: the deployed model and each table's activation flag.

```sql
SHOW NAMESPACES OR TABLES IN lightning.metastore.nfl_usl_ns
```

| name | type | usl_id | count | activated |
|---|---|---|---|---|
| nfl_usl | usl | 1034 | 5 | NULL |

_0.3s_

## 28. Step 7: the model's tables and their activation flags.

```sql
SHOW NAMESPACES OR TABLES IN lightning.metastore.nfl_usl_ns.nfl_usl
```

| name | type | usl_id | count | activated |
|---|---|---|---|---|
| game | table | NULL | 0 | true |
| injury_report | table | NULL | 0 | true |
| player | table | NULL | 0 | true |
| player_week | table | NULL | 0 | true |
| team | table | NULL | 0 | true |

_0.2s_

4 statements, 0 errors.
