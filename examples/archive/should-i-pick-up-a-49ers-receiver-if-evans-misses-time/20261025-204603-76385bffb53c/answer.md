```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Team usage, Depth chart, Games without the player
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: model, model, model
Timings: total 74.4s; analyst 22.9s, critic 50.5s, factor_agent 1.5s, planner 0.4s (busy time; factor agents run in parallel)

Question: Should I pick up a 49ers receiver if Evans misses time?
Run 76385bffb53c: 6 queries, 3 critic rounds, 74.4s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for rr2-league: 12-team, half-PPR scoring; roster: George Kittle (SF, TE), Davante Adams (LA, WR) (4 memories retrieved)
[MEMORY CONTEXT]
## fantasy
- [WK] Davante Adams (LA, WR) is on the user's roster. (entities: davante adams, davante, adams) <mem-53bf1f21c0a4>
- [WK] The user's league has 12 teams. <mem-846a5373c69b>
- [WK] George Kittle (SF, TE) is on the user's roster. (entities: george kittle, george, kittle) <mem-bc60a151f56a>
- [WK] The user's league uses half-PPR scoring. (entities: ppr) <mem-dcf20d6a8f36>
[/MEMORY CONTEXT]

Answer before the critic:
Deebo Samuel is next at WR on the depth chart, but the target share points to George Kittle (24.9%), so for fantasy: pick up George Kittle. Evans = Mike Evans, SF WR. George Kittle's 24.9% target share ranks him second on the 49ers, making him the highest-targeted tight end and the best fantasy replacement if Mike Evans misses time. In half-PPR, Kittle's target share surpasses Deebo Samuel's 11.1% and Brandin Cooks' 7.2%, providing more projected points than the other available 49ers options.

Critic rounds:
  Round 1: needs_revision (review: model), 3 blocking of 4 issues
    - [blocking] user_context in answer: George Kittle is already on the user's roster; recommend a player who is not.
      claim: pick up George Kittle.
    - [recorded] model_review in answer: The depth chart places Mike Evans as WR1 and Deebo Samuel as WR2. If Mike Evans is out, Deebo Samuel moves up to WR1 per depth chart order. George Kittle is listed WR10 on the WR depth chart and is a TE, so he is not the natural WR1 replacement.
      claim: George Kittle's 24.9% target share ranks him second on the 49ers behind Mike Evans' 27.1%, making him the highest-targeted tight end and the best fantasy replacement if Mike Evans misses time.
    - [blocking] model_review in answer: The facts state Davante Adams' roster status is RES (inactive) and there are no target share stats provided for Adams. Without Adams's target share, the comparison cannot be validated against the facts.
      claim: In half-PPR, Kittle's target share surpasses Deebo Samuel's 11.1% and Brandin Cooks' 7.2%, providing more projected points than the other available 49ers options.
    - [blocking] model_review in answer: The depth chart order dictates the WR1 succession: the player listed right after an injured starter is the one next in line. Per the depth chart facts, Deebo Samuel is next at WR on the depth chart. Target share data does not override depth chart order for determining the WR1 replacement.
      claim: Deebo Samuel is next at WR on the depth chart, but the target share points to George Kittle (24.9%), so for fantasy: pick up George Kittle.
  Round 2: needs_revision (review: model), 1 blocking of 2 issues
    - [blocking] verdict_support in answer: Deebo Samuel Sr.'s recent target share (11.1%) trails Christian McCaffrey (RB) 22.8%, and is less than half of Christian McCaffrey's. A 'Pick up' must follow the usage numbers: recommend the player they back. The answer may still say who is next on the depth chart.
      claim: pick up Deebo Samuel.
    - [recorded] model_review in answer: The depth chart facts state the WR order is Mike Evans (WR1), Deebo Samuel (WR2), Brandin Cooks (WR3), etc. If Mike Evans is out, Deebo Samuel moves up to WR1 per depth chart order. However, target share data shows George Kittle (24.9%) has higher recent target share than Deebo Samuel (11.1%). In half-PPR, Kittle's target share significantly outperforms Samuel's other available 49ers options. The answer correctly states the depth chart succession but overlooks that Kittle's target share surpasses Samuel's for fantasy production.
      claim: Deebo Samuel is next at WR on the depth chart, so for fantasy: pick up Deebo Samuel.
  Round 3: needs_revision (review: model), 2 blocking of 4 issues
    - [blocking] verdict_support in answer: Deebo Samuel Sr.'s recent target share (11.1%) trails Christian McCaffrey (RB) 22.8%, and is less than half of Christian McCaffrey's. A 'Pick up' must follow the usage numbers: recommend the player they back. The answer may still say who is next on the depth chart.
      claim: pick up Deebo Samuel.
    - [blocking] position_label in answer: 'WR1' is wrong for Christian McCaffrey, who is a RB.
      claim: Among available 49ers options, Deebo Samuel's 11.1% target share ranks third behind George Kittle (24.9%) and McCaffrey (22.8%), yet he is the top receiver option since the depth chart places him next at WR1 if Evans is out.
    - [recorded] model_review in answer: Depth chart order dictates that Deebo Samuel (WR2) is the next WR1 if Mike Evans is out. However, target share data shows George Kittle (TE) at 24.9% and Christian McCaffrey (RB) at 22.8% both have higher recent target shares than Deebo Samuel's 11.1%. In a half-PPR league, Kittle and McCaffrey would likely project more fantasy points than Samuel even if Samuel moves to WR1 per depth chart.
      claim: Deebo Samuel's 11.1% target share ranks him third behind George Kittle (24.9%) and McCaffrey (22.8%), yet he is the top receiver option since the depth chart places him next at WR1 if Evans is out.
    - [recorded] model_review in answer: The facts show George Kittle (24.9%) and Christian McCaffrey (22.8%) both have higher recent target shares than Deebo Samuel's 11.1%. Since the answer does not explicitly compare Samuel to Kittle and McCaffrey on half-PPR production, and those players have significantly higher target shares, the claim that Samuel significantly outperforms the other options is not fully supported by the target share numbers.
      claim: In half-PPR, Samuel's target share significantly outperforms the other available 49ers receivers like Brandin Cooks (7.2%) and Jacob Cowing (3.7%).

Final answer (unresolved after 3 rounds; model verdict):
Deebo Samuel is next at WR on the depth chart (11.1% recent target share), so for fantasy: pick up Deebo Samuel. Evans = Mike Evans, SF WR. Mike Evans has the highest target share at 27.1%, but he is out per the question. Among available 49ers options, Deebo Samuel's 11.1% target share ranks third behind George Kittle (24.9%) and McCaffrey (22.8%), yet he is the top receiver option since the depth chart places him next at WR1 if Evans is out. In half-PPR, Samuel's target share significantly outperforms the other available 49ers receivers like Brandin Cooks (7.2%) and Jacob Cowing (3.7%). Critic note: Deebo Samuel Sr.'s recent target share (11.1%) trails Christian McCaffrey (RB) 22.8%, and is less than half of Christian McCaffrey's. A 'Pick up' must follow the usage numbers: recommend the player they back. The answer may still say who is next on the depth chart. 'WR1' is wrong for Christian McCaffrey, who is a RB.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Team usage [strong, model] (queries 4): Mike Evans has the highest recent target share at 27.1%, significantly ahead of other 49ers receivers and tight end George Kittle at 24.9%.
  2. Depth chart [strong, model] (queries 5): Mike Evans is the clear WR1 with 75.5 half-PPR points, and the 49ers' WR depth chart shows a steep drop-off after him, with the next highest target-getter Deebo Samuel far behind.
  3. Games without the player [not supported, model] (queries 6): Mike Evans has played every team game this season, so there are no games without him to compare.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Mike Evans: SF, WR, 75.5 half-PPR points this season. Mitchell Evans: CAR, TE, 9.7 half-PPR points this season. Omari Evans: KC, WR, n/a half-PPR points this season.  (queries 2)
  2. Latest injury report: week 7, no game status; Did Not Participate In Practice.  (queries 3)
  3. Mike Evans has the highest recent target share at 27.1%, significantly ahead of other 49ers receivers and tight end George Kittle at 24.9%.  (queries 4)
  4. Mike Evans is the clear WR1 with 75.5 half-PPR points, and the 49ers' WR depth chart shows a steep drop-off after him, with the next highest target-getter Deebo Samuel far behind.  (queries 5)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('evans', 'should i', 'i pick', 'pick up', 'up a', 'a ers', 'ers receiver', 'receiver if', 'if evans', 'evans misses', 'misses time', 'should i pick', 'i pick up', 'pick up a', 'up a ers', 'a ers receiver', 'ers receiver if', 'receiver if evans', 'if evans misses', 'evans misses time') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week
  [2] skill players with the last name Evans
      WITH latest AS (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND position IN ('QB', 'RB', 'WR', 'TE') AND (LOWER(full_name) LIKE '% evans' OR LOWER(full_name) LIKE '% evans %') GROUP BY gsis_id), pts AS (SELECT player_id, ROUND(SUM((fantasy_points + fantasy_points_ppr) / 2), 1) AS season_points FROM NFLVERSE.player_stats WHERE season = 2026 GROUP BY player_id) SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week, p.season_points AS season_half_ppr_points FROM NFLVERSE.rosters r JOIN latest l ON r.gsis_id = l.gsis_id AND r.week = l.week LEFT JOIN pts p ON p.player_id = r.gsis_id WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
      gsis_id | full_name | team | position | status | week | season_half_ppr_points
      00-0031408 | Mike Evans | SF | WR | ACT | 7 | 75.5
      00-0040187 | Mitchell Evans | CAR | TE | ACT | 7 | 9.7
      00-0040954 | Omari Evans | KC | WR | DEV | 7 | 
  [3] Mike Evans: injury report entries this season
      SELECT week, report_status, report_primary_injury, practice_status FROM NFLVERSE.injuries WHERE season = 2026 AND gsis_id = '00-0031408' ORDER BY week
      week | report_status | report_primary_injury | practice_status
      3 | Questionable | Hip | Limited Participation in Practice
      4 | Questionable | Ribs | Limited Participation in Practice
      5 |  |  | Limited Participation in Practice
      6 | Questionable | Ribs | Did Not Participate In Practice
      7 |  |  | Did Not Participate In Practice
  [4] SF RB/WR/TE usage this season and in weeks 5-6
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
  [5] SF current WR depth chart (pos_rank 1 = top)
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
  [6] SF RB/WR/TE targets in games Mike Evans missed vs games he played this season
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
