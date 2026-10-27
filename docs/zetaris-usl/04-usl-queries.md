# Queries against the USL: live results

Live results of [`04-usl-queries.sql`](04-usl-queries.sql), run on 2026-10-27 00:20 UTC through the Zetaris UI-proxy route by [`run_usl.py`](run_usl.py) (no cached results). Pasted as returned; nothing edited except that long results show their first 25 rows and cells over 600 characters are cut.

## 1. Rows per USL table: every table is activated and returns data.

```sql
SELECT 'team' AS usl_table, COUNT(*) AS row_count FROM lightning.metastore.nfl_usl_ns.nfl_usl.team
UNION ALL SELECT 'player', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.player
UNION ALL SELECT 'game', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.game
UNION ALL SELECT 'player_week', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week
UNION ALL SELECT 'injury_report', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.injury_report
```

| usl_table | row_count |
|---|---|
| team | 32 |
| player | 3054 |
| game | 272 |
| player_week | 6488 |
| injury_report | 2062 |

_7.0s_

## 2. player_week -> player -> game: Christian Watson's PPR points per game, with the opponent taken from the game's home and away teams. (player.team is the latest roster team, so this opponent rule is only right for a player who has not changed teams.)

```sql
SELECT pw.week, g.game_id,
       CASE WHEN g.home_team = p.team THEN g.away_team ELSE g.home_team END AS opponent,
       CASE WHEN g.home_team = p.team THEN 'home' ELSE 'away' END AS venue,
       pw.targets, ROUND(100 * pw.target_share, 1) AS target_share_pct, ROUND(pw.fantasy_points_ppr, 1) AS ppr_points
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week pw
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player p ON p.gsis_id = pw.player_id
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.game g ON g.game_id = pw.game_id
WHERE p.full_name = 'Christian Watson'
ORDER BY pw.week
```

| week | game_id | opponent | venue | targets | target_share_pct | ppr_points |
|---|---|---|---|---|---|---|
| 1 | 2026_01_GB_MIN | MIN | away | 8 | 20.0 | 32.7 |
| 2 | 2026_02_GB_NYJ | NYJ | away | 11 | 37.9 | 14.1 |
| 3 | 2026_03_ATL_GB | ATL | home | 10 | 19.6 | 22.6 |
| 4 | 2026_04_GB_TB | TB | away | 3 | 10.0 | 7.7 |
| 5 | 2026_05_CHI_GB | CHI | home | 8 | 25.8 | 32.3 |
| 6 | 2026_06_DAL_GB | DAL | home | 8 | 20.0 | 9.4 |

_4.5s_

## 3. player -> game: Christian Watson's week-7 opponent, and his PPR points per game so far (player_week).

```sql
SELECT p.full_name, p.team, g.game_id,
       CASE WHEN g.home_team = p.team THEN g.away_team ELSE g.home_team END AS week_7_opponent,
       CASE WHEN g.home_team = p.team THEN 'home' ELSE 'away' END AS venue,
       s.games, s.ppr_per_game
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player p
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.game g ON g.week = 7 AND p.team IN (g.home_team, g.away_team)
JOIN (SELECT player_id, COUNT(*) AS games, ROUND(AVG(fantasy_points_ppr), 1) AS ppr_per_game
      FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week GROUP BY player_id) s ON s.player_id = p.gsis_id
WHERE p.full_name = 'Christian Watson'
```

| column | value |
|---|---|
| full_name | Christian Watson |
| team | GB |
| game_id | 2026_07_GB_DET |
| week_7_opponent | DET |
| venue | away |
| games | 6 |
| ppr_per_game | 19.8 |

_41.9s_

## 4. injury_report -> player -> player_week: skill players listed Out or Doubtful in week 7, by PPR points per game (how much each absence matters).

```sql
SELECT ir.team, p.full_name, p.position, ir.report_status, ir.report_primary_injury,
       COUNT(pw.player_game_id) AS games, ROUND(AVG(pw.fantasy_points_ppr), 1) AS ppr_per_game
FROM lightning.metastore.nfl_usl_ns.nfl_usl.injury_report ir
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player p ON p.gsis_id = ir.gsis_id
LEFT JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player_week pw ON pw.player_id = p.gsis_id
WHERE ir.week = 7 AND ir.report_status IN ('Out', 'Doubtful') AND p.position IN ('QB', 'RB', 'WR', 'TE')
GROUP BY ir.team, p.full_name, p.position, ir.report_status, ir.report_primary_injury
ORDER BY ppr_per_game DESC
LIMIT 15
```

| column | value |
|---|---|
| team | CHI |
| full_name | Kyle Monangai |
| position | RB |
| report_status | Out |
| report_primary_injury | Thumb |
| games | 4 |
| ppr_per_game | 14.8 |

_6.1s_

## 5. What the player FK guards: player_week rows with and without a matching player row (the 6 invalid records from RUN DQ).

```sql
SELECT CASE WHEN p.gsis_id IS NULL THEN 'no matching player' ELSE 'matches a player' END AS player_fk,
       COUNT(*) AS player_week_rows
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week pw
LEFT JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player p ON p.gsis_id = pw.player_id
GROUP BY CASE WHEN p.gsis_id IS NULL THEN 'no matching player' ELSE 'matches a player' END
ORDER BY player_week_rows DESC
```

| player_fk | player_week_rows |
|---|---|
| matches a player | 6482 |
| no matching player | 6 |

_3.0s_

5 statements, 0 errors.
