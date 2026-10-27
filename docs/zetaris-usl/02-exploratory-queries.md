# Exploratory queries: live results

Live results of [`02-exploratory-queries.sql`](02-exploratory-queries.sql), run on 2026-10-27 00:22 UTC through the Zetaris UI-proxy route by [`run_usl.py`](run_usl.py) (no cached results). Pasted as returned; nothing edited except that long results show their first 25 rows and cells over 600 characters are cut.

## 1. player_stats: row count, players, games and weeks

```sql
SELECT COUNT(*) AS row_count, COUNT(DISTINCT player_id) AS players, COUNT(DISTINCT game_id) AS games,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.player_stats
```

| row_count | players | games | first_week | last_week |
|---|---|---|---|---|
| 6488 | 1650 | 93 | 1 | 6 |

_1.7s_

## 2. player_stats: sample row

```sql
SELECT * FROM NFLVERSE.player_stats WHERE player_display_name = 'Christian Watson' AND week = 1
```

| column | value |
|---|---|
| player_id | 00-0038124 |
| player_name | C.Watson |
| player_display_name | Christian Watson |
| position | WR |
| season | 2026 |
| week | 1 |
| season_type | REG |
| game_id | 2026_01_GB_MIN |
| team | GB |
| opponent_team | MIN |
| completions | 0 |
| attempts | 0 |
| passing_yards | 0 |
| passing_tds | 0 |
| passing_interceptions | 0 |
| passing_air_yards | 0 |
| passing_2pt_conversions | 0 |
| carries | 0 |
| rushing_yards | 0 |
| rushing_tds | 0 |
| rushing_2pt_conversions | 0 |
| receptions | 6 |
| targets | 8 |
| receiving_yards | 147 |
| receiving_tds | 2 |
| receiving_air_yards | 127 |
| receiving_yards_after_catch | 72 |
| receiving_2pt_conversions | 0 |
| target_share | 0.2 |
| air_yards_share | 0.27078891257995735 |
| wopr | 0.4895522388059702 |
| fumbles_lost_total | 0 |
| fantasy_points | 26.700000000000003 |
| fantasy_points_ppr | 32.7 |

_1.1s_

## 3. player_stats: top 10 PPR scorers through the latest week (the Opportunity and Matchups factors read this table)

```sql
SELECT player_display_name, position, team, COUNT(*) AS games, ROUND(SUM(fantasy_points_ppr), 1) AS ppr_points,
       ROUND(SUM(fantasy_points_ppr) / COUNT(*), 1) AS ppr_per_game
FROM NFLVERSE.player_stats
WHERE season_type = 'REG'
GROUP BY player_display_name, position, team
ORDER BY ppr_points DESC
LIMIT 10
```

| player_display_name | position | team | games | ppr_points | ppr_per_game |
|---|---|---|---|---|---|
| Jaxon Smith-Njigba | WR | SEA | 6 | 164.9 | 27.5 |
| Josh Allen | QB | BUF | 6 | 161.3 | 26.9 |
| Jahmyr Gibbs | RB | DET | 5 | 153.7 | 30.7 |
| Kenneth Walker III | RB | KC | 5 | 138.0 | 27.6 |
| Brock Purdy | QB | SF | 6 | 134.0 | 22.3 |
| CeeDee Lamb | WR | DAL | 6 | 131.1 | 21.9 |
| Bijan Robinson | RB | ATL | 6 | 128.5 | 21.4 |
| Christian McCaffrey | RB | SF | 6 | 122.0 | 20.3 |
| Kyren Williams | RB | LA | 6 | 119.0 | 19.8 |
| Christian Watson | WR | GB | 6 | 118.8 | 19.8 |

_1.5s_

## 4. player_stats: highest average target share among WRs and TEs with 4+ games (Opportunity factor)

