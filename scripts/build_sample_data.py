"""Build nflverse Parquet files for the current season: python scripts/build_sample_data.py

Writes each table twice, with the same columns:
    data/full/NFLVERSE/<table>.parquet    gitignored; for uploading to Zetaris
    data/sample/NFLVERSE/<table>.parquet  committed; must stay under 5 MB
One season of these columns fits under 5 MB, so both copies currently hold
every row and sample mode answers the same as Zetaris. The build fails if a
sample file grows past 5 MB.

Derived columns (not in nflverse):
    depth_charts.week       week of the team's next game on or after the snapshot date
    injuries.game_date      the team's game date for that week
Times in depth_charts.dt are UTC.
"""

from __future__ import annotations

import sys
from pathlib import Path

import nflreadpy as nfl
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
FULL_DIR = REPO_ROOT / "data" / "full" / "NFLVERSE"
SAMPLE_DIR = REPO_ROOT / "data" / "sample" / "NFLVERSE"
MAX_SAMPLE_BYTES = 5 * 1024 * 1024

COLUMNS = {
    "player_stats": [
        "player_id", "player_name", "player_display_name", "position", "season", "week",
        "season_type", "game_id", "team", "opponent_team",
        "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
        "passing_air_yards", "passing_2pt_conversions",
        "carries", "rushing_yards", "rushing_tds", "rushing_2pt_conversions",
        "receptions", "targets", "receiving_yards", "receiving_tds", "receiving_air_yards",
        "receiving_yards_after_catch", "receiving_2pt_conversions",
        "target_share", "air_yards_share", "wopr", "fumbles_lost_total",
        "fantasy_points", "fantasy_points_ppr",
    ],
    "pbp": [
        "game_id", "play_id", "season", "week", "season_type", "posteam", "defteam",
        "game_half", "qtr", "down", "ydstogo", "yardline_100",
        "play_type", "pass", "rush", "pass_attempt", "rush_attempt", "complete_pass",
        "passer_player_id", "passer_player_name", "receiver_player_id", "receiver_player_name",
        "rusher_player_id", "rusher_player_name",
        "air_yards", "yards_after_catch", "yards_gained",
        "touchdown", "pass_touchdown", "rush_touchdown", "two_point_attempt",
        "interception", "fumble_lost", "epa",
    ],
    "snap_counts": [
        "game_id", "season", "game_type", "week", "player", "pfr_player_id", "position",
        "team", "opponent", "offense_snaps", "offense_pct",
    ],
    "depth_charts": [
        "dt", "week", "team", "player_name", "gsis_id", "pos_grp", "pos_abb", "pos_slot",
        "pos_rank",
    ],
    "injuries": [
        "season", "game_type", "week", "game_date", "team", "gsis_id", "full_name", "position",
        "report_primary_injury", "report_secondary_injury", "report_status",
        "practice_primary_injury", "practice_status",
    ],
    "rosters": [
        "season", "week", "team", "gsis_id", "pfr_id", "full_name", "position",
        "depth_chart_position", "jersey_number", "status", "status_description_abbr",
        "years_exp", "rookie_year", "entry_year",
    ],
    "schedules": [
        "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime",
        "away_team", "home_team", "away_score", "home_score", "result", "total", "overtime",
        "away_rest", "home_rest", "div_game", "roof", "surface",
        "away_qb_id", "away_qb_name", "home_qb_id", "home_qb_name",
    ],
}


def team_games(schedules: pl.DataFrame) -> pl.DataFrame:
    """One row per team per game: season, game_type, week, team, game_date."""
    keys = ["season", "game_type", "week", "gameday"]
    return (
        pl.concat(
            [
                schedules.select(*keys, team=pl.col("home_team")),
                schedules.select(*keys, team=pl.col("away_team")),
            ]
        )
        .rename({"gameday": "game_date"})
        .sort("game_date")
    )


def add_depth_week(depth: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    depth = depth.with_columns(
        pl.col("dt").str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%SZ")
    ).with_columns(snapshot_date=pl.col("dt").dt.date()).sort("snapshot_date")
    return depth.join_asof(
        games.select("team", "game_date", "week"),
        left_on="snapshot_date",
        right_on="game_date",
        by="team",
        strategy="forward",
        check_sortedness=False,  # both sides are sorted above
    )


def add_injury_date(injuries: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    return injuries.join(
        games, on=["season", "game_type", "week", "team"], how="left"
    )


def write(table: str, frame: pl.DataFrame) -> None:
    FULL_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    sample_path = SAMPLE_DIR / f"{table}.parquet"
    frame.write_parquet(FULL_DIR / f"{table}.parquet")
    frame.write_parquet(sample_path)
    size = sample_path.stat().st_size
    print(f"{table:13} {frame.height:>7} rows  {size / 1e6:5.2f} MB")
    if size > MAX_SAMPLE_BYTES:
        raise SystemExit(f"{sample_path} is over 5 MB; add a row filter for {table}.")


def main() -> int:
    season = nfl.get_current_season()
    print(f"Building nflverse data for season {season}")

    schedules = nfl.load_schedules([season]).with_columns(
        pl.col("gameday").str.strptime(pl.Date, "%Y-%m-%d")
    )
    games = team_games(schedules)

    tables = {
        "player_stats": nfl.load_player_stats([season]),
        "pbp": nfl.load_pbp([season]),
        "snap_counts": nfl.load_snap_counts([season]),
        "depth_charts": add_depth_week(nfl.load_depth_charts([season]), games),
        "injuries": add_injury_date(nfl.load_injuries([season]), games),
        "rosters": nfl.load_rosters([season]),
        "schedules": schedules,
    }
    for table, frame in tables.items():
        write(table, frame.select(COLUMNS[table]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
