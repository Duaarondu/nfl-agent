-- =============================================================================
-- Exploratory queries over the seven NFLVERSE tables (criterion 1b).
-- Read-only: nothing here changes a table. For each table: a row count, one
-- sample row, then two or three queries that show what the agents get out of it.
-- Live results: 02-exploratory-queries.md (made by run_usl.py).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- player_stats: one row per player per game
-- ---------------------------------------------------------------------------

-- player_stats: row count, players, games and weeks
SELECT COUNT(*) AS row_count, COUNT(DISTINCT player_id) AS players, COUNT(DISTINCT game_id) AS games,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.player_stats;

-- player_stats: sample row
SELECT * FROM NFLVERSE.player_stats WHERE player_display_name = 'Christian Watson' AND week = 1;

-- player_stats: top 10 PPR scorers through the latest week (the Opportunity and Matchups factors read this table)
SELECT player_display_name, position, team, COUNT(*) AS games, ROUND(SUM(fantasy_points_ppr), 1) AS ppr_points,
       ROUND(SUM(fantasy_points_ppr) / COUNT(*), 1) AS ppr_per_game
FROM NFLVERSE.player_stats
WHERE season_type = 'REG'
GROUP BY player_display_name, position, team
ORDER BY ppr_points DESC
LIMIT 10;

-- player_stats: highest average target share among WRs and TEs with 4+ games (Opportunity factor)
SELECT player_display_name, position, team, COUNT(*) AS games, ROUND(100 * AVG(target_share), 1) AS avg_target_share_pct,
       SUM(targets) AS targets
FROM NFLVERSE.player_stats
WHERE position IN ('WR', 'TE') AND target_share IS NOT NULL
GROUP BY player_display_name, position, team
HAVING COUNT(*) >= 4
ORDER BY avg_target_share_pct DESC
LIMIT 10;

-- player_stats: rows with no player_id (found while building the USL keys)
SELECT game_id, team, week, position, fantasy_points_ppr
FROM NFLVERSE.player_stats
WHERE player_id IS NULL;

-- ---------------------------------------------------------------------------
-- pbp: one row per play
-- ---------------------------------------------------------------------------

-- pbp: row count, games and play types
SELECT COUNT(*) AS row_count, COUNT(DISTINCT game_id) AS games, COUNT(DISTINCT play_type) AS play_types,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.pbp;

-- pbp: sample row
SELECT * FROM NFLVERSE.pbp WHERE game_id = '2026_01_NE_SEA' AND play_type = 'pass' LIMIT 1;

-- pbp: pass rate by team, highest first (Team pass rate and game script factor)
SELECT posteam, SUM(pass) AS pass_plays, SUM(rush) AS rush_plays,
       ROUND(100 * SUM(pass) / NULLIF(SUM(pass) + SUM(rush), 0), 1) AS pass_rate_pct
FROM NFLVERSE.pbp
WHERE posteam IS NOT NULL
GROUP BY posteam
ORDER BY pass_rate_pct DESC
LIMIT 10;

-- pbp: most red-zone targets (yardline_100 <= 20; Touchdowns and red zone factor)
SELECT receiver_player_name, posteam, COUNT(*) AS rz_targets, SUM(pass_touchdown) AS rz_pass_tds
FROM NFLVERSE.pbp
WHERE yardline_100 <= 20 AND receiver_player_id IS NOT NULL AND play_type = 'pass'
GROUP BY receiver_player_name, posteam
ORDER BY rz_targets DESC
LIMIT 10;

-- ---------------------------------------------------------------------------
-- snap_counts: one row per player per game; no GSIS ID
-- ---------------------------------------------------------------------------

-- snap_counts: row count, players and games
SELECT COUNT(*) AS row_count, COUNT(DISTINCT pfr_player_id) AS players, COUNT(DISTINCT game_id) AS games,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.snap_counts;