```sql
SELECT player_display_name, position, team, COUNT(*) AS games, ROUND(100 * AVG(target_share), 1) AS avg_target_share_pct,
       SUM(targets) AS targets
FROM NFLVERSE.player_stats
WHERE position IN ('WR', 'TE') AND target_share IS NOT NULL
GROUP BY player_display_name, position, team
HAVING COUNT(*) >= 4
ORDER BY avg_target_share_pct DESC
LIMIT 10
```

| player_display_name | position | team | games | avg_target_share_pct | targets |
|---|---|---|---|---|---|
| Jaxon Smith-Njigba | WR | SEA | 6 | 35.6 | 66 |
| DeVonta Smith | WR | PHI | 4 | 32.3 | 41 |
| Amon-Ra St. Brown | WR | DET | 5 | 31.1 | 57 |
| Puka Nacua | WR | LA | 4 | 30.9 | 52 |
| Zay Flowers | WR | BAL | 5 | 30.8 | 42 |
| Trey McBride | TE | ARI | 6 | 29.7 | 65 |
| Brock Bowers | TE | LV | 4 | 29.3 | 43 |
| Isaiah Likely | TE | NYG | 6 | 29.1 | 59 |
| Drake London | WR | ATL | 6 | 28.9 | 46 |
| Garrett Wilson | WR | NYJ | 6 | 28.5 | 48 |

_1.3s_

## 5. player_stats: rows with no player_id (found while building the USL keys)

```sql
SELECT game_id, team, week, position, fantasy_points_ppr
FROM NFLVERSE.player_stats
WHERE player_id IS NULL
```

| game_id | team | week | position | fantasy_points_ppr |
|---|---|---|---|---|
| 2026_01_NE_SEA | SEA | 1 | NULL | 0.0 |
| 2026_02_DET_BUF | BUF | 2 | NULL | 0.0 |
| 2026_03_ATL_GB | ATL | 3 | NULL | 0.0 |
| 2026_04_PIT_CLE | CLE | 4 | NULL | 0.0 |
| 2026_05_TB_DAL | DAL | 5 | NULL | 0.0 |
| 2026_06_SEA_DEN | SEA | 6 | NULL | 0.0 |

_0.9s_

## 6. pbp: row count, games and play types

```sql
SELECT COUNT(*) AS row_count, COUNT(DISTINCT game_id) AS games, COUNT(DISTINCT play_type) AS play_types,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.pbp
```

| row_count | games | play_types | first_week | last_week |
|---|---|---|---|---|
| 16380 | 93 | 9 | 1 | 6 |

_1.1s_

## 7. pbp: sample row

```sql
SELECT * FROM NFLVERSE.pbp WHERE game_id = '2026_01_NE_SEA' AND play_type = 'pass' LIMIT 1
```

| column | value |
|---|---|
| game_id | 2026_01_NE_SEA |
| play_id | 86.0 |
| season | 2026 |
| week | 1 |
| season_type | REG |
| posteam | SEA |
| defteam | NE |
| game_half | Half1 |
| qtr | 1.0 |
| down | 1.0 |
| ydstogo | 10.0 |
| yardline_100 | 63.0 |
| play_type | pass |
| pass | 1.0 |
| rush | 0.0 |
| pass_attempt | 1.0 |
| rush_attempt | 0.0 |
| complete_pass | 1.0 |
| passer_player_id | 00-0034869 |
| passer_player_name | S.Darnold |
| receiver_player_id | 00-0038543 |
| receiver_player_name | J.Smith-Njigba |
| rusher_player_id | NULL |
| rusher_player_name | NULL |
| air_yards | 11.0 |
| yards_after_catch | 2.0 |
| yards_gained | 13.0 |
| touchdown | 0.0 |
| pass_touchdown | 0.0 |
| rush_touchdown | 0.0 |
| two_point_attempt | 0.0 |
| interception | 0.0 |
| fumble_lost | 0.0 |
| epa | 0.825319406343624 |

_1.2s_

## 8. pbp: pass rate by team, highest first (Team pass rate and game script factor)

