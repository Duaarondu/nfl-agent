```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Depth chart, Games without the player
  factors by rules: Team usage
  first verdict: rule-based; final verdict: rule-based
  critic reviews: rule-based
Timings: total 238.5s; analyst 64.7s, critic 90.0s, factor_agent 103.2s, planner 22.7s (busy time; factor agents run in parallel)
Failed or skipped model calls: factor_agent:Team usage factor (error, 60.0s); analyst verdict (error, 60.0s); critic review (error, 90.0s)

Question: 12-team half-PPR, my TE is George Kittle and my WR is Davante Adams. Who becomes the Bucs' WR1 if Mike Evans is out?
Run 737f52e76684: 5 queries, 1 critic rounds, 238.5s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for demo: 12-team, half-PPR scoring; roster: George Kittle (SF, TE), Davante Adams (LA, WR) (4 memories retrieved)
[MEMORY CONTEXT]
## fantasy
- [WK] George Kittle (SF, TE) is on the user's roster. (entities: george kittle, george, kittle) <mem-e056c4b30e22>
- [WK] Davante Adams (LA, WR) is on the user's roster. (entities: davante adams, davante, adams) <mem-a50203748634>
- [WK] The user's league uses half-PPR scoring. (entities: ppr) <mem-93d88debe813>
- [WK] The user's league has 12 teams. <mem-9034ec3fad7e>
[/MEMORY CONTEXT]

Premise correction: Mike Evans is on SF in the data (rosters, week 7), not TB.

Answer before the critic:
Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey if available. Most supported by the data: Team usage (strong): Highest recent target share: Mike Evans (WR) 27.1%; George Kittle (TE) 24.9%; Christian McCaffrey (RB) 22.8%; Deebo Samuel Sr. (WR) 11.1%; Depth chart (strong): If Mike Evans (depth #1) is out, Deebo Samuel (depth #2) becomes the 49ers' WR1 per the depth chart factor for week 7. Not supported: Games without the player. Christian McCaffrey (RB) has the top recent target share among his teammates not already on your roster (22.8%). He averages 18 half-PPR points per game this season. (Rule-based verdict: the verdict model call failed, so fixed thresholds were applied.)

Critic rounds:
  Round 1: approved (review: rule-based), 0 blocking of 0 issues

Final answer (approved; rule-based verdict):
Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey if available. Most supported by the data: Team usage (strong): Highest recent target share: Mike Evans (WR) 27.1%; George Kittle (TE) 24.9%; Christian McCaffrey (RB) 22.8%; Deebo Samuel Sr. (WR) 11.1%; Depth chart (strong): If Mike Evans (depth #1) is out, Deebo Samuel (depth #2) becomes the 49ers' WR1 per the depth chart factor for week 7. Not supported: Games without the player. Christian McCaffrey (RB) has the top recent target share among his teammates not already on your roster (22.8%). He averages 18 half-PPR points per game this season. (Rule-based verdict: the verdict model call failed, so fixed thresholds were applied.)

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Team usage [strong, rule-based: highest recent target share 27.1% (strong >= 20, moderate >= 15)] (queries 3): Highest recent target share: Mike Evans (WR) 27.1%; George Kittle (TE) 24.9%; Christian McCaffrey (RB) 22.8%; Deebo Samuel Sr. (WR) 11.1%.
  2. Depth chart [strong, model] (queries 4): If Mike Evans (depth #1) is out, Deebo Samuel (depth #2) becomes the 49ers' WR1 per the depth chart factor for week 7.
  3. Games without the player [not supported, model] (queries 5): Mike Evans played all team games this season, resulting in 0 games without him to assess how the WR1 role would change.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Davante Adams: LA, WR, roster status RES (week 7). George Kittle: SF, TE, roster status ACT (week 7). Mike Evans: SF, WR, roster status ACT (week 7).  (queries 1)
  2. Latest injury report: week 7, no game status; Did Not Participate In Practice.  (queries 2)
  3. Highest recent target share: Mike Evans (WR) 27.1%; George Kittle (TE) 24.9%; Christian McCaffrey (RB) 22.8%; Deebo Samuel Sr. (WR) 11.1%.  (queries 3)
  4. If Mike Evans (depth #1) is out, Deebo Samuel (depth #2) becomes the 49ers' WR1 per the depth chart factor for week 7.  (queries 4)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('mike evans', 'team half-ppr', 'half-ppr my', 'my te', 'te is', 'is george', 'george kittle', 'kittle and', 'and my', 'my wr', 'wr is', 'is davante', 'davante adams', 'adams who', 'who becomes', 'becomes the', 'the bucs', 'bucs wr', 'wr if', 'if mike', 'evans is', 'is out', 'team half-ppr my', 'half-ppr my te', 'my te is', 'te is george', 'is george kittle', 'george kittle and', 'kittle and my', 'and my wr', 'my wr is', 'wr is davante', 'is davante adams', 'davante adams who', 'adams who becomes', 'who becomes the', 'becomes the bucs', 'the bucs wr', 'bucs wr if', 'wr if mike', 'if mike evans', 'mike evans is', 'evans is out') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
      00-0031381 | Davante Adams | LA | WR | RES | 7
      00-0033288 | George Kittle | SF | TE | ACT | 7
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
      SELECT player_display_name, position, COUNT(*) AS games, SUM(targets) AS targets, ROUND(100 * AVG(target_share), 1) AS avg_target_share_pct, ROUND(100 * AVG(CASE WHEN week >= 5 THEN target_share END), 1) AS recent_target_share_pct, SUM(carries) AS carries, ROUND(AVG((fantasy_points + fantasy_points_ppr) / 2), 1) AS half_ppr_per_game FROM NFLVERSE.player_stats WHERE season = 2026 AND team = 'SF' AND position IN ('RB', 'WR', 'TE') GROUP BY player_display_name, position ORDER BY targets DESC LIMIT 12
      player_display_name | position | games | targets | avg_target_share_pct | recent_target_share_pct | carries | half_ppr_per_game
      Mike Evans | WR | 6 | 39 | 23.3 | 27.1 | 0 | 12.6
      George Kittle | TE | 6 | 36 | 21.9 | 24.9 | 0 | 12.8
      Christian McCaffrey | RB | 6 | 35 | 20.8 | 22.8 | 77 | 18.0
      Deebo Samuel Sr. | WR | 5 | 20 | 14.3 | 11.1 | 9 | 10.5
      Demarcus Robinson | WR | 2 | 6 | 11.6 |  | 0 | 8.5
      Brandin Cooks | WR | 3 | 5 | 5.9 | 7.2 | 0 | 3.0
      Jacob Cowing | WR | 6 | 5 | 3.1 | 3.7 | 1 | 0.3
      Luke Farrell | TE | 6 | 4 | 2.2 | 1.9 | 0 | 0.5
      Jordan Watkins | WR | 2 | 3 | 5.6 | 3.4 | 0 | 4.9
      Kaelon Black | RB | 6 | 3 | 1.7 | 1.7 | 45 | 3.1
      KhaDarel Hodge | WR | 3 | 1 | 1.6 |  | 0 | 0.8
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
      WITH team_games AS (SELECT game_id FROM NFLVERSE.schedules WHERE season = 2026 AND (home_team = 'SF' OR away_team = 'SF') AND home_score IS NOT NULL), played AS (SELECT DISTINCT game_id FROM NFLVERSE.player_stats WHERE season = 2026 AND player_id = '00-0031408'), missed AS (SELECT g.game_id FROM team_games g LEFT JOIN played p ON p.game_id = g.game_id WHERE p.game_id IS NULL) SELECT CASE WHEN m.game_id IS NULL THEN 'played' ELSE 'missed' END AS player_status, ps.player_display_name, ps.position, COUNT(*) AS games, SUM(ps.targets) AS targets, ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, ROUND(AVG((ps.fantasy_points + ps.fantasy_points_ppr) / 2), 1) AS half_ppr_per_game FROM NFLVERSE.player_stats ps JOIN team_games g ON g.game_id = ps.game_id LEFT JOIN missed m ON m.game_id = ps.game_id WHERE ps.season = 2026 AND ps.team = 'SF' AND ps.player_id <> '00-0031408' AND ps.position IN ('RB', 'WR', 'TE') GROUP BY CASE WHEN m.game_id IS NULL THEN 'played' ELSE 'missed' END, ps.player_display_name, ps.position ORDER BY player_status, targets DESC LIMIT 30
      player_status | player_display_name | position | games | targets | avg_target_share_pct | half_ppr_per_game
      played | George Kittle | TE | 6 | 36 | 21.9 | 12.8
      played | Christian McCaffrey | RB | 6 | 35 | 20.8 | 18.0
      played | Deebo Samuel Sr. | WR | 5 | 20 | 14.3 | 10.5
      played | Demarcus Robinson | WR | 2 | 6 | 11.6 | 8.5
      played | Jacob Cowing | WR | 6 | 5 | 3.1 | 0.3
      played | Brandin Cooks | WR | 3 | 5 | 5.9 | 3.0
      played | Luke Farrell | TE | 6 | 4 | 2.2 | 0.5
      played | Jordan Watkins | WR | 2 | 3 | 5.6 | 4.9
      played | Kaelon Black | RB | 6 | 3 | 1.7 | 3.1
      played | KhaDarel Hodge | WR | 3 | 1 | 1.6 | 0.8
      played | Brayden Willis | TE | 4 | 0 | 0.0 | 0.0
      played | Jordan James | RB | 3 | 0 | 0.0 | 0.5
```
