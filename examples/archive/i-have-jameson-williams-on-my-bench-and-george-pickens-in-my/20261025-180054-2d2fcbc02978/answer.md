```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Weekly opportunity, Touchdown share, Next matchup, Team usage share, Recent trend
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: model
Timings: total 128.7s; analyst 41.7s, critic 57.8s, factor_agent 90.5s, planner 5.4s (busy time; factor agents run in parallel)

Question: I have Jameson Williams on my bench and George Pickens in my starting lineup, who should I pick?
Run 2d2fcbc02978: 6 queries, 1 critic rounds, 128.7s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for demo: 12-team, half-PPR scoring; roster: George Kittle (SF, TE), Davante Adams (LA, WR), Jameson Williams (DET, WR), George Pickens (DAL, WR) (6 memories retrieved)
[MEMORY CONTEXT]
## fantasy
- [WK] Jameson Williams (DET, WR) is on the user's roster. (entities: jameson williams, jameson, williams, det) <mem-a007710dcf54>
- [WK] George Pickens (DAL, WR) is on the user's roster. (entities: george pickens, george, pickens, dal) <mem-8122c920a3ea>
- [WK] George Kittle (SF, TE) is on the user's roster. (entities: george kittle, george, kittle) <mem-e056c4b30e22>
- [WK] Davante Adams (LA, WR) is on the user's roster. (entities: davante adams, davante, adams) <mem-a50203748634>
- [WK] The user's league uses half-PPR scoring. (entities: ppr) <mem-93d88debe813>
- [WK] The user's league has 12 teams. <mem-9034ec3fad7e>
[/MEMORY CONTEXT]

Answer before the critic:
Start George Pickens over Jameson Williams. George Pickens gets the start over Jameson Williams in week 7. Pickens owns a 21.9% target share and 8.7 targets per game, producing 10.9 half-PPR points, and faces a PHI defense that allows 31.8 half-PPR points per game to WRs (rank 3), far more favorable than Williams' matchup against GB (26 allowed, rank 17). Though Williams is more touchdown-reliant at 24.7% of his half-PPR points coming from scores (vs Pickens' 9.2%), Pickens' higher usage and significantly softer defensive spot make him the stronger weekly play in half-PPR.

Critic rounds:
  Round 1: approved (review: model), 0 blocking of 0 issues

Final answer (approved; model verdict):
Start George Pickens over Jameson Williams. George Pickens gets the start over Jameson Williams in week 7. Pickens owns a 21.9% target share and 8.7 targets per game, producing 10.9 half-PPR points, and faces a PHI defense that allows 31.8 half-PPR points per game to WRs (rank 3), far more favorable than Williams' matchup against GB (26 allowed, rank 17). Though Williams is more touchdown-reliant at 24.7% of his half-PPR points coming from scores (vs Pickens' 9.2%), Pickens' higher usage and significantly softer defensive spot make him the stronger weekly play in half-PPR.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Weekly opportunity [favours George Pickens, strong, model] (queries 2): Pickens has a 21.9% target share and 8.7 targets per game for 10.9 half-PPR points, while Williams has a 15.2% target share and 5.8 targets per game for 9.7 half-PPR points.
  2. Touchdown share [favours Jameson Williams, strong, model] (queries 5): Jameson Williams accounts for 24.7% of his half-PPR points from touchdowns (12 of 48.6) versus George Pickens' 9.2% (6 of 65.3).
  3. Next matchup [favours George Pickens, strong, model] (queries 6): Pickens faces PHI allowing 31.8 half-PPR points per game to WRs (rank 3), while Williams faces GB allowing 26 half-PPR points per game to WRs (rank 17).
  4. Team usage share [favours George Pickens, moderate, model] (queries 3): George Pickens averages 21.9% target share versus Jameson Williams' 15.2%.
  5. Recent trend [favours Jameson Williams, moderate, model] (queries 4): George Pickens averaged 7.7 half-PPR points per game in weeks 1-3 and 14.1 from week 4 on, with target share dropping from 24.4% to 19.4%, while Jameson Williams averaged 5.9 in weeks 1-3 and 15.5 from week 4 on, with target share shifting from 15.5% to 14.7%.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. George Pickens: DAL, WR, roster status ACT (week 7). Jameson Williams: DET, WR, roster status ACT (week 7).  (queries 1)
  2. Pickens has a 21.9% target share and 8.7 targets per game for 10.9 half-PPR points, while Williams has a 15.2% target share and 5.8 targets per game for 9.7 half-PPR points.  (queries 2)
  3. Jameson Williams accounts for 24.7% of his half-PPR points from touchdowns (12 of 48.6) versus George Pickens' 9.2% (6 of 65.3).  (queries 5)
  4. Pickens faces PHI allowing 31.8 half-PPR points per game to WRs (rank 3), while Williams faces GB allowing 26 half-PPR points per game to WRs (rank 17).  (queries 6)
  5. George Pickens averages 21.9% target share versus Jameson Williams' 15.2%.  (queries 3)
  6. George Pickens averaged 7.7 half-PPR points per game in weeks 1-3 and 14.1 from week 4 on, with target share dropping from 24.4% to 19.4%, while Jameson Williams averaged 5.9 in weeks 1-3 and 15.5 from week 4 on, with target share shifting from 15.5% to 14.7%.  (queries 4)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('jameson williams', 'george pickens', 'i have', 'have jameson', 'williams on', 'on my', 'my bench', 'bench and', 'and george', 'pickens in', 'in my', 'my starting', 'starting lineup', 'lineup who', 'who should', 'should i', 'i pick', 'i have jameson', 'have jameson williams', 'jameson williams on', 'williams on my', 'on my bench', 'my bench and', 'bench and george', 'and george pickens', 'george pickens in', 'pickens in my', 'in my starting', 'my starting lineup', 'starting lineup who', 'lineup who should', 'who should i', 'should i pick') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0037247 | George Pickens | DAL | WR | ACT | 7
      00-0037240 | Jameson Williams | DET | WR | ACT | 7
  [2] Jameson Williams vs George Pickens: snap %, targets, target share and half-PPR points by week
      SELECT ps.player_display_name AS player, ps.week, ps.opponent_team, ROUND(100 * sc.offense_pct, 1) AS snap_pct, ps.targets, ROUND(100 * ps.target_share, 1) AS target_share_pct, ps.receptions, ps.carries, ROUND((ps.fantasy_points + ps.fantasy_points_ppr) / 2, 1) AS half_ppr_points FROM NFLVERSE.player_stats ps LEFT JOIN NFLVERSE.snap_counts sc ON sc.game_id = ps.game_id AND sc.player = ps.player_display_name AND sc.team = ps.team WHERE ps.season = 2026 AND ps.player_id IN ('00-0037240', '00-0037247') ORDER BY ps.player_display_name, ps.week
      player | week | opponent_team | snap_pct | targets | target_share_pct | receptions | carries | half_ppr_points
      George Pickens | 1 | NYG | 84.0 | 6 | 20.0 | 3 | 0 | 4.3
      George Pickens | 2 | WAS | 76.0 | 8 | 25.8 | 6 | 0 | 7.0
      George Pickens | 3 | BAL | 85.0 | 11 | 27.5 | 7 | 0 | 11.7
      George Pickens | 4 | HOU | 86.0 | 3 | 7.0 | 2 | 0 | 8.5
      George Pickens | 5 | TB | 88.0 | 13 | 31.0 | 9 | 0 | 23.5
      George Pickens | 6 | GB | 88.0 | 11 | 20.4 | 6 | 0 | 10.3
      Jameson Williams | 1 | NO | 84.0 | 9 | 23.1 | 4 | 0 | 6.5
      Jameson Williams | 2 | BUF | 97.0 | 4 | 10.5 | 2 | 0 | 4.3
      Jameson Williams | 3 | NYJ | 82.0 | 4 | 12.9 | 4 | 0 | 6.9
      Jameson Williams | 4 | CAR | 99.0 | 8 | 15.7 | 6 | 0 | 13.2
      Jameson Williams | 5 | ARI | 89.0 | 4 | 13.8 | 2 | 0 | 17.7
  [3] Jameson Williams vs George Pickens: share of their team's targets and air yards, and half-PPR points per game
      SELECT ps.player_display_name AS player, ps.team, COUNT(*) AS games, SUM(ps.targets) AS targets, ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, ROUND(100 * AVG(ps.air_yards_share), 1) AS avg_air_yards_share_pct, SUM(ps.carries) AS carries, ROUND(AVG((ps.fantasy_points + ps.fantasy_points_ppr) / 2), 1) AS half_ppr_per_game FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037240', '00-0037247') GROUP BY ps.player_display_name, ps.team ORDER BY ps.player_display_name
      player | team | games | targets | avg_target_share_pct | avg_air_yards_share_pct | carries | half_ppr_per_game
      George Pickens | DAL | 6 | 52 | 21.9 | 31.9 | 0 | 10.9
      Jameson Williams | DET | 5 | 29 | 15.2 | 34.1 | 0 | 9.7
  [4] Jameson Williams vs George Pickens: half-PPR points per game and target share in weeks 1-3 vs 4-6
      SELECT ps.player_display_name AS player, 3 AS split_week, SUM(CASE WHEN ps.week <= 3 THEN 1 ELSE 0 END) AS early_games, SUM(CASE WHEN ps.week > 3 THEN 1 ELSE 0 END) AS late_games, ROUND(AVG(CASE WHEN ps.week <= 3 THEN (ps.fantasy_points + ps.fantasy_points_ppr) / 2 END), 1) AS early_half_ppr_per_game, ROUND(AVG(CASE WHEN ps.week > 3 THEN (ps.fantasy_points + ps.fantasy_points_ppr) / 2 END), 1) AS late_half_ppr_per_game, ROUND(100 * AVG(CASE WHEN ps.week <= 3 THEN ps.target_share END), 1) AS early_target_share_pct, ROUND(100 * AVG(CASE WHEN ps.week > 3 THEN ps.target_share END), 1) AS late_target_share_pct FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037240', '00-0037247') GROUP BY ps.player_display_name ORDER BY ps.player_display_name
      player | split_week | early_games | late_games | early_half_ppr_per_game | late_half_ppr_per_game | early_target_share_pct | late_target_share_pct
      George Pickens | 3 | 3 | 3 | 7.7 | 14.1 | 24.4 | 19.4
      Jameson Williams | 3 | 3 | 2 | 5.9 | 15.5 | 15.5 | 14.7
  [5] Jameson Williams vs George Pickens: touchdowns and the share of half-PPR points that came from them
      SELECT ps.player_display_name AS player, SUM(ps.receiving_tds + ps.rushing_tds) AS touchdowns, 6 * SUM(ps.receiving_tds + ps.rushing_tds) AS td_points, ROUND(SUM((ps.fantasy_points + ps.fantasy_points_ppr) / 2), 1) AS half_ppr_points, ROUND(100 * 6 * SUM(ps.receiving_tds + ps.rushing_tds) / NULLIF(SUM((ps.fantasy_points + ps.fantasy_points_ppr) / 2), 0), 1) AS td_share_pct FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037240', '00-0037247') GROUP BY ps.player_display_name ORDER BY ps.player_display_name
      player | touchdowns | td_points | half_ppr_points | td_share_pct
      George Pickens | 1 | 6 | 65.3 | 9.2
      Jameson Williams | 2 | 12 | 48.6 | 24.7
  [6] Jameson Williams vs George Pickens: next opponent after week 6 and its average half-PPR points allowed to the position (rank 1 = most allowed)
      WITH players AS (SELECT '00-0037240' AS player_id, 'Jameson Williams' AS player, 'DET' AS team, 'WR' AS position UNION ALL SELECT '00-0037247' AS player_id, 'George Pickens' AS player, 'DAL' AS team, 'WR' AS position), games AS (SELECT home_team AS team, away_team AS opponent, week FROM NFLVERSE.schedules WHERE season = 2026 AND week > 6 UNION ALL SELECT away_team AS team, home_team AS opponent, week FROM NFLVERSE.schedules WHERE season = 2026 AND week > 6), next_week AS (SELECT team, MIN(week) AS week FROM games GROUP BY team), allowed AS (SELECT opponent_team, position, week, SUM((fantasy_points + fantasy_points_ppr) / 2) AS pts FROM NFLVERSE.player_stats WHERE season = 2026 GROUP BY opponent_team, position, week), avg_allowed AS (SELECT opponent_team, position, ROUND(AVG(pts), 1) AS avg_half_ppr_allowed FROM allowed GROUP BY opponent_team, position), ranked AS (SELECT opponent_team, position, avg_half_ppr_allowed, RANK() OVER (PARTITION BY position ORDER BY avg_half_ppr_allowed DESC) AS allowed_rank FROM avg_allowed) SELECT p.player, p.team, p.position, n.week AS next_week, g.opponent, r.avg_half_ppr_allowed AS opp_avg_half_ppr_allowed, r.allowed_rank FROM players p JOIN next_week n ON n.team = p.team JOIN games g ON g.team = p.team AND g.week = n.week LEFT JOIN ranked r ON r.opponent_team = g.opponent AND r.position = p.position ORDER BY p.player
      player | team | position | next_week | opponent | opp_avg_half_ppr_allowed | allowed_rank
      George Pickens | DAL | WR | 7 | PHI | 31.8 | 3
      Jameson Williams | DET | WR | 7 | GB | 26.0 | 17
```
