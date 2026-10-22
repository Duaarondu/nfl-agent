import json

import duckdb
import pytest

from app.adapters import zetaris
from app.adapters.zetaris import ZetarisError, run_sql


@pytest.fixture
def sample_dir(tmp_path, monkeypatch):
    schema_dir = tmp_path / "NFLVERSE"
    schema_dir.mkdir()
    target = (schema_dir / "player_stats.parquet").as_posix()
    duckdb.sql(
        f"""
        COPY (
            SELECT * FROM (VALUES
                ('00-0031408', 'M.Evans', 'TB', 1, 9, 1.5, true),
                ('00-0031408', 'M.Evans', 'TB', 2, 7, NULL, false),
                ('00-0036900', 'J.Chase', 'CIN', 1, 12, 2.0, true)
            ) AS t(player_id, player_name, team, week, targets, epa, active)
        ) TO '{target}' (FORMAT parquet)
        """
    )
    monkeypatch.setattr(zetaris, "SAMPLE_DIR", tmp_path)
    monkeypatch.setattr(zetaris, "CACHE_DIR", tmp_path / "zetaris_cache")
    monkeypatch.setattr(zetaris, "_duckdb", None)
    monkeypatch.setenv("SAMPLE_MODE", "true")
    yield tmp_path
    if zetaris._duckdb is not None:
        zetaris._duckdb.close()


def test_two_part_name_returns_live_shape(sample_dir):
    result = run_sql(
        "SELECT week, targets FROM NFLVERSE.player_stats "
        "WHERE player_name = 'M.Evans' ORDER BY week"
    )
    assert result["headers"] == ["week", "targets"]
    assert result["data"] == [["1", "9"], ["2", "7"]]
    assert result["total"] == 2
    assert isinstance(result["timeUsed"], int)


def test_values_formatted_like_live(sample_dir):
    result = run_sql("SELECT epa, active FROM NFLVERSE.player_stats ORDER BY week, player_id")
    assert result["data"] == [["1.5", "true"], ["2.0", "true"], [None, "false"]]


def test_dates_and_timestamps_formatted_like_live(sample_dir):
    result = run_sql(
        "SELECT TIMESTAMP '2026-03-22 07:35:35' AS a, "
        "TIMESTAMP '2026-03-22 07:35:35.120' AS b, DATE '2026-09-13' AS c"
    )
    assert result["data"] == [["2026-03-22 07:35:35.0", "2026-03-22 07:35:35.12", "2026-09-13"]]


def test_names_are_case_insensitive(sample_dir):
    result = run_sql("select count(*) from nflverse.PLAYER_STATS")
    assert result["data"] == [["3"]]


def test_limit_applied(sample_dir):
    result = run_sql("SELECT * FROM NFLVERSE.player_stats", limit=2)
    assert result["total"] == 2
    assert len(result["data"]) == 2


def test_with_query_and_trailing_semicolon(sample_dir):
    result = run_sql(
        "WITH t AS (SELECT team, SUM(targets) AS tgt FROM NFLVERSE.player_stats GROUP BY team) "
        "SELECT tgt FROM t WHERE team = 'TB';"
    )
    assert result["data"] == [["16"]]


def test_rejects_multiple_statements(sample_dir):
    with pytest.raises(ZetarisError, match="exactly one"):
        run_sql("SELECT 1; SELECT 2")


def test_rejects_non_select(sample_dir):
    with pytest.raises(ZetarisError, match="SELECT and WITH"):
        run_sql("DROP VIEW NFLVERSE.player_stats")


def test_unknown_table_raises_zetaris_error(sample_dir):
    with pytest.raises(ZetarisError, match="Sample query failed"):
        run_sql("SELECT * FROM NFLVERSE.no_such_table")


def test_live_failure_falls_back_to_exact_sql_cache(sample_dir, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "false")

    def fail(sql, limit):
        raise ZetarisError("live down")

    monkeypatch.setattr(zetaris, "_run_live", fail)
    cached = {"headers": ["a"], "data": [["1"]], "total": 1, "timeUsed": 0}
    path = zetaris._cache_path("SELECT 1 AS a")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(cached), encoding="utf-8")

    assert run_sql("select   1 as a") == cached
    with pytest.raises(ZetarisError, match="live down"):
        run_sql("SELECT 2 AS a")
