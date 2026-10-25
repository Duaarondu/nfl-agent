```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Weekly opportunity, Next matchup, Team usage share, Recent trend, Touchdown share
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: rule-based, model
Timings: total 79.2s; analyst 45.8s, critic 31.6s, factor_agent 3.1s, planner 1.1s (busy time; factor agents run in parallel)

Question: Start McBride or Brock Bowers?
Run 9fff19ee315b: 6 queries, 2 critic rounds, 79.2s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for mcbride-bowers-1: PPR scoring; roster: none (0 memories retrieved)

Answer before the critic:
Start Trey McBride over Brock Bowers. McBride's moderate advantage in target share (29.7% vs 29.3%) and touchdown dependency (17.5% vs 21.9%) is outweighed by Bowers's tough matchup against the LA defense (rank 31, 8.3 PPR allowed to TEs), while McBride faces a much friendlier DEN defense (rank 15, 13.2 PPR allowed). McBride's more stable recent form and better defensive matchup make him the stronger start for week 7.

Critic rounds:
  Round 1: needs_revision (review: rule-based), 1 blocking of 3 issues
    - [recorded] numbers in factor:Weekly opportunity: 3.4 is not in the cited rows or the facts computed from them.
      claim: Bowers averages 20.6 PPR points per game on 10.8 targets, while McBride averages 17.2 PPR points per game on 10.8 targets, giving Bowers a 3.4-point weekly advantage.
    - [recorded] numbers in factor:Team usage share: 0.4 is not in the cited rows or the facts computed from them.
      claim: McBride has a 0.4% higher average target share (29.7% vs 29.3%) and a 10.1% lower average air yards share (23.8% vs 33.9%), indicating greater red-zone involvement per target.
    - [blocking] compare in answer: The head-to-head numbers favour Brock Bowers: Trey McBride averages 17.2 PPR points per game to Brock Bowers's 20.6, and 14.7 to 18.2 in the later weeks.
      claim: Start Trey McBride over Brock Bowers.
  Round 2: approved (review: model), 0 blocking of 3 issues
    - [recorded] numbers in factor:Weekly opportunity: 3.4 is not in the cited rows or the facts computed from them.
      claim: Bowers averages 20.6 PPR points per game on 10.8 targets, while McBride averages 17.2 PPR points per game on 10.8 targets, giving Bowers a 3.4-point weekly advantage.
    - [recorded] numbers in factor:Team usage share: 0.4 is not in the cited rows or the facts computed from them.
      claim: McBride has a 0.4% higher average target share (29.7% vs 29.3%) and a 10.1% lower average air yards share (23.8% vs 33.9%), indicating greater red-zone involvement per target.
    - [recorded] model_review in answer: The head-to-head average PPR points per game favor Brock Bowers (20.6) over Trey McBride (17.2). Over the most recent stretch (weeks 4-6), Bowers averages 18.2 PPR points per game compared to McBride's 14.7. While Bowers has a better seasonal average, McBride's significantly easier matchup (DEN rank 15, 13.2 PPR allowed vs LA rank 31, 8.3 PPR allowed) and the narrowing production gap in recent weeks weaken the case for Bowers as the stronger start despite the defensive disparity.
      claim: Despite McBride's easier defensive matchup, Bowers's higher weekly production and consistent 10.8-target workload make him the stronger start.

Final answer (approved; model verdict):
Start Brock Bowers over Trey McBride. Bowers holds a head-to-head PPR advantage, averaging 20.6 points per game to McBride's 17.2, and 18.2 to McBride's 14.7 over the later weeks. Despite McBride's easier defensive matchup, Bowers's higher weekly production and consistent 10.8-target workload make him the stronger start.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Weekly opportunity [favours Brock Bowers, strong, model] (queries 2): Bowers averages 20.6 PPR points per game on 10.8 targets, while McBride averages 17.2 PPR points per game on 10.8 targets, giving Bowers a 3.4-point weekly advantage.
  2. Next matchup [favours Trey McBride, strong, model] (queries 6): McBride faces a significantly easier matchup, with DEN allowing 13.2 PPR to TEs (rank 15) compared to LA's 8.3 PPR allowed (rank 31) for Bowers.
  3. Team usage share [favours Trey McBride, moderate, model] (queries 3): McBride has a 0.4% higher average target share (29.7% vs 29.3%) and a 10.1% lower average air yards share (23.8% vs 33.9%), indicating greater red-zone involvement per target.
  4. Recent trend [favours Brock Bowers, moderate, model] (queries 4): Brock Bowers averaged 27.6 PPR points per game in weeks 1-3 compared to Trey McBride's 19.7, but Bowers's target share dropped from 43.3% to 24.6% while McBride's declined only from 31.9% to 27.5%.
  5. Touchdown share [favours Trey McBride, moderate, model] (queries 5): McBride's 17.5% touchdown share is lower than Bowers's 21.9%, making him less touchdown-dependent for PPR points.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Brock Bowers: LV, TE, roster status ACT (week 7). Trey McBride: ARI, TE, roster status ACT (week 7).  (queries 1)
  2. Bowers averages 20.6 PPR points per game on 10.8 targets, while McBride averages 17.2 PPR points per game on 10.8 targets, giving Bowers a 3.4-point weekly advantage.  (queries 2)
  3. McBride faces a significantly easier matchup, with DEN allowing 13.2 PPR to TEs (rank 15) compared to LA's 8.3 PPR allowed (rank 31) for Bowers.  (queries 6)
  4. McBride has a 0.4% higher average target share (29.7% vs 29.3%) and a 10.1% lower average air yards share (23.8% vs 33.9%), indicating greater red-zone involvement per target.  (queries 3)
  5. Brock Bowers averaged 27.6 PPR points per game in weeks 1-3 compared to Trey McBride's 19.7, but Bowers's target share dropped from 43.3% to 24.6% while McBride's declined only from 31.9% to 27.5%.  (queries 4)
  6. McBride's 17.5% touchdown share is lower than Bowers's 21.9%, making him less touchdown-dependent for PPR points.  (queries 5)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('trey mcbride', 'start mcbride', 'mcbride or', 'or brock', 'brock bowers', 'start mcbride or', 'mcbride or brock', 'or brock bowers') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0039338 | Brock Bowers | LV | TE | ACT | 7
      00-0037744 | Trey McBride | ARI | TE | ACT | 7
  [2] Trey McBride vs Brock Bowers: snap %, targets, target share and PPR points by week
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
  [3] Trey McBride vs Brock Bowers: share of their team's targets and air yards, and PPR points per game
      SELECT ps.player_display_name AS player, ps.team, COUNT(*) AS games, SUM(ps.targets) AS targets, ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, ROUND(100 * AVG(ps.air_yards_share), 1) AS avg_air_yards_share_pct, SUM(ps.carries) AS carries, ROUND(AVG(ps.fantasy_points_ppr), 1) AS ppr_per_game FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') GROUP BY ps.player_display_name, ps.team ORDER BY ps.player_display_name
      player | team | games | targets | avg_target_share_pct | avg_air_yards_share_pct | carries | ppr_per_game
      Brock Bowers | LV | 4 | 43 | 29.3 | 33.9 | 0 | 20.6
      Trey McBride | ARI | 6 | 65 | 29.7 | 23.8 | 0 | 17.2
  [4] Trey McBride vs Brock Bowers: PPR points per game and target share in weeks 1-3 vs 4-6
      SELECT ps.player_display_name AS player, 3 AS split_week, SUM(CASE WHEN ps.week <= 3 THEN 1 ELSE 0 END) AS early_games, SUM(CASE WHEN ps.week > 3 THEN 1 ELSE 0 END) AS late_games, ROUND(AVG(CASE WHEN ps.week <= 3 THEN ps.fantasy_points_ppr END), 1) AS early_ppr_per_game, ROUND(AVG(CASE WHEN ps.week > 3 THEN ps.fantasy_points_ppr END), 1) AS late_ppr_per_game, ROUND(100 * AVG(CASE WHEN ps.week <= 3 THEN ps.target_share END), 1) AS early_target_share_pct, ROUND(100 * AVG(CASE WHEN ps.week > 3 THEN ps.target_share END), 1) AS late_target_share_pct FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') GROUP BY ps.player_display_name ORDER BY ps.player_display_name
      player | split_week | early_games | late_games | early_ppr_per_game | late_ppr_per_game | early_target_share_pct | late_target_share_pct
      Brock Bowers | 3 | 1 | 3 | 27.6 | 18.2 | 43.3 | 24.6
      Trey McBride | 3 | 3 | 3 | 19.7 | 14.7 | 31.9 | 27.5
  [5] Trey McBride vs Brock Bowers: touchdowns and the share of PPR points that came from them
      SELECT ps.player_display_name AS player, SUM(ps.receiving_tds + ps.rushing_tds) AS touchdowns, 6 * SUM(ps.receiving_tds + ps.rushing_tds) AS td_points, ROUND(SUM(ps.fantasy_points_ppr), 1) AS ppr_points, ROUND(100 * 6 * SUM(ps.receiving_tds + ps.rushing_tds) / NULLIF(SUM(ps.fantasy_points_ppr), 0), 1) AS td_share_pct FROM NFLVERSE.player_stats ps WHERE ps.season = 2026 AND ps.player_id IN ('00-0037744', '00-0039338') GROUP BY ps.player_display_name ORDER BY ps.player_display_name
      player | touchdowns | td_points | ppr_points | td_share_pct
      Brock Bowers | 3 | 18 | 82.2 | 21.9
      Trey McBride | 3 | 18 | 103.1 | 17.5
  [6] Trey McBride vs Brock Bowers: next opponent after week 6 and its average PPR points allowed per game to the position (rank 1 = most allowed)
      WITH players AS (SELECT '00-0037744' AS player_id, 'Trey McBride' AS player, 'ARI' AS team, 'TE' AS position UNION ALL SELECT '00-0039338' AS player_id, 'Brock Bowers' AS player, 'LV' AS team, 'TE' AS position), games AS (SELECT home_team AS team, away_team AS opponent, week, home_score FROM NFLVERSE.schedules WHERE season = 2026 UNION ALL SELECT away_team AS team, home_team AS opponent, week, home_score FROM NFLVERSE.schedules WHERE season = 2026), target AS (SELECT team, MIN(week) AS week FROM games WHERE week > 6 GROUP BY team), allowed AS (SELECT opponent_team, position, week, SUM(fantasy_points_ppr) AS pts FROM NFLVERSE.player_stats WHERE season = 2026 GROUP BY opponent_team, position, week), avg_allowed AS (SELECT opponent_team, position, ROUND(AVG(pts), 1) AS avg_ppr_allowed, COUNT(*) AS opp_games FROM allowed GROUP BY opponent_team, position), ranked AS (SELECT opponent_team, position, avg_ppr_allowed, opp_games, RANK() OVER (PARTITION BY position ORDER BY avg_ppr_allowed DESC) AS allowed_rank, COUNT(*) OVER (PARTITION BY position) AS teams_ranked FROM avg_allowed) SELECT p.player, p.team, p.position, t.week AS game_week, g.opponent, CASE WHEN g.home_score IS NULL THEN 0 ELSE 1 END AS played, r.avg_ppr_allowed AS opp_avg_ppr_allowed, r.allowed_rank, r.teams_ranked, r.opp_games FROM players p LEFT JOIN target t ON t.team = p.team LEFT JOIN games g ON g.team = p.team AND g.week = t.week LEFT JOIN ranked r ON r.opponent_team = g.opponent AND r.position = p.position ORDER BY p.player
      player | team | position | game_week | opponent | played | opp_avg_ppr_allowed | allowed_rank | teams_ranked | opp_games
      Brock Bowers | LV | TE | 7 | LA | 0 | 8.3 | 31 | 32 | 6
      Trey McBride | ARI | TE | 7 | DEN | 0 | 13.2 | 15 | 32 | 6
```