```sql
SELECT posteam, SUM(pass) AS pass_plays, SUM(rush) AS rush_plays,
       ROUND(100 * SUM(pass) / NULLIF(SUM(pass) + SUM(rush), 0), 1) AS pass_rate_pct
FROM NFLVERSE.pbp
WHERE posteam IS NOT NULL
GROUP BY posteam
ORDER BY pass_rate_pct DESC
LIMIT 10
```

| posteam | pass_plays | rush_plays | pass_rate_pct |
|---|---|---|---|
| DAL | 287.0 | 116.0 | 71.2 |
| PIT | 277.0 | 122.0 | 69.4 |
| GB | 260.0 | 123.0 | 67.9 |
| CIN | 212.0 | 105.0 | 66.9 |
| LA | 282.0 | 143.0 | 66.4 |
| HOU | 258.0 | 134.0 | 65.8 |
| PHI | 240.0 | 126.0 | 65.6 |
| TB | 258.0 | 138.0 | 65.2 |
| NO | 273.0 | 147.0 | 65.0 |
| WAS | 257.0 | 140.0 | 64.7 |

_1.3s_

## 9. pbp: most red-zone targets (yardline_100 <= 20; Touchdowns and red zone factor)

```sql
SELECT receiver_player_name, posteam, COUNT(*) AS rz_targets, SUM(pass_touchdown) AS rz_pass_tds
FROM NFLVERSE.pbp
WHERE yardline_100 <= 20 AND receiver_player_id IS NOT NULL AND play_type = 'pass'
GROUP BY receiver_player_name, posteam
ORDER BY rz_targets DESC
LIMIT 10
```

| receiver_player_name | posteam | rz_targets | rz_pass_tds |
|---|---|---|---|
| A.St. Brown | DET | 16 | 4.0 |
| T.McBride | ARI | 13 | 3.0 |
| C.Lamb | DAL | 12 | 3.0 |
| M.Golden | GB | 12 | 3.0 |
| J.Smith-Njigba | SEA | 11 | 5.0 |
| Mi.Wilson | ARI | 10 | 1.0 |
| G.Kittle | SF | 10 | 4.0 |
| I.Likely | NYG | 10 | 4.0 |
| M.Nabers | NYG | 9 | 1.0 |
| C.Loveland | CHI | 9 | 1.0 |

_1.4s_

## 10. snap_counts: row count, players and games

```sql
SELECT COUNT(*) AS row_count, COUNT(DISTINCT pfr_player_id) AS players, COUNT(DISTINCT game_id) AS games,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.snap_counts
```

| row_count | players | games | first_week | last_week |
|---|---|---|---|---|
| 8671 | 1863 | 93 | 1 | 6 |

_37.3s_

## 11. snap_counts: sample row

```sql
SELECT * FROM NFLVERSE.snap_counts WHERE player = 'Christian Watson' AND week = 1
```

| column | value |
|---|---|
| game_id | 2026_01_GB_MIN |
| season | 2026 |
| game_type | REG |
| week | 1 |
| player | Christian Watson |
| pfr_player_id | WatsCh00 |
| position | WR |
| team | GB |
| opponent | MIN |
| offense_snaps | 52.0 |
| offense_pct | 0.76 |

_1.0s_

## 12. snap_counts: WRs with the highest average offensive snap share, 4+ games (Opportunity factor)

```sql
SELECT player, team, COUNT(*) AS games, ROUND(100 * AVG(offense_pct), 1) AS avg_snap_pct
FROM NFLVERSE.snap_counts
WHERE position = 'WR'
GROUP BY player, team
HAVING COUNT(*) >= 4
ORDER BY avg_snap_pct DESC
LIMIT 10
```