-- snap_counts: sample row
SELECT * FROM NFLVERSE.snap_counts WHERE player = 'Christian Watson' AND week = 1;

-- snap_counts: WRs with the highest average offensive snap share, 4+ games (Opportunity factor)
SELECT player, team, COUNT(*) AS games, ROUND(100 * AVG(offense_pct), 1) AS avg_snap_pct
FROM NFLVERSE.snap_counts
WHERE position = 'WR'
GROUP BY player, team
HAVING COUNT(*) >= 4
ORDER BY avg_snap_pct DESC
LIMIT 10;

-- snap_counts: names that differ from player_stats on the same team and game (the join our app uses is by name)
SELECT sc.player AS snap_counts_name, sc.team, COUNT(*) AS games
FROM NFLVERSE.snap_counts sc
LEFT JOIN NFLVERSE.player_stats ps ON ps.game_id = sc.game_id AND ps.team = sc.team AND ps.player_display_name = sc.player
WHERE ps.player_id IS NULL AND sc.position IN ('QB', 'RB', 'WR', 'TE') AND sc.offense_snaps >= 20
GROUP BY sc.player, sc.team
ORDER BY games DESC, snap_counts_name
LIMIT 15;

-- snap_counts: skill-player rows that find their player_stats row by name (the app's Opportunity join) vs by ID (rosters.pfr_id -> gsis_id)
SELECT COUNT(*) AS skill_snap_rows,
       SUM(CASE WHEN n.player_id IS NULL THEN 0 ELSE 1 END) AS matched_by_name,
       SUM(CASE WHEN i.player_id IS NULL THEN 0 ELSE 1 END) AS matched_by_id
FROM NFLVERSE.snap_counts sc
LEFT JOIN NFLVERSE.player_stats n ON n.game_id = sc.game_id AND n.team = sc.team AND n.player_display_name = sc.player
LEFT JOIN NFLVERSE.rosters r ON r.pfr_id = sc.pfr_player_id
LEFT JOIN NFLVERSE.player_stats i ON i.game_id = sc.game_id AND i.player_id = r.gsis_id
WHERE sc.position IN ('QB', 'RB', 'WR', 'TE');

-- snap_counts: Deebo Samuel's snap share by week, joined by name (as the app does) and by ID
SELECT ps.week, ps.player_display_name, ROUND(100 * n.offense_pct, 1) AS snap_pct_by_name,
       ROUND(100 * i.offense_pct, 1) AS snap_pct_by_id, i.player AS snap_counts_name
FROM NFLVERSE.player_stats ps
LEFT JOIN NFLVERSE.snap_counts n ON n.game_id = ps.game_id AND n.team = ps.team AND n.player = ps.player_display_name
LEFT JOIN NFLVERSE.rosters r ON r.gsis_id = ps.player_id
LEFT JOIN NFLVERSE.snap_counts i ON i.game_id = ps.game_id AND i.pfr_player_id = r.pfr_id
WHERE ps.player_display_name LIKE 'Deebo Samuel%'
ORDER BY ps.week;

-- ---------------------------------------------------------------------------
-- depth_charts: snapshots, many per week
-- ---------------------------------------------------------------------------

-- depth_charts: row count, snapshots, players and teams
SELECT COUNT(*) AS row_count, COUNT(DISTINCT dt) AS snapshots, COUNT(DISTINCT gsis_id) AS players,
       COUNT(DISTINCT team) AS teams, MIN(dt) AS first_snapshot, MAX(dt) AS last_snapshot
FROM NFLVERSE.depth_charts;

-- depth_charts: sample row
SELECT * FROM NFLVERSE.depth_charts WHERE team = 'SF' AND pos_abb = 'WR' AND pos_rank = 1 ORDER BY dt DESC LIMIT 1;

-- depth_charts: the 49ers' current WR and TE order (Depth chart factor: latest snapshot only)
SELECT pos_abb, pos_rank, player_name, pos_slot
FROM NFLVERSE.depth_charts
WHERE team = 'SF' AND pos_abb IN ('WR', 'TE') AND dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = 'SF')
ORDER BY pos_abb, pos_rank, pos_slot
LIMIT 15;

