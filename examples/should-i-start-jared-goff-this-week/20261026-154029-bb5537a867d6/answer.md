```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  factors by model: Depth chart, Next matchup, Points per game
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: model, model, model
Timings: total 70.8s; analyst 14.5s, critic 55.1s, factor_agent 1.9s, planner 0.6s (busy time; factor agents run in parallel)

Question: Should I start Jared Goff this week?
Run bb5537a867d6: 5 queries, 3 critic rounds, 70.8s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

Answer before the critic:
Start Jared Goff. Jared Goff's 23.0 PPR points per game this season are driven by a strong opportunity factor, averaging 24.9 fantasy points per game over 5 games with 12 passing and 1 rushing touchdown. However, his week 7 matchup against GB is a significant liability, as GB allows 12.1 PPR points per game to QBs, ranking 28th of 32 (tough matchup). The tough matchup outweighs his scoring output, making him a risky start despite his role as the Lions' clear QB1.

Critic rounds:
  Round 1: needs_revision (review: model), 2 blocking of 2 issues
    - [blocking] numbers in answer: 24.9 is not in the cited rows or the facts computed from them.
      claim: Jared Goff's 23.0 PPR points per game this season are driven by a strong opportunity factor, averaging 24.9 fantasy points per game over 5 games with 12 passing and 1 rushing touchdown.
    - [blocking] model_review in answer: The facts state Jared Goff has 23 PPR points per game over 5 games. The average of 24.9 fantasy points per game is not supported by the given facts.
      claim: Jared Goff's 23.0 PPR points per game this season are driven by a strong opportunity factor, averaging 24.9 fantasy points per game over 5 games
  Round 2: needs_revision (review: model), 1 blocking of 4 issues
    - [blocking] question_fit in answer: A start/sit answer should open with one of: Start, Sit, Bench.
      claim: Hold Jared Goff.
    - [recorded] model_review in answer: The facts state Jared Goff has 23 PPR points per game over 5 games. The average of 24.9 fantasy points per game is not supported by the given facts.
      claim: Jared Goff's 23.0 PPR points per game this season are driven by a strong opportunity factor, averaging 24.9 fantasy points per game over 5 games
    - [recorded] model_review in answer: The facts state that GB's rank 28 of 32 against QBs means they are a tough matchup (rank 1 allows the most points; 1-10 favorable, 11-22 neutral, 23-32 tough). The numerical threshold 12.1 PPR points per game does not map to this scale, and the claim that it makes the matchup "tough" contradicts the given scale logic.
      claim: GB is a tough matchup for Jared Goff because they allow 12.1 PPR points per game to QBs (rank 28th of 32)
    - [recorded] model_review in answer: The facts state that rank 28 of 32 against QBs (allowing 12.1 PPR) is a "tough matchup" per the provided scale (1-10 favorable, 11-22 neutral, 23-32 tough). A defense allowing 12.1 PPR to QBs should be classified as at least neutral, if not favorable, under that scale logic.
      claim: Jared Goff averages 23 PPR points per game over 5 games with 12 passing and 1 rushing touchdown, which is moderate production against a top-32 defense
  Round 3: approved (review: model), 0 blocking of 2 issues
    - [recorded] model_review in answer: The facts state that GB's rank 28 of 32 against QBs (allowing 12.1 PPR) means they are a tough matchup (rank 1 allows the most points; 1-10 favorable, 11-22 neutral, 23-32 tough). However, rank 28 is at the bottom of the 23-32 range, and the numerical threshold 12.1 PPR points per game does not map cleanly to the provided scale logic where rank 28 would typically be considered at least neutral. The claim that it is a "tough" matchup contradicts the scale's intent when rank 28 sits near the worst possible ranking.
      claim: Jared Goff faces a tough matchup against GB (rank 28 of 32 against QBs allowing 12.1 PPR)
    - [recorded] model_review in answer: The facts state Jared Goff has 23 PPR points per game over 5 games. The average of 24.9 fantasy points per game is not supported by the given facts.
      claim: Jared Goff's 23.0 PPR points per game this season are driven by a strong opportunity factor, averaging 24.9 fantasy points per game over 5 games

Final answer (approved; model verdict):
Start Jared Goff. Jared Goff faces a tough matchup against GB (rank 28 of 32 against QBs allowing 12.1 PPR), but he is the clear QB1 on the Lions' depth chart with no injury concerns. Over 5 games this season, Goff averages 23 PPR points per game with 12 passing and 1 rushing touchdown, providing moderate production despite the opponent's defensive ranking.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Depth chart [strong, model] (queries 4): Jared Goff is the clear QB1 on the Lions' depth chart, with Joshua Dobbs as the only listed backup, indicating he is the primary starter.
  2. Next matchup [strong, model] (queries 5): Jared Goff faces GB in week 7, who allow 12.1 PPR points per game to QBs, ranking 28th of 32 (tough matchup).
  3. Points per game [moderate, model] (queries 3): Goff averages 23 PPR points per game over 5 games with 12 passing and 1 rushing touchdown.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Jared Goff: DET, QB, roster status ACT (week 7).  (queries 1)
  2. Jared Goff is the clear QB1 on the Lions' depth chart, with Joshua Dobbs as the only listed backup, indicating he is the primary starter.  (queries 4)
  3. Jared Goff faces GB in week 7, who allow 12.1 PPR points per game to QBs, ranking 28th of 32 (tough matchup).  (queries 5)
  4. Goff averages 23 PPR points per game over 5 games with 12 passing and 1 rushing touchdown.  (queries 3)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND REGEXP_REPLACE(LOWER(full_name), ' (jr|sr|ii|iii|iv)[.]?$', '') IN ('jared goff', 'should i', 'i start', 'start jared', 'goff this', 'this week', 'should i start', 'i start jared', 'start jared goff', 'jared goff this', 'goff this week') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0033106 | Jared Goff | DET | QB | ACT | 7
  [2] Jared Goff: injury report entries this season
      SELECT week, report_status, report_primary_injury, practice_status FROM NFLVERSE.injuries WHERE season = 2026 AND gsis_id = '00-0033106' ORDER BY week
      week | report_status | report_primary_injury | practice_status
  [3] Jared Goff: games, passing and rushing touchdowns and PPR points per game this season
      SELECT player_display_name, position, COUNT(*) AS games, SUM(passing_yards) AS passing_yards, SUM(passing_tds) AS passing_tds, SUM(rushing_tds) AS rushing_tds, ROUND(AVG(fantasy_points_ppr), 1) AS ppr_per_game FROM NFLVERSE.player_stats WHERE season = 2026 AND player_id = '00-0033106' GROUP BY player_display_name, position
      player_display_name | position | games | passing_yards | passing_tds | rushing_tds | ppr_per_game
      Jared Goff | QB | 5 | 1485 | 12 | 1 | 23.0
  [4] DET current QB depth chart (pos_rank 1 = top), with roster status and the week 7 injury report
      SELECT DISTINCT d.pos_abb, d.pos_rank, d.player_name, r.status AS roster_status, i.report_status FROM NFLVERSE.depth_charts d LEFT JOIN (SELECT gsis_id, MAX(status) AS status FROM NFLVERSE.rosters WHERE season = 2026 AND week = (SELECT MAX(week) FROM NFLVERSE.rosters WHERE season = 2026) GROUP BY gsis_id) r ON r.gsis_id = d.gsis_id LEFT JOIN (SELECT gsis_id, MAX(report_status) AS report_status FROM NFLVERSE.injuries WHERE season = 2026 AND week = 7 GROUP BY gsis_id) i ON i.gsis_id = d.gsis_id WHERE d.team = 'DET' AND d.pos_abb = 'QB' AND d.dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = 'DET') ORDER BY d.pos_rank LIMIT 25
      pos_abb | pos_rank | player_name | roster_status | report_status
      QB | 1 | Jared Goff | ACT | 
      QB | 2 | Joshua Dobbs | ACT | 
  [5] Jared Goff: week 7 opponent and its average PPR points allowed per game to the position (rank 1 = most allowed)
      WITH players AS (SELECT '00-0033106' AS player_id, 'Jared Goff' AS player, 'DET' AS team, 'QB' AS position, 'ACT' AS roster_status), games AS (SELECT home_team AS team, away_team AS opponent, week, home_score FROM NFLVERSE.schedules WHERE season = 2026 UNION ALL SELECT away_team AS team, home_team AS opponent, week, home_score FROM NFLVERSE.schedules WHERE season = 2026), target AS (SELECT DISTINCT team, 7 AS week FROM players), allowed AS (SELECT opponent_team, position, week, SUM(fantasy_points_ppr) AS pts FROM NFLVERSE.player_stats WHERE season = 2026 GROUP BY opponent_team, position, week), avg_allowed AS (SELECT opponent_team, position, ROUND(AVG(pts), 1) AS avg_ppr_allowed, COUNT(*) AS opp_games FROM allowed GROUP BY opponent_team, position), ranked AS (SELECT opponent_team, position, avg_ppr_allowed, opp_games, RANK() OVER (PARTITION BY position ORDER BY avg_ppr_allowed DESC) AS allowed_rank, COUNT(*) OVER (PARTITION BY position) AS teams_ranked FROM avg_allowed) SELECT p.player, p.team, p.position, t.week AS game_week, g.opponent, CASE WHEN g.home_score IS NULL THEN 0 ELSE 1 END AS played, r.avg_ppr_allowed AS opp_avg_ppr_allowed, r.allowed_rank, r.teams_ranked, r.opp_games, p.roster_status, i.report_status, i.report_primary_injury FROM players p LEFT JOIN target t ON t.team = p.team LEFT JOIN (SELECT gsis_id, week, MAX(report_status) AS report_status, MAX(report_primary_injury) AS report_primary_injury FROM NFLVERSE.injuries WHERE season = 2026 GROUP BY gsis_id, week) i ON i.gsis_id = p.player_id AND i.week = t.week LEFT JOIN games g ON g.team = p.team AND g.week = t.week LEFT JOIN ranked r ON r.opponent_team = g.opponent AND r.position = p.position ORDER BY p.player
      player | team | position | game_week | opponent | played | opp_avg_ppr_allowed | allowed_rank | teams_ranked | opp_games | roster_status | report_status | report_primary_injury
      Jared Goff | DET | QB | 7 | GB | 0 | 12.1 | 28 | 32 | 6 | ACT |  | 
```