| player | team | games | avg_snap_pct |
|---|---|---|---|
| D.K. Metcalf | PIT | 6 | 95.3 |
| Denzel Boston | CLE | 6 | 92.0 |
| Devaughn Vele | NO | 6 | 92.0 |
| Jordan Addison | MIN | 4 | 91.3 |
| Garrett Wilson | NYJ | 6 | 91.3 |
| Michael Wilson | ARI | 6 | 90.3 |
| Jameson Williams | DET | 5 | 90.2 |
| Drake London | ATL | 6 | 90.0 |
| Amon-Ra St. Brown | DET | 5 | 88.2 |
| DeVonta Smith | PHI | 4 | 87.3 |

_1.7s_

## 13. snap_counts: names that differ from player_stats on the same team and game (the join our app uses is by name)

```sql
SELECT sc.player AS snap_counts_name, sc.team, COUNT(*) AS games
FROM NFLVERSE.snap_counts sc
LEFT JOIN NFLVERSE.player_stats ps ON ps.game_id = sc.game_id AND ps.team = sc.team AND ps.player_display_name = sc.player
WHERE ps.player_id IS NULL AND sc.position IN ('QB', 'RB', 'WR', 'TE') AND sc.offense_snaps >= 20
GROUP BY sc.player, sc.team
ORDER BY games DESC, snap_counts_name
LIMIT 15
```

| snap_counts_name | team | games |
|---|---|---|
| Chris Godwin | TB | 6 |
| D.K. Metcalf | PIT | 6 |
| Harold Fannin | CLE | 6 |
| Luther Burden | CHI | 6 |
| Ted Hurst | TB | 6 |
| Brian Thomas | JAX | 5 |
| Deebo Samuel | SF | 5 |
| Kenneth Gainwell | TB | 5 |
| Adam Trautman | DEN | 4 |
| D.J. Moore | BUF | 4 |
| Kevin Coleman | MIA | 4 |
| Mark Redman | GB | 4 |
| Michael Penix | ATL | 4 |
| John Metchie | CAR | 3 |
| Michael Pittman Jr. | PIT | 3 |

_2.4s_

## 14. snap_counts: skill-player rows that find their player_stats row by name (the app's Opportunity join) vs by ID (rosters.pfr_id -> gsis_id)

```sql
SELECT COUNT(*) AS skill_snap_rows,
       SUM(CASE WHEN n.player_id IS NULL THEN 0 ELSE 1 END) AS matched_by_name,
       SUM(CASE WHEN i.player_id IS NULL THEN 0 ELSE 1 END) AS matched_by_id
FROM NFLVERSE.snap_counts sc
LEFT JOIN NFLVERSE.player_stats n ON n.game_id = sc.game_id AND n.team = sc.team AND n.player_display_name = sc.player
LEFT JOIN NFLVERSE.rosters r ON r.pfr_id = sc.pfr_player_id
LEFT JOIN NFLVERSE.player_stats i ON i.game_id = sc.game_id AND i.player_id = r.gsis_id
WHERE sc.position IN ('QB', 'RB', 'WR', 'TE')
```

| skill_snap_rows | matched_by_name | matched_by_id |
|---|---|---|
| 2354 | 1955 | 2059 |

_3.2s_

## 15. snap_counts: Deebo Samuel's snap share by week, joined by name (as the app does) and by ID

```sql
SELECT ps.week, ps.player_display_name, ROUND(100 * n.offense_pct, 1) AS snap_pct_by_name,
       ROUND(100 * i.offense_pct, 1) AS snap_pct_by_id, i.player AS snap_counts_name
FROM NFLVERSE.player_stats ps
LEFT JOIN NFLVERSE.snap_counts n ON n.game_id = ps.game_id AND n.team = ps.team AND n.player = ps.player_display_name
LEFT JOIN NFLVERSE.rosters r ON r.gsis_id = ps.player_id
LEFT JOIN NFLVERSE.snap_counts i ON i.game_id = ps.game_id AND i.pfr_player_id = r.pfr_id
WHERE ps.player_display_name LIKE 'Deebo Samuel%'
ORDER BY ps.week
```

