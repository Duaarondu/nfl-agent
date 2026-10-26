```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Team usage share, Recent trend, Touchdown share, Next matchup, Weekly opportunity
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: model, model
Timings: total 43.4s; analyst 31.7s, critic 7.7s, factor_agent 5.2s, planner 2.5s (busy time; factor agents run in parallel)

Question: Who should I start Trey Mcbride or Bowers for week 7
Run 76a8e6f7a7f6: 7 queries, 2 critic rounds, 43.4s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for rr4-mcbride: PPR scoring; roster: none (0 memories retrieved)

Answer before the critic:
Start Brock Bowers over Trey McBride. Bowers = Brock Bowers, LV TE. Brock Bowers leads in PPR points per game (20.6 vs 17.2) and recent weekly production (18.2 vs 14.7), outweighing Trey McBride's edge in touchdown share (17.5% vs 21.9%) and matchup difficulty (DEN rank 15 vs LA rank 31). Bowers's stronger seasonal consistency and higher target volume edge decide the start.

Critic rounds:
  Round 1: needs_revision (review: model), 2 blocking of 2 issues
    - [blocking] model_review in answer: The facts show Brock Bowers has higher seasonal PPR points per game (20.6 vs 17.2) and higher recent weekly points (18.2 vs 14.7 in weeks 4-6). However, Trey McBride has a more favorable week 7 matchup (DEN rank 15 allowing 13.2 PPR vs LA rank 31 allowing 8.3 PPR) and lower touchdown dependency (17.5% vs 21.9%), which the code rules favor McBride. The overall PPR production edge for Bowers is clear, but the answer's claim that it 'outweighs' both the matchup and touchdown factors is a value judgment; the facts present competing advantages without a definitive hierarchy.
      claim: Brock Bowers leads in PPR points per game (20.6 vs 17.2) and recent weekly production (18.2 vs 14.7), outweighing Trey McBride's edge in touchdown share (17.5% vs 21.9%) and matchup difficulty (DEN rank 15 vs LA rank 31).
    - [blocking] model_review in answer: The facts show Trey McBride has higher target volume (65 vs 43 targets) and higher average snap share (90.5% vs 82.2%). While Bowers has higher seasonal PPR points per game, McBride's target and snap share edge contradicts the claim of 'higher target volume edge' for Bowers.
      claim: Bowers's stronger seasonal consistency and higher target volume edge decide the start.
  Round 2: approved (review: model), 0 blocking of 1 issues
    - [recorded] model_review in answer: The facts show Trey McBride has the easier week 7 matchup (DEN rank 15, 13.2 PPR allowed) vs Brock Bowers (LA rank 31, 8.3 PPR allowed). By the code rule for next opponent's PPR points allowed per game, this factor favours Trey McBride. The answer incorrectly states McBride has the more favorable matchup but then says Bowers's advantage outweighs it; the facts indicate the matchup factor favors McBride, not Bowers. Additionally, while Bowers has higher seasonal PPR (20.6 vs 17.2) and higher recent weekly points (18.2 vs 14.7 weeks 4-6), the code rule for share of points from touchdowns favors Trey McBride (17.5% vs 21.9%, lower is steadier). The answer dismisses the touchdown dependency factor, but the facts show it favors McBride. The overall assessment that Bowers's scoring advantage outweighs the matchup and dependency factors is a value judgment; the factual data shows the matchup and touchdown dependency factors both favor McBride, which the answer does not correctly account for.
      claim: Brock Bowers has higher seasonal PPR points per game (20.6 vs 17.2) and a stronger recent weekly trend (18.2 vs 14.7 in weeks 4-6), giving him a consistent production edge despite Trey McBride's more favorable week 7 matchup against a Denver defense allowing 13.2 PPR points to TEs and lower touchdown dependency. The overall scoring advantage for Bowers outweighs the matchup and dependency factors.

Final answer (approved; model verdict):
Start Brock Bowers over Trey McBride. Bowers = Brock Bowers, LV TE. Brock Bowers has higher seasonal PPR points per game (20.6 vs 17.2) and a stronger recent weekly trend (18.2 vs 14.7 in weeks 4-6), giving him a consistent production edge despite Trey McBride's more favorable week 7 matchup against a Denver defense allowing 13.2 PPR points to TEs and lower touchdown dependency. The overall scoring advantage for Bowers outweighs the matchup and dependency factors.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Team usage share [favours Trey McBride, strong, model] (queries 4): Trey McBride has a 29.7% average target share compared to Brock Bowers's 29.3%, making this factor level per the code rule.
  2. Recent trend [favours Brock Bowers, strong, model] (queries 5): Brock Bowers averaged 18.2 PPR points per game in later weeks compared to Trey McBride's 14.7, making Bowers the stronger start based on recent trend.
  3. Touchdown share [favours Trey McBride, strong, model] (queries 6): Trey McBride has 17.5% of his PPR points from touchdowns compared to Brock Bowers's 21.9%, making McBride less touchdown-dependent and steadier.
  4. Next matchup [favours Trey McBride, strong, model] (queries 7): Trey McBride faces DEN allowing 13.2 PPR points per game to TEs (rank 15), while Brock Bowers faces LA allowing 8.3 (rank 31), making McBride's matchup easier.
  5. Weekly opportunity [favours Trey McBride, weak, model] (queries 3): Both players have identical 10.8 targets per game, but Trey McBride has a higher average snap share (90.5% vs 82.2%) and a slightly higher average target share (29.7% vs 29.3%), while Brock Bowers has a higher average PPR points per game (20.6 vs 17.2).

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Trey McBride: ARI, TE, roster status ACT (week 7).  (queries 1)
  2. Brock Bowers: LV, TE, 82.2 PPR points this season.  (queries 2)
  3. Trey McBride has a 29.7% average target share compared to Brock Bowers's 29.3%, making this factor level per the code rule.  (queries 4)
  4. Brock Bowers averaged 18.2 PPR points per game in later weeks compared to Trey McBride's 14.7, making Bowers the stronger start based on recent trend.  (queries 5)
  5. Trey McBride has 17.5% of his PPR points from touchdowns compared to Brock Bowers's 21.9%, making McBride less touchdown-dependent and steadier.  (queries 6)
  6. Trey McBride faces DEN allowing 13.2 PPR points per game to TEs (rank 15), while Brock Bowers faces LA allowing 8.3 (rank 31), making McBride's matchup easier.  (queries 7)
  7. Both players have identical 10.8 targets per game, but Trey McBride has a higher average snap share (90.5% vs 82.2%) and a slightly higher average target share (29.7% vs 29.3%), while Brock Bowers has a higher average PPR points per game (20.6 vs 17.2).  (queries 3)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND REGEXP_REPLACE(LOWER(full_name), ' (jr|sr|ii|iii|iv)[.]?$', '') IN ('trey mcbride', 'who should', 'should i', 'i start', 'start trey', 'mcbride or', 'or bowers', 'bowers for', 'for week', 'who should i', 'should i start', 'i start trey', 'start trey mcbride', 'trey mcbride or', 'mcbride or bowers', 'or bowers for', 'bowers for week') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0037744 | Trey McBride | ARI | TE | ACT | 7
  [2] skill players with the last name Bowers
      WITH latest AS (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND position IN ('QB', 'RB', 'WR', 'TE') AND (LOWER(full_name) LIKE '% bowers' OR LOWER(full_name) LIKE '% bowers %') GROUP BY gsis_id), pts AS (SELECT player_id, ROUND(SUM(fantasy_points_ppr), 1) AS season_points FROM NFLVERSE.player_stats WHERE season = 2026 GROUP BY player_id) SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week, p.season_points AS season_ppr_points FROM NFLVERSE.rosters r JOIN latest l ON r.gsis_id = l.gsis_id AND r.week = l.week LEFT JOIN pts p ON p.player_id = r.gsis_id WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week | season_ppr_points
      00-0039338 | Brock Bowers | LV | TE | ACT | 7 | 82.2
  [3] Trey McBride vs Brock Bowers: snap %, targets, target share and PPR points by week
      SELECT ps.player_display_name AS player, ps.week, ps.opponent_team, ROUND(100 * sc.offense_pct, 1) AS snap_pct, ps.targets, ROUND(100 * ps.target_share, 1) AS target_share_pct, ps.receptions, ps.carries, ROUND(ps.fantasy_points_ppr, 1) AS ppr_points FROM NFLVERSE.player_stats ps LEFT JOIN NFLVERSE.snap_counts sc ON sc.game_id = ps.game_id AND sc.player = ps.player_display_name AND sc.team = ps.team WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') ORDER BY ps.player_display_name, ps.week
      player | week | opponent_team | snap_pct | targets | target_share_pct | receptions | carries | ppr_points
      Brock Bowers | 3 | NO | 79.0 | 13 | 43.3 | 10 | 0 | 27.6
      Brock Bowers | 4 | KC | 82.0 | 11 | 22.9 | 6 | 0 | 20.6
      Brock Bowers | 5 | NE | 70.0 | 10 | 27.8 | 8 | 0 | 23.0
      Brock Bowers | 6 | BUF | 98.0 | 9 | 23.1 | 4 | 0 | 11.0
      Trey McBride | 1 | LAC | 80.0 | 13 | 35.1 | 9 | 0 | 24.5
      Trey McBride | 2 | SEA | 88.0 | 10 | 38.5 | 8 | 0 | 18.1
      Trey McBride | 3 | SF | 91.0 | 11 | 22.0 | 9 | 0 | 16.5
      Trey McBride | 4 | NYG | 97.0 | 12 | 34.3 | 7 | 0 | 10.1
      Trey McBride | 5 | DET | 90.0 | 10 | 21.7 | 9 | 0 | 21.6
      Trey McBride | 6 | LA | 97.0 | 9 | 26.5 | 7 | 0 | 12.3
  [4] Trey McBride vs Brock Bowers: share of their team's targets and air yards, and PPR points per game
      SELECT ps.player_display_name AS player, ps.team, COUNT(*) AS games, SUM(ps.targets) AS targets, ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, ROUND(100 * AVG(ps.air_yards_share), 1) AS avg_air_yards_share_pct, SUM(ps.carries) AS carries, ROUND(AVG(ps.fantasy_points_ppr), 1) AS ppr_per_game FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') GROUP BY ps.player_display_name, ps.team ORDER BY ps.player_display_name
      player | team | games | targets | avg_target_share_pct | avg_air_yards_share_pct | carries | ppr_per_game
      Brock Bowers | LV | 4 | 43 | 29.3 | 33.9 | 0 | 20.6
      Trey McBride | ARI | 6 | 65 | 29.7 | 23.8 | 0 | 17.2
  [5] Trey McBride vs Brock Bowers: PPR points per game and target share in weeks 1-3 vs 4-6
      SELECT ps.player_display_name AS player, 3 AS split_week, SUM(CASE WHEN ps.week <= 3 THEN 1 ELSE 0 END) AS early_games, SUM(CASE WHEN ps.week > 3 THEN 1 ELSE 0 END) AS late_games, ROUND(AVG(CASE WHEN ps.week <= 3 THEN ps.fantasy_points_ppr END), 1) AS early_ppr_per_game, ROUND(AVG(CASE WHEN ps.week > 3 THEN ps.fantasy_points_ppr END), 1) AS late_ppr_per_game, ROUND(100 * AVG(CASE WHEN ps.week <= 3 THEN ps.target_share END), 1) AS early_target_share_pct, ROUND(100 * AVG(CASE WHEN ps.week > 3 THEN ps.target_share END), 1) AS late_target_share_pct FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') GROUP BY ps.player_display_name ORDER BY ps.player_display_name
      player | split_week | early_games | late_games | early_ppr_per_game | late_ppr_per_game | early_target_share_pct | late_target_share_pct
      Brock Bowers | 3 | 1 | 3 | 27.6 | 18.2 | 43.3 | 24.6
      Trey McBride | 3 | 3 | 3 | 19.7 | 14.7 | 31.9 | 27.5
  [6] Trey McBride vs Brock Bowers: touchdowns and the share of PPR points that came from them
      SELECT ps.player_display_name AS player, SUM(ps.receiving_tds + ps.rushing_tds) AS touchdowns, 6 * SUM(ps.receiving_tds + ps.rushing_tds) AS td_points, ROUND(SUM(ps.fantasy_points_ppr), 1) AS ppr_points, ROUND(100 * 6 * SUM(ps.receiving_tds + ps.rushing_tds) / NULLIF(SUM(ps.fantasy_points_ppr), 0), 1) AS td_share_pct FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') GROUP BY ps.player_display_name ORDER BY ps.player_display_name
      player | touchdowns | td_points | ppr_points | td_share_pct
      Brock Bowers | 3 | 18 | 82.2 | 21.9
      Trey McBride | 3 | 18 | 103.1 | 17.5
  [7] Trey McBride vs Brock Bowers: week 7 opponent and its average PPR points allowed per game to the position (rank 1 = most allowed)
      WITH players AS (SELECT '00-0037744' AS player_id, 'Trey McBride' AS player, 'ARI' AS team, 'TE' AS position UNION ALL SELECT '00-0039338' AS player_id, 'Brock Bowers' AS player, 'LV' AS team, 'TE' AS position), games AS (SELECT home_team AS team, away_team AS opponent, week, home_score FROM NFLVERSE.schedules WHERE season = 2026 UNION ALL SELECT away_team AS team, home_team AS opponent, week, home_score FROM NFLVERSE.schedules WHERE season = 2026), target AS (SELECT DISTINCT team, 7 AS week FROM players), allowed AS (SELECT opponent_team, position, week, SUM(fantasy_points_ppr) AS pts FROM NFLVERSE.player_stats WHERE season = 2026 GROUP BY opponent_team, position, week), avg_allowed AS (SELECT opponent_team, position, ROUND(AVG(pts), 1) AS avg_ppr_allowed, COUNT(*) AS opp_games FROM allowed GROUP BY opponent_team, position), ranked AS (SELECT opponent_team, position, avg_ppr_allowed, opp_games, RANK() OVER (PARTITION BY position ORDER BY avg_ppr_allowed DESC) AS allowed_rank, COUNT(*) OVER (PARTITION BY position) AS teams_ranked FROM avg_allowed) SELECT p.player, p.team, p.position, t.week AS game_week, g.opponent, CASE WHEN g.home_score IS NULL THEN 0 ELSE 1 END AS played, r.avg_ppr_allowed AS opp_avg_ppr_allowed, r.allowed_rank, r.teams_ranked, r.opp_games FROM players p LEFT JOIN target t ON t.team = p.team LEFT JOIN games g ON g.team = p.team AND g.week = t.week LEFT JOIN ranked r ON r.opponent_team = g.opponent AND r.position = p.position ORDER BY p.player
      player | team | position | game_week | opponent | played | opp_avg_ppr_allowed | allowed_rank | teams_ranked | opp_games
      Brock Bowers | LV | TE | 7 | LA | 0 | 8.3 | 31 | 32 | 6
      Trey McBride | ARI | TE | 7 | DEN | 0 | 13.2 | 15 | 32 | 6
```
