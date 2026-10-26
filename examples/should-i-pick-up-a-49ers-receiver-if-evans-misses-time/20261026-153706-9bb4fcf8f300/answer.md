```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Team usage, Depth chart, Games without the player
  factors by rules: none
  first verdict: model; final verdict: rule-based
  critic reviews: model, model, model
Timings: total 51.4s; analyst 28.9s, critic 21.2s, factor_agent 1.8s, planner 0.5s (busy time; factor agents run in parallel)

Question: Should I pick up a 49ers receiver if Evans misses time?
Run 9bb4fcf8f300: 6 queries, 3 critic rounds, 51.4s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for rr5-league: 12-team, half-PPR scoring; roster: George Kittle (SF, TE), Davante Adams (LA, WR) (4 memories retrieved)
[MEMORY CONTEXT]
## fantasy
- [WK] George Kittle (SF, TE) is on the user's roster. (entities: george kittle, george, kittle) <mem-ac5b7444e37a>
- [WK] The user's league has 12 teams. <mem-c0efa3283e87>
- [WK] Davante Adams (LA, WR) is on the user's roster. (entities: davante adams, davante, adams) <mem-c3d540d84a61>
- [WK] The user's league uses half-PPR scoring. (entities: ppr) <mem-fc65e55574bf>
[/MEMORY CONTEXT]

Answer before the critic:
Deebo Samuel is next at WR on the depth chart (11.1% recent target share), so for fantasy: pick up Deebo Samuel. Evans = Mike Evans, SF WR. Mike Evans has the highest recent target share at 27.1%, but since he is out, the fantasy allocation drops to the next available WR. By target share ranking, George Kittle (24.9%) and Christian McCaffrey (22.8%) rank higher, but Samuel's 11.1% target share is the highest among the WRs below Evans on the depth chart not already on the roster. In a 12-team half-PPR league, picking up Deebo Samuel provides the best WR streamer option as the designated backup to Mike Evans.

Critic rounds:
  Round 1: needs_revision (review: model), 3 blocking of 4 issues
    - [blocking] direction in answer: The answer is reversed here: it puts George Kittle above Mike Evans, but by recent target share George Kittle has 24.9% to Mike Evans's 27.1%.
      claim: By target share ranking, George Kittle (24.9%) and Christian McCaffrey (22.8%) rank higher, but Samuel's 11.1% target share is the highest among the WRs below Evans on the depth chart not already on the roster.
    - [blocking] direction in answer: The answer is reversed here: it puts Christian McCaffrey above Mike Evans, but by recent target share Christian McCaffrey has 22.8% to Mike Evans's 27.1%.
      claim: By target share ranking, George Kittle (24.9%) and Christian McCaffrey (22.8%) rank higher, but Samuel's 11.1% target share is the highest among the WRs below Evans on the depth chart not already on the roster.
    - [recorded] model_review in answer: By recent target share ranking, the WRs below Evans on the depth chart are Brandin Cooks (WR3) 7.2%, Jacob Cowing (WR5) 3.7%, and Deebo Samuel (WR2) 11.1%. However, Christian McCaffrey (RB) 22.8% and George Kittle (TE) 24.9% rank higher than Deebo Samuel and are available in the league. Since George Kittle is already on the user's roster, the next available highest target share is Christian McCaffrey (22.8%), not Deebo Samuel (11.1%).
      claim: Deebo Samuel's 11.1% recent target share is the highest among the WRs below Evans on the depth chart not already on the roster.
    - [blocking] model_review in answer: By target share ranking, George Kittle (24.9%) and Christian McCaffrey (22.8%) rank higher than Deebo Samuel (11.1%) and are available. Picking up George Kittle provides a better streamer option, but since George Kittle is already on the user's roster, the next best available option is Christian McCaffrey (22.8%), not Deebo Samuel (11.1%).
      claim: In a 12-team half-PPR league, picking up Deebo Samuel provides the best WR streamer option as the designated backup to Mike Evans.
  Round 2: needs_revision (review: model), 1 blocking of 2 issues
    - [blocking] verdict_support in answer: Christian McCaffrey is not a WR below Mike Evans on the SF depth chart who can play; the stand-ins are Deebo Samuel, Brandin Cooks, Jacob Cowing.
      claim: pick up Christian McCaffrey.
    - [recorded] model_review in answer: Christian McCaffrey is an RB, not a WR. The question asks about picking up a 49ers receiver. Depth chart order lists Deebo Samuel (WR2) as next at WR after Mike Evans; picking up McCaffrey does not fill the WR position. McCaffrey's target share (22.8%) is higher than Samuel's (11.1%), but he cannot play WR in this context.
      claim: picking up Christian McCaffrey provides the best available fantasy asset after Evans's projected absence.
  Round 3: approved (review: model), 0 blocking of 2 issues
    - [recorded] model_review in answer: By recent target share ranking, George Kittle (24.9%) and Christian McCaffrey (22.8%) rank higher than Deebo Samuel (11.1%) and are available in the league. Since George Kittle is already on the user's roster, the next available highest target share is Christian McCaffrey (22.8%), not Deebo Samuel.
      claim: Deebo Samuel has the most recent target share among the WRs below Mike Evans on the depth chart not already on your roster (11.1%).
    - [recorded] model_review in answer: The data does not provide per-game scoring averages. This claim is unsupported by the given facts.
      claim: He averages 10.5 half-PPR points per game this season.

Final answer (approved; rule-based verdict):
Deebo Samuel is next at WR on the depth chart (11.1% recent target share), so for fantasy: pick up Deebo Samuel if available. Evans = Mike Evans, SF WR. Most supported by the data: Team usage (strong): Mike Evans has the highest recent target share at 27.1%, and since he is out, the next highest target share holder on the 49ers is George Kittle (TE) at 24.9%, making Kittle the effective TE1 by usage if Evans is inactive; Depth chart (moderate): Mike Evans is the SF WR1 with 75.5 half-PPR points, but the 49ers have 10 receivers on the depth chart, indicating limited immediate impact if he misses time. Not supported: Games without the player. Deebo Samuel has the most recent target share among the WRs below Mike Evans on the depth chart not already on your roster (11.1%). He averages 10.5 half-PPR points per game this season. (Rule-based verdict: the model recommended a player the usage numbers do not back after a revision, so fixed thresholds were applied.)

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Team usage [strong, model] (queries 4): Mike Evans has the highest recent target share at 27.1%, and since he is out, the next highest target share holder on the 49ers is George Kittle (TE) at 24.9%, making Kittle the effective TE1 by usage if Evans is inactive.
  2. Depth chart [moderate, model] (queries 5): Mike Evans is the SF WR1 with 75.5 half-PPR points, but the 49ers have 10 receivers on the depth chart, indicating limited immediate impact if he misses time.
  3. Games without the player [not supported, model] (queries 6): Mike Evans has played every team game this season; there are no games without him to compare.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Mike Evans: SF, WR, 75.5 half-PPR points this season. Mitchell Evans: CAR, TE, 9.7 half-PPR points this season. Omari Evans: KC, WR, n/a half-PPR points this season.  (queries 2)
  2. Latest injury report: week 7, no game status; Did Not Participate In Practice.  (queries 3)
  3. Mike Evans has the highest recent target share at 27.1%, and since he is out, the next highest target share holder on the 49ers is George Kittle (TE) at 24.9%, making Kittle the effective TE1 by usage if Evans is inactive.  (queries 4)
  4. Mike Evans is the SF WR1 with 75.5 half-PPR points, but the 49ers have 10 receivers on the depth chart, indicating limited immediate impact if he misses time.  (queries 5)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND REGEXP_REPLACE(LOWER(full_name), ' (jr|sr|ii|iii|iv)[.]?$', '') IN ('evans', 'should i', 'i pick', 'pick up', 'up a', 'a ers', 'ers receiver', 'receiver if', 'if evans', 'evans misses', 'misses time', 'should i pick', 'i pick up', 'pick up a', 'up a ers', 'a ers receiver', 'ers receiver if', 'receiver if evans', 'if evans misses', 'evans misses time') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
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
  [5] SF current WR depth chart (pos_rank 1 = top), with roster status and the week 7 injury report
      SELECT DISTINCT d.pos_abb, d.pos_rank, d.player_name, r.status AS roster_status, i.report_status FROM NFLVERSE.depth_charts d LEFT JOIN (SELECT gsis_id, MAX(status) AS status FROM NFLVERSE.rosters WHERE season = 2026 AND week = (SELECT MAX(week) FROM NFLVERSE.rosters WHERE season = 2026) GROUP BY gsis_id) r ON r.gsis_id = d.gsis_id LEFT JOIN (SELECT gsis_id, MAX(report_status) AS report_status FROM NFLVERSE.injuries WHERE season = 2026 AND week = 7 GROUP BY gsis_id) i ON i.gsis_id = d.gsis_id WHERE d.team = 'SF' AND d.pos_abb = 'WR' AND d.dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = 'SF') ORDER BY d.pos_rank LIMIT 25
      pos_abb | pos_rank | player_name | roster_status | report_status
      WR | 1 | Mike Evans | ACT | 
      WR | 2 | Deebo Samuel | ACT | 
      WR | 3 | Brandin Cooks | ACT | 
      WR | 4 | Jordan Watkins | ACT | 
      WR | 5 | Jacob Cowing | ACT | 
      WR | 6 | Christian Kirk | RES | 
      WR | 7 | Demarcus Robinson | RES | 
      WR | 8 | De'Zhaun Stribling | RES | 
      WR | 9 | Ricky Pearsall | RES | 
      WR | 10 | Brandon Aiyuk |  | 
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
