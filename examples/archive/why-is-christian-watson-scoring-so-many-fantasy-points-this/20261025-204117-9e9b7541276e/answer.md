```
Data: live Zetaris cluster (SAMPLE_MODE=false).
Models: Meterless Nightshift (nvidia/nemotron-3.5-lightning-30b-a3b).
Steps (model vs rule-based):
  planner: model
  memory mining: code
  factors by model: Opportunity, Teammate absences, Team pass rate and game script, Big plays, Touchdowns and red zone, Matchups
  factors by rules: none
  first verdict: model; final verdict: model
  critic reviews: model, model, model
Timings: total 128.4s; analyst 77.9s, critic 45.7s, factor_agent 11.5s, planner 0.3s (busy time; factor agents run in parallel)

Question: Why is Christian Watson scoring so many fantasy points this season?
Run 9e9b7541276e: 8 queries, 3 critic rounds, 128.4s
Season context: current season 2026; the latest week with stats is week 6. "This season" means season 2026.

League memory for rr2-watson: PPR scoring; roster: none (0 memories retrieved)

Answer before the critic:
Christian Watson's 19.8 PPR points per game this season are driven by big play efficiency (11.2 yards per target, with air yards share rising to 34.8%) and touchdown efficiency (6 TDs = 30.3% of PPR points). However, his opportunity has declined sharply: snap share dropped from 82% in weeks 1-3 to 78.7% in weeks 4-6, and target share fell from 25.8% to 18.6%, causing PPR points per game to drop from 23.1 to 16.5. For fantasy production this season, his strong touchdown and red-zone efficiency (6 TDs, 20% of targets) and improved yards per target sustain value despite the opportunity decline. Verdict: start Christian Watson.

Critic rounds:
  Round 1: needs_revision (review: model), 3 blocking of 3 issues
    - [blocking] model_review in answer: The facts show 11.2 yards per target is the overall season average, but yards per target actually rose from 10.6 in weeks 1-3 to 13.9 in weeks 4-6. Air yards share rose from 30% in weeks 1-3 to 34.8% in weeks 4-6. However, the claim that 19.8 PPR points per game are driven by big play efficiency is not well-supported because PPR points per game declined from 23.1 to 16.5 despite the rise in yards per target and air yards share. Touchdown efficiency is accurate: 6 TDs = 36 of 118.8 PPR points (30.3%).
      claim: Christian Watson's 19.8 PPR points per game this season are driven by big play efficiency (11.2 yards per target, with air yards share rising to 34.8%) and touchdown efficiency (6 TDs = 30.3% of PPR points).
    - [blocking] model_review in answer: The facts confirm the numbers: snap share 82% in weeks 1-3 vs 78.7% in weeks 4-6, target share 25.8% in weeks 1-3 vs 18.6% in weeks 4-6, and PPR points per game 23.1 in weeks 1-3 vs 16.5 in weeks 4-6. The decline in opportunity and PPR points per game is correctly stated and well-supported.
      claim: his opportunity has declined sharply: snap share dropped from 82% in weeks 1-3 to 78.7% in weeks 4-6, and target share fell from 25.8% to 18.6%, causing PPR points per game to drop from 23.1 to 16.5.
    - [blocking] model_review in answer: The facts show red-zone target share is 20% (7 of 35 targets), which is accurate. Yards per target improved from 10.6 to 13.9, which is accurate. However, the opportunity decline directly contradicts the premise of 'sustaining value' because PPR points per game dropped from 23.1 to 16.5. The facts do not support that the improved yards per target and red-zone efficiency overcome the significant loss in target share and overall PPR points.
      claim: For fantasy production this season, his strong touchdown and red-zone efficiency (6 TDs, 20% of targets) and improved yards per target sustain value despite the opportunity decline.
  Round 2: needs_revision (review: model), 1 blocking of 4 issues
    - [blocking] question_fit in answer: The verdict 'hold' names no player; say who to hold.
      claim: hold.
    - [recorded] model_review in answer: The facts show 'this season' averages 19.8 PPR points per game across 6 games, but the season-long average masks a clear decline: weeks 1-3 averaged 23.1 PPR points per game, while weeks 4-6 averaged 16.5. The answer's claim that the 19.8 figure is 'driven by declining opportunity' is contradicted by the data showing the overall average includes the high-output early weeks.
      claim: Christian Watson's 19.8 PPR points per game this season are driven by declining opportunity despite improved big-play efficiency.
    - [recorded] model_review in answer: The facts confirm the directional changes: target share fell from 25.8% (weeks 1-3) to 18.6% (weeks 4-6), snap share fell from 82% to 78.7%, and PPR points per game fell from 23.1 to 16.5. These specific numbers are correctly stated and well-supported.
      claim: Target share dropped from 25.8% to 18.6% and snap share from 82% to 78.7%, causing PPR points per game to fall from 23.1 to 16.5.
    - [recorded] model_review in answer: The facts show yards per target rose from 10.6 (weeks 1-3) to 13.9 (weeks 4-6), and air yards share rose from 30% to 34.8%. However, the answer's premise that the loss in target share and PPR production 'outweighs' the improved efficiency is a value judgment not directly checked by the facts. The facts themselves present the conflicting trends (declining opportunity vs. improved efficiency) without establishing which factor dominates the season-long 19.8 average.
      claim: Although yards per target rose from 10.6 to 13.9 and air yards share increased to 34.8%, and his 6 TDs account for 30.3% of PPR points, the significant loss in target share and overall PPR production outweighs the improved efficiency, making Hold the recommended action.
  Round 3: needs_revision (review: model), 1 blocking of 3 issues
    - [blocking] question_fit in answer: The verdict 'hold' names no player; say who to hold.
      claim: hold.
    - [recorded] model_review in answer: The facts show that although opportunity declined (target share fell from 25.8% to 18.6%, snap share from 82% to 78.7%), the season-long 19.8 PPR points per game average includes higher-output early weeks (23.1 PPR per game in weeks 1-3). The data indicates a decline in opportunity and PPR production, but the claim that the 19.8 average is 'driven by declining opportunity' contradicts the fact that the overall average is inflated by the high-output weeks 1-3.
      claim: Christian Watson's 19.8 PPR points per game this season are driven by declining opportunity despite improved big-play efficiency.
    - [recorded] model_review in answer: The facts present conflicting trends: target share and PPR points per game declined, but yards per target and air yards share rose. The facts do not establish which factor dominates the season-long 19.8 average, and the recommended action 'Hold' is a value judgment not directly supported or contradicted by the computed facts alone.
      claim: the significant loss in target share and overall PPR production outweighs the improved efficiency, making Hold the recommended action.

Final answer (unresolved after 3 rounds; model verdict):
Christian Watson's 19.8 PPR points per game this season are driven by declining opportunity despite improved big-play efficiency. Target share dropped from 25.8% to 18.6% and snap share from 82% to 78.7%, causing PPR points per game to fall from 23.1 to 16.5. Although yards per target rose from 10.6 to 13.9 and air yards share increased to 34.8%, and his 6 TDs account for 30.3% of PPR points, the significant loss in target share and overall PPR production outweighs the improved efficiency, making Hold the recommended action. Verdict: hold. Critic note: The verdict 'hold' names no player; say who to hold.

_Informational only, based on nflverse data; not betting advice._

Factors (most to least supported):
  1. Opportunity [moderate, model] (queries 3): Christian Watson's 19.8 PPR points per game this season are driven by a declining opportunity factor: snap share dropped from 82% in weeks 1-3 to 78.7% in weeks 4-6, and target share fell from 25.8% to 18.6%, causing PPR points per game to decrease from 23.1 to 16.5.
  2. Teammate absences [moderate, model] (queries 4): Christian Watson's PPR points per game increased to 21.4 when teammates were out (weeks 3, 5, 6) compared to 18.2 in other weeks, despite a lower target share of 21.8% vs 22.6% and lower yards per target of 11.8 vs 12.6.
  3. Team pass rate and game script [moderate, model] (queries 5): Pass rate dropped from 72.3% in weeks 1-3 to 62.8% in weeks 4-6, but is higher in losses (76.2%) than wins/ties (63.2%), indicating game script effects rather than consistent opportunity.
  4. Big plays [moderate, model] (queries 6): Christian Watson's 11.2 yards per target this season is driven by a significant increase from 10.6 in weeks 1-3 to 13.9 in weeks 4-6, with air yards share rising from 30% to 34.8% over the same period.
  5. Touchdowns and red zone [moderate, model] (queries 7): Touchdowns account for 30.3% of Watson's PPR points (6 TDs = 36 of 118.8 points), and 20% of his targets are red zone (7 of 35), but his snap share declined from 82% in weeks 1-3 to 78.7% in weeks 4-6, and target share fell from 25.8% to 18.6% over the same span.
  6. Matchups [moderate, model] (queries 8): Christian Watson's 19.8 PPR points per game this season are driven by favorable matchups against lower-ranked defenses, as he averages 21.7 PPR points per game against the rest (4 games) compared to 16 against top-10 soft defenses (2 games).

Not measurable with this data:
  - Route participation and alignment
  - Coverage faced and quality of the cornerbacks
  - Coaching intent and play-calling plans
  - Injury severity beyond the official report

Claims:
  1. Christian Watson: GB, WR, roster status ACT (week 7).  (queries 1)
  2. Latest injury report: week 7, no game status; Limited Participation in Practice.  (queries 2)
  3. Christian Watson's 19.8 PPR points per game this season are driven by a declining opportunity factor: snap share dropped from 82% in weeks 1-3 to 78.7% in weeks 4-6, and target share fell from 25.8% to 18.6%, causing PPR points per game to decrease from 23.1 to 16.5.  (queries 3)
  4. Christian Watson's PPR points per game increased to 21.4 when teammates were out (weeks 3, 5, 6) compared to 18.2 in other weeks, despite a lower target share of 21.8% vs 22.6% and lower yards per target of 11.8 vs 12.6.  (queries 4)
  5. Pass rate dropped from 72.3% in weeks 1-3 to 62.8% in weeks 4-6, but is higher in losses (76.2%) than wins/ties (63.2%), indicating game script effects rather than consistent opportunity.  (queries 5)
  6. Christian Watson's 11.2 yards per target this season is driven by a significant increase from 10.6 in weeks 1-3 to 13.9 in weeks 4-6, with air yards share rising from 30% to 34.8% over the same period.  (queries 6)
  7. Touchdowns account for 30.3% of Watson's PPR points (6 TDs = 36 of 118.8 points), and 20% of his targets are red zone (7 of 35), but his snap share declined from 82% in weeks 1-3 to 78.7% in weeks 4-6, and target share fell from 25.8% to 18.6% over the same span.  (queries 7)
  8. Christian Watson's 19.8 PPR points per game this season are driven by favorable matchups against lower-ranked defenses, as he averages 21.7 PPR points per game against the rest (4 games) compared to 16 against top-10 soft defenses (2 games).  (queries 8)

Queries:
  [1] team, position and roster status
      SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week FROM NFLVERSE.rosters r JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters WHERE season = 2026 AND LOWER(full_name) IN ('christian watson', 'why is', 'is christian', 'watson scoring', 'scoring so', 'so many', 'many fantasy', 'fantasy points', 'points this', 'this season', 'why is christian', 'is christian watson', 'christian watson scoring', 'watson scoring so', 'scoring so many', 'so many fantasy', 'many fantasy points', 'fantasy points this', 'points this season') GROUP BY gsis_id) latest ON r.gsis_id = latest.gsis_id AND r.week = latest.week WHERE r.season = 2026 AND r.position IN ('QB', 'RB', 'WR', 'TE') ORDER BY r.full_name
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
      week | full_name | position | report_status | report_primary_injury
      3 | Jayden Reed | WR | Out | Neck
      5 | Chris Brooks | RB | Out | Ankle
      5 | Savion Williams | WR | Out | Ankle
      6 | Skyy Moore | WR | Out | Ankle
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
