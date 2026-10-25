```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: keyword
  factors by model: none
  factors by rules: Opportunity, Team pass rate and game script, Big plays, Touchdowns and red zone, Teammate absences, Matchups
  first verdict: model; final verdict: model
  critic reviews: model
Timings: total 169.9s; analyst 114.8s, critic 21.0s, factor_agent 77.9s, planner 18.5s (busy time; factor agents run in parallel)
Failed or skipped model calls: planner classify (error, 18.5s); factor_agent:Touchdowns and red zone factor (error, 15.6s); factor_agent:Matchups factor (error, 15.6s); factor_agent:Team pass rate and game script factor (error, 15.6s); factor_agent:Big plays factor (error, 15.6s); factor_agent:Opportunity factor (error, 15.6s)

Question: Why is Christian Watson scoring so many fantasy points this season?
Run 1f70a86c1057: 8 queries, 1 critic rounds, 169.9s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

Answer before the critic:
Opportunity is the primary driver: an 80.3% average snap share and 22.2% target share over 6 games yield 19.8 PPR points per game (23.1 in weeks 1-3, 16.5 in weeks 4-6). A strong team pass rate of 67.5% average (76.2% in losses vs 63.2% in wins/ties) further inflates his target volume. Big-play ability cements the scoring, with 11.2 yards per target (10.6 early, 13.9 later), a 32.4% air yards share, and 10 plays of 20+ yards. Verdict: start Christian Watson.

Critic rounds:
  Round 1: approved (review: model), 0 blocking of 0 issues

Final answer (approved; model verdict):
Opportunity is the primary driver: an 80.3% average snap share and 22.2% target share over 6 games yield 19.8 PPR points per game (23.1 in weeks 1-3, 16.5 in weeks 4-6). A strong team pass rate of 67.5% average (76.2% in losses vs 63.2% in wins/ties) further inflates his target volume. Big-play ability cements the scoring, with 11.2 yards per target (10.6 early, 13.9 later), a 32.4% air yards share, and 10 plays of 20+ yards. Verdict: start Christian Watson.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Opportunity [strong, rule-based: average target share 22.2% (strong >= 22 with snap share >= 70%, moderate >= 15, weak >= 10)] (queries 3): 6 games, 48 targets, average snap share 80.3%, average target share 22.2%, 19.8 PPR points per game. Highest target share: week 2 (37.9%). Snap share: 82% in weeks 1-3 vs 78.7% in weeks 4-6. Target share: 25.8% in weeks 1-3 vs 18.6% in weeks 4-6. PPR points per game: 23.1 in weeks 1-3 vs 16.5 in weeks 4-6.
  2. Team pass rate and game script [strong, rule-based: PPR per game in above-average pass-rate weeks minus the rest: 11.8 (strong >= 5, moderate >= 2, weak > 0)] (queries 5): Average pass rate 67.5%; 2 losses, 4 wins or ties. Pass rate 76.2% in losses vs 63.2% in wins or ties. Pass rate: 72.3% in weeks 1-3 vs 62.8% in weeks 4-6.
  3. Big plays [strong, rule-based: 11.2 yards per target (strong >= 10, moderate >= 8.5, weak >= 7)] (queries 6): 538 receiving yards on 48 targets (11.2 yards per target); 10 plays of 20+ yards; longest 81. Average air yards share 32.4%. Yards per target: 10.6 in weeks 1-3 vs 13.9 in weeks 4-6.
  4. Touchdowns and red zone [moderate, rule-based: touchdowns are 30.3% of PPR points (strong >= 35, moderate >= 25, weak >= 15)] (queries 7): 6 touchdowns = 36 of 118.8 PPR points (30.3%). Scored in weeks: 1, 2, 3, 5. 7 of the team's 35 red-zone targets (20%); 0 red-zone carries.
  5. Teammate absences [not supported, rule-based: PPR per game in weeks with a teammate out minus other weeks: n/a (strong >= 5, moderate >= 2, weak > 0)] (queries -): Query failed; no data.
  6. Matchups [not supported, rule-based: PPR per game vs top-10 soft defenses minus the rest: -5.7 (strong >= 5, moderate >= 2, weak > 0)] (queries 8): Average opponent rank in PPR points allowed to the position: 15.2 of 32 (1 = most allowed). 16 PPR per game vs top-10 soft defenses (2 games), 21.7 vs the rest (4 games).

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Christian Watson: GB, WR, roster status ACT (week 7).  (queries 1)
  2. Latest injury report: week 7, no game status; Limited Participation in Practice.  (queries 2)
  3. 6 games, 48 targets, average snap share 80.3%, average target share 22.2%, 19.8 PPR points per game. Highest target share: week 2 (37.9%). Snap share: 82% in weeks 1-3 vs 78.7% in weeks 4-6. Target share: 25.8% in weeks 1-3 vs 18.6% in weeks 4-6. PPR points per game: 23.1 in weeks 1-3 vs 16.5 in weeks 4-6.  (queries 3)
  4. Average pass rate 67.5%; 2 losses, 4 wins or ties. Pass rate 76.2% in losses vs 63.2% in wins or ties. Pass rate: 72.3% in weeks 1-3 vs 62.8% in weeks 4-6.  (queries 5)
  5. 538 receiving yards on 48 targets (11.2 yards per target); 10 plays of 20+ yards; longest 81. Average air yards share 32.4%. Yards per target: 10.6 in weeks 1-3 vs 13.9 in weeks 4-6.  (queries 6)
  6. 6 touchdowns = 36 of 118.8 PPR points (30.3%). Scored in weeks: 1, 2, 3, 5. 7 of the team's 35 red-zone targets (20%); 0 red-zone carries.  (queries 7)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('why is', 'is christian', 'christian watson', 'watson scoring', 'scoring so', 'so many', 'many fantasy', 'fantasy points', 'points this', 'this season', 'why is christian', 'is christian watson', 'christian watson scoring', 'watson scoring so', 'scoring so many', 'so many fantasy', 'many fantasy points', 'fantasy points this', 'points this season') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0038124 | Christian Watson | GB | WR | ACT | 7
  [2] Christian Watson: injury report entries this season
      SELECT week, report_status, report_primary_injury, practice_status FROM NFLVERSE.injuries WHERE season = 2026 AND gsis_id = '00-0038124' ORDER BY week
      week | report_status | report_primary_injury | practice_status
      7 |  |  | Limited Participation in Practice
  [3] Christian Watson: snap %, targets, target share and PPR points by week
      SELECT ps.week, ps.opponent_team, sc.offense_snaps, ROUND(100 * sc.offense_pct, 1) AS snap_pct, ps.targets, ROUND(100 * ps.target_share, 1) AS target_share_pct, ps.receptions, ps.carries, ROUND(ps.fantasy_points_ppr, 1) AS ppr_points FROM NFLVERSE.player_stats ps LEFT JOIN NFLVERSE.snap_counts sc ON sc.game_id = ps.game_id AND sc.player = ps.player_display_name AND sc.team = ps.team WHERE ps.season = 2026 AND ps.player_id = '00-0038124' ORDER BY ps.week
      week | opponent_team | offense_snaps | snap_pct | targets | target_share_pct | receptions | carries | ppr_points
      1 | MIN | 52.0 | 76.0 | 8 | 20.0 | 6 | 0 | 32.7
      2 | NYJ | 53.0 | 90.0 | 11 | 37.9 | 4 | 0 | 14.1
      3 | ATL | 53.0 | 80.0 | 10 | 19.6 | 7 | 0 | 22.6
      4 | TB | 41.0 | 68.0 | 3 | 10.0 | 3 | 0 | 7.7
      5 | CHI | 49.0 | 80.0 | 8 | 25.8 | 6 | 0 | 32.3
      6 | DAL | 66.0 | 88.0 | 8 | 20.0 | 3 | 0 | 9.4
  [4] GB skill players listed Out or Doubtful, by week
      SELECT week, full_name, position, report_status, report_primary_injury FROM NFLVERSE.injuries WHERE season = 2026 AND team = 'GB' AND gsis_id <> '00-0038124' AND position IN ('QB', 'RB', 'WR', 'TE') AND report_status IN ('Out', 'Doubtful') ORDER BY week, position, full_name LIMIT 50
      ERROR: Cannot reach https://new-ui.dbc6c124-94f5-4ea0-a4d4-693b260d685d.cloud.zetaris.com: The read operation timed out
  [5] GB pass rate and final score margin by week
      SELECT p.week, MAX(p.defteam) AS opponent, SUM(p.pass) AS pass_plays, SUM(p.rush) AS rush_plays, ROUND(100 * SUM(p.pass) / NULLIF(SUM(p.pass) + SUM(p.rush), 0), 1) AS pass_rate_pct, MAX(CASE WHEN s.home_team = 'GB' THEN s.home_score - s.away_score ELSE s.away_score - s.home_score END) AS final_margin FROM NFLVERSE.pbp p JOIN NFLVERSE.schedules s ON s.game_id = p.game_id WHERE p.season = 2026 AND p.posteam = 'GB' GROUP BY p.week ORDER BY p.week
      week | opponent | pass_plays | rush_plays | pass_rate_pct | final_margin
      1 | MIN | 46.0 | 22.0 | 67.6 | -17
      2 | NYJ | 38.0 | 21.0 | 64.4 | 3
      3 | ATL | 56.0 | 10.0 | 84.8 | -21
      4 | TB | 34.0 | 23.0 | 59.6 | 3
      5 | CHI | 37.0 | 23.0 | 61.7 | 24
      6 | DAL | 49.0 | 24.0 | 67.1 | 10
  [6] Christian Watson: air yards, yards per target and 20+ yard plays by week
      SELECT ps.week, ps.targets, ps.receiving_yards, ROUND(ps.receiving_air_yards, 1) AS air_yards, ROUND(100 * ps.air_yards_share, 1) AS air_yards_share_pct, ROUND(ps.receiving_yards / NULLIF(ps.targets, 0), 1) AS yards_per_target, COALESCE(b.plays_20_plus, 0) AS plays_20_plus, b.longest_play FROM NFLVERSE.player_stats ps LEFT JOIN (SELECT game_id, SUM(CASE WHEN yards_gained >= 20 THEN 1 ELSE 0 END) AS plays_20_plus, MAX(yards_gained) AS longest_play FROM NFLVERSE.pbp WHERE season = 2026 AND play_type IN ('pass', 'run') AND (receiver_player_id = '00-0038124' OR rusher_player_id = '00-0038124') GROUP BY game_id) b ON b.game_id = ps.game_id WHERE ps.season = 2026 AND ps.player_id = '00-0038124' ORDER BY ps.week
      week | targets | receiving_yards | air_yards | air_yards_share_pct | yards_per_target | plays_20_plus | longest_play
      1 | 8 | 147 | 127 | 27.1 | 18.4 | 2 | 81.0
      2 | 11 | 41 | 86 | 39.8 | 3.7 | 1 | 20.0
      3 | 10 | 96 | 91 | 23.2 | 9.6 | 2 | 34.0
      4 | 3 | 47 | 23 | 10.7 | 15.7 | 0 | 18.0
      5 | 8 | 143 | 179 | 56.1 | 17.9 | 3 | 53.0
      6 | 8 | 64 | 145 | 37.5 | 8.0 | 2 | 28.0
  [7] Christian Watson: touchdowns, TD points vs PPR points, red-zone targets and carries by week
      SELECT ps.week, ps.receiving_tds, ps.rushing_tds, 6 * (ps.receiving_tds + ps.rushing_tds) AS td_points, ROUND(ps.fantasy_points_ppr, 1) AS ppr_points, COALESCE(rz.rz_targets, 0) AS rz_targets, COALESCE(rz.team_rz_targets, 0) AS team_rz_targets, COALESCE(rz.rz_carries, 0) AS rz_carries FROM NFLVERSE.player_stats ps LEFT JOIN (SELECT game_id, posteam, SUM(CASE WHEN receiver_player_id = '00-0038124' THEN 1 ELSE 0 END) AS rz_targets, SUM(CASE WHEN receiver_player_id IS NOT NULL THEN 1 ELSE 0 END) AS team_rz_targets, SUM(CASE WHEN rusher_player_id = '00-0038124' AND rush = 1 THEN 1 ELSE 0 END) AS rz_carries FROM NFLVERSE.pbp WHERE season = 2026 AND yardline_100 <= 20 AND play_type IN ('pass', 'run') GROUP BY game_id, posteam) rz ON rz.game_id = ps.game_id AND rz.posteam = ps.team WHERE ps.season = 2026 AND ps.player_id = '00-0038124' ORDER BY ps.week
      week | receiving_tds | rushing_tds | td_points | ppr_points | rz_targets | team_rz_targets | rz_carries
      1 | 2 | 0 | 12 | 32.7 | 1 | 7 | 0
      2 | 1 | 0 | 6 | 14.1 | 2 | 3 | 0
      3 | 1 | 0 | 6 | 22.6 | 3 | 8 | 0
      4 | 0 | 0 | 0 | 7.7 | 1 | 7 | 0
      5 | 2 | 0 | 12 | 32.3 | 0 | 6 | 0
      6 | 0 | 0 | 0 | 9.4 | 0 | 4 | 0
  [8] Christian Watson: PPR points by opponent, and each opponent's average PPR points allowed to WRs (rank 1 = most allowed)
      WITH allowed AS (SELECT opponent_team, week, SUM(fantasy_points_ppr) AS pts FROM NFLVERSE.player_stats WHERE season = 2026 AND position = 'WR' GROUP BY opponent_team, week), avg_allowed AS (SELECT opponent_team, ROUND(AVG(pts), 1) AS avg_ppr_allowed FROM allowed GROUP BY opponent_team), ranked AS (SELECT opponent_team, avg_ppr_allowed, RANK() OVER (ORDER BY avg_ppr_allowed DESC) AS allowed_rank FROM avg_allowed) SELECT ps.week, ps.opponent_team, ROUND(ps.fantasy_points_ppr, 1) AS ppr_points, r.avg_ppr_allowed AS opp_avg_ppr_allowed_to_wr, r.allowed_rank FROM NFLVERSE.player_stats ps LEFT JOIN ranked r ON r.opponent_team = ps.opponent_team WHERE ps.season = 2026 AND ps.player_id = '00-0038124' ORDER BY ps.week
      week | opponent_team | ppr_points | opp_avg_ppr_allowed_to_wr | allowed_rank
      1 | MIN | 32.7 | 27.1 | 28
      2 | NYJ | 14.1 | 30.5 | 21
      3 | ATL | 22.6 | 37.0 | 6
      4 | TB | 7.7 | 33.2 | 13
      5 | CHI | 32.3 | 32.5 | 16
      6 | DAL | 9.4 | 36.2 | 7
```