| week | player_display_name | snap_pct_by_name | snap_pct_by_id | snap_counts_name |
|---|---|---|---|---|
| 1 | Deebo Samuel Sr. | NULL | 42.0 | Deebo Samuel |
| 2 | Deebo Samuel Sr. | NULL | 60.0 | Deebo Samuel |
| 3 | Deebo Samuel Sr. | NULL | 76.0 | Deebo Samuel |
| 4 | Deebo Samuel Sr. | NULL | 67.0 | Deebo Samuel |
| 5 | Deebo Samuel Sr. | NULL | 43.0 | Deebo Samuel |

_3.0s_

## 16. depth_charts: row count, snapshots, players and teams

```sql
SELECT COUNT(*) AS row_count, COUNT(DISTINCT dt) AS snapshots, COUNT(DISTINCT gsis_id) AS players,
       COUNT(DISTINCT team) AS teams, MIN(dt) AS first_snapshot, MAX(dt) AS last_snapshot
FROM NFLVERSE.depth_charts
```

| row_count | snapshots | players | teams | first_snapshot | last_snapshot |
|---|---|---|---|---|---|
| 684720 | 251 | 3030 | 32 | 2026-03-22 06:38:42.0 | 2026-10-22 12:59:29.0 |

_1.9s_

## 17. depth_charts: sample row

```sql
SELECT * FROM NFLVERSE.depth_charts WHERE team = 'SF' AND pos_abb = 'WR' AND pos_rank = 1 ORDER BY dt DESC LIMIT 1
```

| column | value |
|---|---|
| dt | 2026-10-22 12:59:29.0 |
| week | 7 |
| team | SF |
| player_name | Mike Evans |
| gsis_id | 00-0031408 |
| pos_grp | 3WR 1TE |
| pos_abb | WR |
| pos_slot | 1 |
| pos_rank | 1 |

_1.3s_

## 18. depth_charts: the 49ers' current WR and TE order (Depth chart factor: latest snapshot only)

```sql
SELECT pos_abb, pos_rank, player_name, pos_slot
FROM NFLVERSE.depth_charts
WHERE team = 'SF' AND pos_abb IN ('WR', 'TE') AND dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = 'SF')
ORDER BY pos_abb, pos_rank, pos_slot
LIMIT 15
```

| pos_abb | pos_rank | player_name | pos_slot |
|---|---|---|---|
| TE | 1 | George Kittle | 10 |
| TE | 2 | Luke Farrell | 10 |
| TE | 3 | Brayden Willis | 10 |
| TE | 4 | Jake Tonges | 10 |
| WR | 1 | Mike Evans | 1 |
| WR | 2 | Deebo Samuel | 2 |
| WR | 3 | Brandin Cooks | 8 |
| WR | 4 | Jordan Watkins | 1 |
| WR | 5 | Jacob Cowing | 2 |
| WR | 6 | Christian Kirk | 8 |
| WR | 7 | Demarcus Robinson | 1 |
| WR | 8 | De'Zhaun Stribling | 2 |
| WR | 9 | Ricky Pearsall | 8 |
| WR | 10 | Brandon Aiyuk | 1 |

_2.3s_

## 19. depth_charts: snapshot rows per team (why the app always filters to MAX(dt))

```sql
SELECT team, COUNT(DISTINCT dt) AS snapshots, COUNT(*) AS rows_all_snapshots
FROM NFLVERSE.depth_charts
GROUP BY team
ORDER BY rows_all_snapshots DESC
LIMIT 5
```

| team | snapshots | rows_all_snapshots |
|---|---|---|
| NYG | 251 | 22703 |
| SF | 251 | 22464 |
| NO | 251 | 22188 |
| CAR | 251 | 21954 |
| GB | 251 | 21936 |

_2.0s_

## 20. injuries: row count, players and weeks

```sql
SELECT COUNT(*) AS row_count, COUNT(DISTINCT gsis_id) AS players, MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.injuries
```

