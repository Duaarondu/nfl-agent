# 1a. Use case and data sources

## The use case: fantasy decisions explained with evidence

Fantasy football managers make a few decisions every week: who to start, who to pick up
off waivers, and who replaces an injured starter. The NFL Fantasy Agent answers those
questions with a verdict, and every number behind the verdict is backed by the SQL query
and rows it came from:

- **"Who becomes the Bucs' WR1 if Mike Evans is out?"** First the agent corrects the
  premise from the rosters: Evans plays for SF in 2026. Then it ranks the WRs below him
  on the 49ers' depth chart by recent target share.
- **"Why is Christian Watson scoring so many fantasy points this season?"** The agent
  looks at weekly snap and target share, teammates on the injury report, the team's pass
  rate, big plays, red-zone usage and the opponents he faced.
- **"Pickens or Olave?"** It compares the two players factor by factor.

Three agents do the work: a Planner, an Analyst (one small factor agent per factor) and
a Critic. The Critic checks every claim against the rows. It also tests timing: did the
rise in target share really start the week the teammate got hurt?

The data is all live in Zetaris: seven nflverse tables registered as `NFLVERSE`
filestore tables over Parquet (`sql/nflverse_create.sql`). The app reads them through
one adapter (`app/adapters/zetaris.py`, one SQL statement per call). The factor queries
are in `app/agents/factor_queries.py`.

## The seven sources

All seven tables cover one season, 2026. The row counts are from the live cluster
([02-exploratory-queries.md](02-exploratory-queries.md)), up to the latest week loaded:
week 6 for game stats, week 7 for rosters, injuries and depth charts.

| Table | What it holds | Grain | Key columns | Rows | Agent factors that use it |
|---|---|---|---|---|---|
| `player_stats` | Box-score stats and fantasy points (standard and PPR) per player per game: targets, target share, carries, yards, TDs, air yards | One row per player per game | `player_id` (GSIS) + `game_id`; also `season`, `week`, `team`, `opponent_team` | 6,488 | Opportunity, Big plays, Touchdowns and red zone, Matchups (points allowed by opponent), Team usage, Points per game, Games without the player, every compare factor (Weekly opportunity, Team usage share, Recent trend, Touchdown share), Next matchup, last-name lookup |
| `pbp` | Play by play: offense and defense team, down and distance, yard line, play type, passer, receiver, rusher, yards gained, TDs, EPA | One row per play | `game_id` + `play_id`; player IDs `passer_player_id`, `receiver_player_id`, `rusher_player_id` (GSIS) | 16,380 | Team pass rate and game script, Big plays (20+ yard plays, longest play), Touchdowns and red zone (targets and carries inside the 20) |
| `snap_counts` | Offensive snaps and snap share | One row per player per game | `game_id` + `pfr_player_id` (Pro Football Reference ID, **no GSIS ID**); `player` (name), `team` | 8,671 | Opportunity and Weekly opportunity (snap %). The app joins it to `player_stats` **by name**; see [05-reflection.md](05-reflection.md) |
| `depth_charts` | Depth chart order by position and formation slot | One row per player per slot per snapshot (251 snapshots between March and October) | `gsis_id`, `team`, `dt` (snapshot time), `pos_abb`, `pos_rank` | 684,720 | Depth chart (who is next up: replacement and pickup questions), the Critic's stand-in rule |
| `injuries` | Weekly injury report: report status (Out, Doubtful, Questionable), injury, practice status | One row per player per week | `gsis_id` + `season` + `game_type` + `week` | 2,062 | Status, Teammate absences, the Depth chart's injury column, Next matchup (injury that week), the Critic's Questionable/Doubtful exception |
| `rosters` | Team, position, roster status (ACT, RES, DEV, ...) and IDs | One row per player (the latest week each was rostered) | `gsis_id`; also `pfr_id` (links `snap_counts`) | 3,054 | Player lookup and the wrong-premise check (which team the player is really on), last-name and closest-name lookups, roster status for stand-ins, H-MEM league memory's roster lookup |
| `schedules` | Games, teams, scores, rest days, starting QBs | One row per game (272: 93 played, 179 not played yet) | `game_id` (`season_week_away_home`); `home_team`, `away_team` | 272 | Team pass rate and game script (final margin), Games without the player, Next matchup (opponent and bye week) |

How the tables connect (from `app/agents/schema.md`, which the Analyst's SQL prompt
uses):

- **GSIS player ID:** `player_stats.player_id` = `pbp.*_player_id` = `rosters.gsis_id` =
  `injuries.gsis_id` = `depth_charts.gsis_id`.
- **snap_counts has no GSIS ID:** link it through `snap_counts.pfr_player_id` =
  `rosters.pfr_id`, or by name.
- **game_id** links `player_stats`, `pbp`, `snap_counts` and `schedules`.
- **Team codes** (SF, GB, ...) are shared by every table.

The USL ([03-nfl-usl.sql](03-nfl-usl.sql)) declares the main joins as keys:
`player.gsis_id`, `game.game_id` and `team.team`. Foreign keys run from
`player_week` and `injury_report` to `player`, from `player_week` to `game`, and from
`game` and `player` to `team`.

Data: nflverse (CC-BY 4.0); FTN Data via nflverse (CC-BY-SA 4.0).
