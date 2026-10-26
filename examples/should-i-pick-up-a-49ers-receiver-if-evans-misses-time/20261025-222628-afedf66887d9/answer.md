```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Team usage, Depth chart, Games without the player
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: model
Timings: total 17.9s; analyst 13.8s, critic 2.6s, factor_agent 2.0s, planner 0.7s (busy time; factor agents run in parallel)

Question: Should I pick up a 49ers receiver if Evans misses time?
Run afedf66887d9: 5 queries, 1 critic rounds, 17.9s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for rr4-league: 12-team, half-PPR scoring; roster: George Kittle (SF, TE), Davante Adams (LA, WR) (4 memories retrieved)
[MEMORY CONTEXT]
## fantasy
- [WK] The user's league has 12 teams. <mem-73a461abc36a>
- [WK] Davante Adams (LA, WR) is on the user's roster. (entities: davante adams, davante, adams) <mem-4c298fb7e0b4>
- [WK] The user's league uses half-PPR scoring. (entities: ppr) <mem-67bc0eff2718>
- [WK] George Kittle (SF, TE) is on the user's roster. (entities: george kittle, george, kittle) <mem-a28503288b18>
[/MEMORY CONTEXT]

Answer before the critic:
Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey. Mike Evans has the highest target share at 27.1% as the 49ers' WR1, but since he is out, the depth chart dictates Deebo Samuel as the next WR in line. However, target share data shows Christian McCaffrey at 22.8% ranks third overall and highest among players not on the roster, making him the top fantasy replacement in half-PPR despite being an RB.

Critic rounds:
  Round 1: approved (review: model), 0 blocking of 0 issues

Final answer (approved; model verdict):
Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey. Mike Evans has the highest target share at 27.1% as the 49ers' WR1, but since he is out, the depth chart dictates Deebo Samuel as the next WR in line. However, target share data shows Christian McCaffrey at 22.8% ranks third overall and highest among players not on the roster, making him the top fantasy replacement in half-PPR despite being an RB.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Team usage [strong, model] (queries 3): Mike Evans has the highest target share at 27.1%, making him the 49ers' WR1 if healthy; if Mike Evans is out, George Kittle's 24.9% target share ranks him as the highest-targeted TE and the next highest usage option overall at 24.9%.
  2. Depth chart [strong, model] (queries 4): Depth chart shows Mike Evans as WR1, Deebo Samuel as WR2, and Brandin Cooks as WR3; if Evans is out, Deebo Samuel becomes the natural WR1 replacement per depth chart succession.
  3. Games without the player [not supported, model] (queries 5): Mike Evans has played every team game this season; there are no games without him to compare.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Mike Evans: SF, WR, roster status ACT (week 7).  (queries 1)
  2. Latest injury report: week 7, no game status; Did Not Participate In Practice.  (queries 2)
  3. Mike Evans has the highest target share at 27.1%, making him the 49ers' WR1 if healthy; if Mike Evans is out, George Kittle's 24.9% target share ranks him as the highest-targeted TE and the next highest usage option overall at 24.9%.  (queries 3)
  4. Depth chart shows Mike Evans as WR1, Deebo Samuel as WR2, and Brandin Cooks as WR3; if Evans is out, Deebo Samuel becomes the natural WR1 replacement per depth chart succession.  (queries 4)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND REGEXP_REPLACE(LOWER(full_name), ' (jr|sr|ii|iii|iv)[.]?$', '') IN ('mike evans', 'should i', 'i pick', 'pick up', 'up a', 'a ers', 'ers receiver', 'receiver if', 'if evans', 'evans misses', 'misses time', 'should i pick', 'i pick up', 'pick up a', 'up a ers', 'a ers receiver', 'ers receiver if', 'receiver if evans', 'if evans misses', 'evans misses time') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
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
