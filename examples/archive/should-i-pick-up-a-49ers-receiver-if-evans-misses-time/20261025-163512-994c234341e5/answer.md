```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Depth chart, Team usage
  factors by rules: none
  first verdict: model; final verdict: rule-based
  critic reviews: model, model
Timings: total 245.2s; analyst 124.9s, critic 90.0s, factor_agent 27.7s, planner 16.1s (busy time; factor agents run in parallel)
Failed or skipped model calls: analyst revise (error, 90.0s)

Question: Should I pick up a 49ers receiver if Evans misses time?
Run 994c234341e5: 4 queries, 2 critic rounds, 245.2s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for demo: 12-team, half-PPR scoring; roster: George Kittle (SF, TE), Davante Adams (LA, WR) (4 memories retrieved)
[MEMORY CONTEXT]
## fantasy
- [WK] The user's league uses half-PPR scoring. (entities: ppr) <mem-0bf98e50780c>
- [WK] The user's league has 12 teams. <mem-45388930c4c3>
- [WK] Davante Adams (LA, WR) is on the user's roster. (entities: davante adams, davante, adams) <mem-9bb93cc2cb3d>
- [WK] George Kittle (SF, TE) is on the user's roster. (entities: george kittle, george, kittle) <mem-ad6e355b4766>
[/MEMORY CONTEXT]

Answer before the critic:
Pick up Deebo Samuel. Per the depth chart, if Mike Evans misses time, Deebo Samuel moves from #2 to the WR1 role as the primary 49ers receiver replacement. Team usage shows Evans leads targets at 27.1%, followed by Kittle at 24.9% and McCaffrey at 22.8%, making Samuel the top target beneficiary when Evans is out.

Critic rounds:
  Round 1: needs_revision (review: model), 1 blocking of 1 issues
    - [blocking] verdict_support in answer: Deebo Samuel Sr.'s recent target share (11.1%) trails Christian McCaffrey (RB) 22.8%, and is less than half of Christian McCaffrey's. A 'Pick up' must follow the usage numbers: recommend the player they back. The answer may still say who is next on the depth chart.
      claim: Pick up Deebo Samuel.
  Round 2: approved (review: model), 0 blocking of 0 issues

Final answer (approved; rule-based verdict):
Pick up Mike Evans. Most supported by the data: Depth chart (strong): If Evans misses time, the 49ers' depth chart lists Samuel #2, Cooks #3, and Watkins #4 as the primary replacements; Team usage (moderate): Mike Evans leads 49ers targets at 27.1%, followed by Kittle (24.9%) and McCaffrey (22.8%), showing significant target share distribution if Evans misses time. Rule: pick up at 15%+ recent target share; his is 27.1%. (Rule-based verdict: the verdict model call failed, so fixed thresholds were applied.)

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Depth chart [strong, model] (queries 4): If Evans misses time, the 49ers' depth chart lists Samuel #2, Cooks #3, and Watkins #4 as the primary replacements.
  2. Team usage [moderate, model] (queries 3): Mike Evans leads 49ers targets at 27.1%, followed by Kittle (24.9%) and McCaffrey (22.8%), showing significant target share distribution if Evans misses time.

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Mike Evans: SF, WR, roster status ACT (week 7).  (queries 1)
  2. Latest injury report: week 7, no game status; Did Not Participate In Practice.  (queries 2)
  3. If Evans misses time, the 49ers' depth chart lists Samuel #2, Cooks #3, and Watkins #4 as the primary replacements.  (queries 4)
  4. Mike Evans leads 49ers targets at 27.1%, followed by Kittle (24.9%) and McCaffrey (22.8%), showing significant target share distribution if Evans misses time.  (queries 3)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('mike evans', 'should i', 'i pick', 'pick up', 'up a', 'a ers', 'ers receiver', 'receiver if', 'if evans', 'evans misses', 'misses time', 'should i pick', 'i pick up', 'pick up a', 'up a ers', 'a ers receiver', 'ers receiver if', 'receiver if evans', 'if evans misses', 'evans misses time') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
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
```