-- depth_charts: snapshot rows per team (why the app always filters to MAX(dt))
SELECT team, COUNT(DISTINCT dt) AS snapshots, COUNT(*) AS rows_all_snapshots
FROM NFLVERSE.depth_charts
GROUP BY team
ORDER BY rows_all_snapshots DESC
LIMIT 5;

-- ---------------------------------------------------------------------------
-- injuries: weekly injury report, one row per player per week
-- ---------------------------------------------------------------------------

-- injuries: row count, players and weeks
SELECT COUNT(*) AS row_count, COUNT(DISTINCT gsis_id) AS players, MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.injuries;

-- injuries: sample row
SELECT * FROM NFLVERSE.injuries WHERE team = 'SF' AND report_status = 'Out' ORDER BY week LIMIT 1;

-- injuries: report status counts (Status and Teammate absences factors)
SELECT COALESCE(report_status, '(none)') AS report_status, COUNT(*) AS player_weeks
FROM NFLVERSE.injuries
GROUP BY COALESCE(report_status, '(none)')
ORDER BY player_weeks DESC;

-- injuries: skill players listed Out in the latest week
SELECT team, full_name, position, report_primary_injury
FROM NFLVERSE.injuries
WHERE week = (SELECT MAX(week) FROM NFLVERSE.injuries) AND report_status = 'Out' AND position IN ('QB', 'RB', 'WR', 'TE')
ORDER BY team, position, full_name
LIMIT 15;

-- ---------------------------------------------------------------------------
-- rosters: one row per player (the latest week each player was rostered)
-- ---------------------------------------------------------------------------

-- rosters: row count, players, teams and weeks
SELECT COUNT(*) AS row_count, COUNT(DISTINCT gsis_id) AS players, COUNT(DISTINCT team) AS teams,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.rosters;

-- rosters: sample row
SELECT * FROM NFLVERSE.rosters WHERE full_name = 'Mike Evans';

-- rosters: roster status counts (the premise check and the stand-in pool use status ACT)
SELECT status, COUNT(*) AS players
FROM NFLVERSE.rosters
GROUP BY status
ORDER BY players DESC;

-- rosters: rows with no gsis_id (found while building the USL keys)
SELECT season, week, team, full_name, position, status
FROM NFLVERSE.rosters
WHERE gsis_id IS NULL;

-- ---------------------------------------------------------------------------
-- schedules: one row per game
-- ---------------------------------------------------------------------------

-- schedules: row count, weeks, and games played vs not played yet
SELECT COUNT(*) AS row_count, MIN(week) AS first_week, MAX(week) AS last_week,
       SUM(CASE WHEN home_score IS NULL THEN 0 ELSE 1 END) AS games_played,
       SUM(CASE WHEN home_score IS NULL THEN 1 ELSE 0 END) AS games_not_played
FROM NFLVERSE.schedules;

-- schedules: sample row
SELECT * FROM NFLVERSE.schedules WHERE game_id = '2026_01_NE_SEA';

-- schedules: week 7 games (the next-matchup factor reads the named week)
SELECT game_id, gameday, away_team, home_team, away_score, home_score
FROM NFLVERSE.schedules
WHERE week = 7
ORDER BY gameday, game_id;

-- schedules: bye weeks so far (weeks 1-7) per team, from home and away games
SELECT team, 7 - COUNT(*) AS byes_in_weeks_1_to_7
FROM (SELECT home_team AS team FROM NFLVERSE.schedules WHERE week <= 7
      UNION ALL SELECT away_team AS team FROM NFLVERSE.schedules WHERE week <= 7) t
GROUP BY team
HAVING COUNT(*) < 7
ORDER BY team;