| row_count | players | first_week | last_week |
|---|---|---|---|
| 2062 | 885 | 1 | 7 |

_1.1s_

## 21. injuries: sample row

```sql
SELECT * FROM NFLVERSE.injuries WHERE team = 'SF' AND report_status = 'Out' ORDER BY week LIMIT 1
```

| column | value |
|---|---|
| season | 2026 |
| game_type | REG |
| week | 1 |
| game_date | 2026-09-10 |
| team | SF |
| gsis_id | 00-0040721 |
| full_name | Alfred Collins |
| position | DT |
| report_primary_injury | Knee |
| report_secondary_injury | NULL |
| report_status | Out |
| practice_primary_injury | Knee |
| practice_status | Did Not Participate In Practice |

_1.4s_

## 22. injuries: report status counts (Status and Teammate absences factors)

```sql
SELECT COALESCE(report_status, '(none)') AS report_status, COUNT(*) AS player_weeks
FROM NFLVERSE.injuries
GROUP BY COALESCE(report_status, '(none)')
ORDER BY player_weeks DESC
```

| report_status | player_weeks |
|---|---|
| (none) | 1267 |
| Out | 398 |
| Questionable | 366 |
| Doubtful | 31 |

_0.9s_

## 23. injuries: skill players listed Out in the latest week

```sql
SELECT team, full_name, position, report_primary_injury
FROM NFLVERSE.injuries
WHERE week = (SELECT MAX(week) FROM NFLVERSE.injuries) AND report_status = 'Out' AND position IN ('QB', 'RB', 'WR', 'TE')
ORDER BY team, position, full_name
LIMIT 15
```

| team | full_name | position | report_primary_injury |
|---|---|---|---|
| CHI | Kyle Monangai | RB | Thumb |

_1.3s_

## 24. rosters: row count, players, teams and weeks

```sql
SELECT COUNT(*) AS row_count, COUNT(DISTINCT gsis_id) AS players, COUNT(DISTINCT team) AS teams,
       MIN(week) AS first_week, MAX(week) AS last_week
FROM NFLVERSE.rosters
```

| row_count | players | teams | first_week | last_week |
|---|---|---|---|---|
| 3054 | 3053 | 32 | 1 | 7 |

_1.1s_

## 25. rosters: sample row

```sql
SELECT * FROM NFLVERSE.rosters WHERE full_name = 'Mike Evans'
```

| column | value |
|---|---|
| season | 2026 |
| week | 7 |
| team | SF |
| gsis_id | 00-0031408 |
| pfr_id | EvanMi00 |
| full_name | Mike Evans |
| position | WR |
| depth_chart_position | WR |
| jersey_number | 5 |
| status | ACT |
| status_description_abbr | A01 |
| years_exp | 12 |
| rookie_year | 2014 |
| entry_year | 2014 |

_0.8s_

## 26. rosters: roster status counts (the premise check and the stand-in pool use status ACT)

```sql
SELECT status, COUNT(*) AS players
FROM NFLVERSE.rosters
GROUP BY status
ORDER BY players DESC
```

| status | players |
|---|---|
| ACT | 1665 |
| DEV | 568 |
| CUT | 435 |
| RES | 331 |
| INA | 26 |
| RET | 23 |
| EXE | 3 |
| TRD | 2 |
| TRT | 1 |

_0.9s_

## 27. rosters: rows with no gsis_id (found while building the USL keys)

```sql
SELECT season, week, team, full_name, position, status
FROM NFLVERSE.rosters
WHERE gsis_id IS NULL
```

| season | week | team | full_name | position | status |
|---|---|---|---|---|---|
| 2026 | 7 | NYJ | Al-Jay Henderson | RB | DEV |

_0.7s_

## 28. schedules: row count, weeks, and games played vs not played yet

