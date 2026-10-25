```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  factors by model: Depth chart, Team usage, Games without the player
  factors by rules: none
  first verdict: model; final verdict: rule-based
  critic reviews: model, rule-based
Timings: total 292.4s; analyst 129.2s, critic 135.0s, factor_agent 43.0s, planner 8.9s (busy time; factor agents run in parallel)
Failed or skipped model calls: analyst revise (error, 90.0s); critic review (error, 90.0s)

Question: Who becomes the Bucs' WR1 if Mike Evans is out?
Run ddb115ab07ae: 5 queries, 2 critic rounds, 292.4s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

Premise correction: Mike Evans is on SF in the data (rosters, week 7), not TB.

Answer before the critic:
Start Deebo Samuel. Per the depth chart, if Mike Evans is out, Deebo Samuel becomes the 49ers' WR1. Samuel currently holds an 11.1% target share, behind Evans at 27.1%, Kittle at 24.9%, and McCaffrey at 22.8%, but the depth chart explicitly promotes him to the top role. This shift would likely increase his target share and red-zone usage, making him the primary passing option in Evans' absence.

Critic rounds:
  Round 1: needs_revision (review: model), 3 blocking of 3 issues
    - [blocking] verdict_support in answer: Deebo Samuel Sr.'s recent target share (11.1%) trails George Kittle (TE) 24.9% and Christian McCaffrey (RB) 22.8%, and is less than half of George Kittle's. A 'Start' must follow the usage numbers: recommend the player they back. The answer may still say who is next on the depth chart.
      claim: Start Deebo Samuel.
    - [blocking] model_review in answer: The depth chart lists Mike Evans as WR1 (rank 1) and Deebo Samuel as WR2 (rank 2); Evans remains the top-ranked receiver on the depth chart, so Samuel is not promoted to WR1 per the depth chart.
      claim: Per the depth chart, if Mike Evans is out, Deebo Samuel becomes the 49ers' WR1.
    - [blocking] model_review in answer: The depth chart has Evans at position 1 and Samuel at position 2; Evans is still the top role, and Samuel is second.
      claim: the depth chart explicitly promotes him to the top role.
  Round 2: approved (review: rule-based), 0 blocking of 0 issues

Final answer (approved; rule-based verdict):
Pick up George Kittle if available. Most supported by the data: Depth chart (strong): If Mike Evans (position 1) is out, Deebo Samuel (position 2) becomes the 49ers' WR1. Not supported: Team usage, Games without the player. George Kittle (TE) has the top recent target share among his teammates (24.9%). He averages 15 PPR points per game this season. The depth chart lists Deebo Samuel next at WR. (Rule-based verdict: the verdict model call failed, so fixed thresholds were applied.)

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Depth chart [strong, model] (queries 4): If Mike Evans (position 1) is out, Deebo Samuel (position 2) becomes the 49ers' WR1.
  2. Team usage [not supported, model] (queries 3): Mike Evans has the highest target share at 27.1%, followed by Kittle at 24.9%, McCaffrey at 22.8%, and Samuel at 11.1%, but the facts do not indicate who becomes the 49ers' WR1 if Evans is out.
  3. Games without the player [not supported, model] (queries 5): 0 games missed this season; no comparative data exists for his absence.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Mike Evans: SF, WR, roster status ACT (week 7).  (queries 1)
  2. Latest injury report: week 7, no game status; Did Not Participate In Practice.  (queries 2)
  3. If Mike Evans (position 1) is out, Deebo Samuel (position 2) becomes the 49ers' WR1.  (queries 4)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('mike evans', 'who becomes', 'becomes the', 'the bucs', 'bucs wr', 'wr if', 'if mike', 'evans is', 'is out', 'who becomes the', 'becomes the bucs', 'the bucs wr', 'bucs wr if', 'wr if mike', 'if mike evans', 'mike evans is', 'evans is out') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0031408 | Mike Evans | SF | WR | ACT | 7
  [2] Mike Evans: injury report entries this season
      SELECT week, report_status, report_primary_injury, practice_status FROM NFLVERSE.injuries WHERE season = 2026 AND gsis_id = '00-0031408' ORDER BY week
      week | report_status | report_primary_injury | practice_status
      3 | Questionable | Hip | Limited Participation in Practice
      4 | Questionable | Ribs | Limited Participation in Practice
      5 |  |  | Limited Participation in Practice
      6 | Questionable | Ribs | Did Not Participate In Practice
      7 |  |  | Did Not Participate In Practice
  [3] SF RB/WR/TE usage this season and in weeks 5-6
      SELECT player_display_name, position, COUNT(*) AS games, SUM(targets) AS targets, ROUND(100 * AVG(target_share), 1) AS avg_target_share_pct, ROUND(100 * AVG(CASE WHEN week >= 5 THEN target_share END), 1) AS recent_target_share_pct, SUM(carries) AS carries, ROUND(AVG(fantasy_points_ppr), 1) AS ppr_per_game FROM NFLVERSE.player_stats WHERE season = 2026 AND team = 'SF' AND position IN ('RB', 'WR', 'TE') GROUP BY player_display_name, position ORDER BY targets DESC LIMIT 12
      player_display_name | position | games | targets | avg_target_share_pct | recent_target_share_pct | carries | ppr_per_game
      Mike Evans | WR | 6 | 39 | 23.3 | 27.1 | 0 | 14.8
      George Kittle | TE | 6 | 36 | 21.9 | 24.9 | 0 | 15.0
      Christian McCaffrey | RB | 6 | 35 | 20.8 | 22.8 | 77 | 20.3
      Deebo Samuel Sr. | WR | 5 | 20 | 14.3 | 11.1 | 9 | 12.1
      Demarcus Robinson | WR | 2 | 6 | 11.6 |  | 0 | 9.7
      Brandin Cooks | WR | 3 | 5 | 5.9 | 7.2 | 0 | 3.3
      Jacob Cowing | WR | 6 | 5 | 3.1 | 3.7 | 1 | 0.4
      Luke Farrell | TE | 6 | 4 | 2.2 | 1.9 | 0 | 0.7
      Jordan Watkins | WR | 2 | 3 | 5.6 | 3.4 | 0 | 5.6
      Kaelon Black | RB | 6 | 3 | 1.7 | 1.7 | 45 | 3.3
      KhaDarel Hodge | WR | 3 | 1 | 1.6 |  | 0 | 0.9
      Brayden Willis | TE | 4 | 0 | 0.0 | 0.0 | 0 | 0.0
  [4] SF current WR depth chart (pos_rank 1 = top)
      SELECT DISTINCT pos_abb, pos_rank, player_name FROM NFLVERSE.depth_charts WHERE team = 'SF' AND pos_abb = 'WR' AND dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = 'SF') ORDER BY pos_rank LIMIT 25
      pos_abb | pos_rank | player_name
      WR | 1 | Mike Evans
      WR | 2 | Deebo Samuel
      WR | 3 | Brandin Cooks
      WR | 4 | Jordan Watkins
      WR | 5 | Jacob Cowing
      WR | 6 | Christian Kirk
      WR | 7 | Demarcus Robinson
      WR | 8 | De'Zhaun Stribling
      WR | 9 | Ricky Pearsall
      WR | 10 | Brandon Aiyuk
  [5] SF RB/WR/TE targets in games Mike Evans missed vs games he played this season
      WITH team_games AS (SELECT game_id FROM NFLVERSE.schedules WHERE season = 2026 AND (home_team = 'SF' OR away_team = 'SF') AND home_score IS NOT NULL), played AS (SELECT DISTINCT game_id FROM NFLVERSE.player_stats WHERE season = 2026 AND player_id = '00-0031408'), missed AS (SELECT g.game_id FROM team_games g LEFT JOIN played p ON p.game_id = g.game_id WHERE p.game_id IS NULL) SELECT CASE WHEN m.game_id IS NULL THEN 'played' ELSE 'missed' END AS player_status, ps.player_display_name, ps.position, COUNT(*) AS games, SUM(ps.targets) AS targets, ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, ROUND(AVG(ps.fantasy_points_ppr), 1) AS ppr_per_game FROM NFLVERSE.player_stats ps JOIN team_games g ON g.game_id = ps.game_id LEFT JOIN missed m ON m.game_id = ps.game_id WHERE ps.season = 2026 AND ps.team = 'SF' AND ps.player_id <> '00-0031408' AND ps.position IN ('RB', 'WR', 'TE') GROUP BY CASE WHEN m.game_id IS NULL THEN 'played' ELSE 'missed' END, ps.player_display_name, ps.position ORDER BY player_status, targets DESC LIMIT 30
      player_status | player_display_name | position | games | targets | avg_target_share_pct | ppr_per_game
      played | George Kittle | TE | 6 | 36 | 21.9 | 15.0
      played | Christian McCaffrey | RB | 6 | 35 | 20.8 | 20.3
      played | Deebo Samuel Sr. | WR | 5 | 20 | 14.3 | 12.1
      played | Demarcus Robinson | WR | 2 | 6 | 11.6 | 9.7
      played | Jacob Cowing | WR | 6 | 5 | 3.1 | 0.4
      played | Brandin Cooks | WR | 3 | 5 | 5.9 | 3.3
      played | Luke Farrell | TE | 6 | 4 | 2.2 | 0.7
      played | Jordan Watkins | WR | 2 | 3 | 5.6 | 5.6
      played | Kaelon Black | RB | 6 | 3 | 1.7 | 3.3
      played | KhaDarel Hodge | WR | 3 | 1 | 1.6 | 0.9
      played | Brayden Willis | TE | 4 | 0 | 0.0 | 0.0
      played | Jordan James | RB | 3 | 0 | 0.0 | 0.5
```
