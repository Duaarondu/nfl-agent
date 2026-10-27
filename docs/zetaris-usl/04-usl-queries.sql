-- =============================================================================
-- Queries against the activated nfl_usl model (criterion 1c): they read only
-- lightning.metastore.nfl_usl_ns.nfl_usl.*, never NFLVERSE.* directly.
-- Live results: 04-usl-queries.md (made by run_usl.py).
-- =============================================================================

-- Rows per USL table: every table is activated and returns data.
SELECT 'team' AS usl_table, COUNT(*) AS row_count FROM lightning.metastore.nfl_usl_ns.nfl_usl.team
UNION ALL SELECT 'player', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.player
UNION ALL SELECT 'game', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.game
UNION ALL SELECT 'player_week', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week
UNION ALL SELECT 'injury_report', COUNT(*) FROM lightning.metastore.nfl_usl_ns.nfl_usl.injury_report;

-- player_week -> player -> game: Christian Watson's PPR points per game, with the opponent taken from the game's home and away teams. (player.team is the latest roster team, so this opponent rule is only right for a player who has not changed teams.)
SELECT pw.week, g.game_id,
       CASE WHEN g.home_team = p.team THEN g.away_team ELSE g.home_team END AS opponent,
       CASE WHEN g.home_team = p.team THEN 'home' ELSE 'away' END AS venue,
       pw.targets, ROUND(100 * pw.target_share, 1) AS target_share_pct, ROUND(pw.fantasy_points_ppr, 1) AS ppr_points
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week pw
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player p ON p.gsis_id = pw.player_id
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.game g ON g.game_id = pw.game_id
WHERE p.full_name = 'Christian Watson'
ORDER BY pw.week;

-- player -> game: Christian Watson's week-7 opponent, and his PPR points per game so far (player_week).
SELECT p.full_name, p.team, g.game_id,
       CASE WHEN g.home_team = p.team THEN g.away_team ELSE g.home_team END AS week_7_opponent,
       CASE WHEN g.home_team = p.team THEN 'home' ELSE 'away' END AS venue,
       s.games, s.ppr_per_game
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player p
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.game g ON g.week = 7 AND p.team IN (g.home_team, g.away_team)
JOIN (SELECT player_id, COUNT(*) AS games, ROUND(AVG(fantasy_points_ppr), 1) AS ppr_per_game
      FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week GROUP BY player_id) s ON s.player_id = p.gsis_id
WHERE p.full_name = 'Christian Watson';

-- injury_report -> player -> player_week: skill players listed Out or Doubtful in week 7, by PPR points per game (how much each absence matters).
SELECT ir.team, p.full_name, p.position, ir.report_status, ir.report_primary_injury,
       COUNT(pw.player_game_id) AS games, ROUND(AVG(pw.fantasy_points_ppr), 1) AS ppr_per_game
FROM lightning.metastore.nfl_usl_ns.nfl_usl.injury_report ir
JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player p ON p.gsis_id = ir.gsis_id
LEFT JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player_week pw ON pw.player_id = p.gsis_id
WHERE ir.week = 7 AND ir.report_status IN ('Out', 'Doubtful') AND p.position IN ('QB', 'RB', 'WR', 'TE')
GROUP BY ir.team, p.full_name, p.position, ir.report_status, ir.report_primary_injury
ORDER BY ppr_per_game DESC
LIMIT 15;

-- What the player FK guards: player_week rows with and without a matching player row (the 6 invalid records from RUN DQ).
SELECT CASE WHEN p.gsis_id IS NULL THEN 'no matching player' ELSE 'matches a player' END AS player_fk,
       COUNT(*) AS player_week_rows
FROM lightning.metastore.nfl_usl_ns.nfl_usl.player_week pw
LEFT JOIN lightning.metastore.nfl_usl_ns.nfl_usl.player p ON p.gsis_id = pw.player_id
GROUP BY CASE WHEN p.gsis_id IS NULL THEN 'no matching player' ELSE 'matches a player' END
ORDER BY player_week_rows DESC;