```sql
SELECT COUNT(*) AS row_count, MIN(week) AS first_week, MAX(week) AS last_week,
       SUM(CASE WHEN home_score IS NULL THEN 0 ELSE 1 END) AS games_played,
       SUM(CASE WHEN home_score IS NULL THEN 1 ELSE 0 END) AS games_not_played
FROM NFLVERSE.schedules
```

| row_count | first_week | last_week | games_played | games_not_played |
|---|---|---|---|---|
| 272 | 1 | 18 | 93 | 179 |

_0.7s_

## 29. schedules: sample row

```sql
SELECT * FROM NFLVERSE.schedules WHERE game_id = '2026_01_NE_SEA'
```

| column | value |
|---|---|
| game_id | 2026_01_NE_SEA |
| season | 2026 |
| game_type | REG |
| week | 1 |
| gameday | 2026-09-09 |
| weekday | Wednesday |
| gametime | 20:20 |
| away_team | NE |
| home_team | SEA |
| away_score | 10 |
| home_score | 13 |
| result | 3 |
| total | 23 |
| overtime | 0 |
| away_rest | 7 |
| home_rest | 7 |
| div_game | 0 |
| roof | outdoors |
| surface | fieldturf |
| away_qb_id | 00-0039851 |
| away_qb_name | Drake Maye |
| home_qb_id | 00-0034869 |
| home_qb_name | Sam Darnold |

_0.7s_

## 30. schedules: week 7 games (the next-matchup factor reads the named week)

```sql
SELECT game_id, gameday, away_team, home_team, away_score, home_score
FROM NFLVERSE.schedules
WHERE week = 7
ORDER BY gameday, game_id
```

| game_id | gameday | away_team | home_team | away_score | home_score |
|---|---|---|---|---|---|
| 2026_07_NE_CHI | 2026-10-22 | NE | CHI | NULL | NULL |
| 2026_07_CIN_BAL | 2026-10-25 | CIN | BAL | NULL | NULL |
| 2026_07_CLE_TEN | 2026-10-25 | CLE | TEN | NULL | NULL |
| 2026_07_DEN_ARI | 2026-10-25 | DEN | ARI | NULL | NULL |
| 2026_07_GB_DET | 2026-10-25 | GB | DET | NULL | NULL |
| 2026_07_IND_MIN | 2026-10-25 | IND | MIN | NULL | NULL |
| 2026_07_KC_SEA | 2026-10-25 | KC | SEA | NULL | NULL |
| 2026_07_LA_LV | 2026-10-25 | LA | LV | NULL | NULL |
| 2026_07_MIA_NYJ | 2026-10-25 | MIA | NYJ | NULL | NULL |
| 2026_07_NYG_HOU | 2026-10-25 | NYG | HOU | NULL | NULL |
| 2026_07_PIT_NO | 2026-10-25 | PIT | NO | NULL | NULL |
| 2026_07_SF_ATL | 2026-10-25 | SF | ATL | NULL | NULL |
| 2026_07_TB_CAR | 2026-10-25 | TB | CAR | NULL | NULL |
| 2026_07_DAL_PHI | 2026-10-26 | DAL | PHI | NULL | NULL |

_0.8s_

## 31. schedules: bye weeks so far (weeks 1-7) per team, from home and away games

```sql
SELECT team, 7 - COUNT(*) AS byes_in_weeks_1_to_7
FROM (SELECT home_team AS team FROM NFLVERSE.schedules WHERE week <= 7
      UNION ALL SELECT away_team AS team FROM NFLVERSE.schedules WHERE week <= 7) t
GROUP BY team
HAVING COUNT(*) < 7
ORDER BY team
```

| team | byes_in_weeks_1_to_7 |
|---|---|
| BUF | 1 |
| CAR | 1 |
| CIN | 1 |
| DET | 1 |
| JAX | 1 |
| KC | 1 |
| LAC | 1 |
| MIA | 1 |
| MIN | 1 |
| WAS | 1 |

_1.4s_

31 statements, 0 errors.
