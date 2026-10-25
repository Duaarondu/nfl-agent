"""Spark sweep: run EVERY planned query against the live Zetaris cluster and report failures.

    python scripts/check_factor_queries_live.py

Sample mode runs the same SQL on DuckDB, which accepts things Spark SQL rejects (the
Team usage ORDER BY SUM(targets) bug, run 7bfa81c3abf1). This runs, live:
  - the season context and player lookup queries the Analyst runs first,
  - every factor query for every question type (why, replacement, start_sit, waiver,
    other) in every league scoring (PPR, half-PPR, standard),
  - the compare (two players, head to head) queries for COMPARE_PAIRS in every scoring,
  - the matchup for a week the question names (the latest week, already played, and
    the next one), and the last-name lookup ("Bowers") in every scoring,
  - league memory's roster lookup,
for Christian Watson, Mike Evans, Puka Nacua and Christian McCaffrey (RB). Identical
SQL is run once, and each is timed.

A query that fails with a cluster or transport error (read timeout, Thrift
TTransportException, "Could not create ResultSet") is retried once after a pause, and
reported separately: those say the cluster struggled, not that Spark rejected the SQL.
Exit code 1 if any query has a SQL error or still fails after its retry.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SAMPLE_MODE"] = "false"  # always the live cluster

from app.adapters.zetaris import ZetarisError, run_sql  # noqa: E402
from app.agents import factor_queries as fq  # noqa: E402
from app.agents import memory  # noqa: E402

PLAYERS = ("Christian Watson", "Mike Evans", "Puka Nacua", "Christian McCaffrey",
           "Jameson Williams", "George Pickens", "Trey McBride", "Brock Bowers")
# Two WRs, an RB vs a WR (the matchup query ranks points allowed per position), two TEs.
COMPARE_PAIRS = (("Jameson Williams", "George Pickens"), ("Christian McCaffrey", "Mike Evans"),
                 ("Trey McBride", "Brock Bowers"))
LAST_NAMES = ["Bowers", "McBride", "Johnson"]
SLOW_SECONDS = 20.0
RETRY_PAUSE = 15.0
SEASON_SQL = "SELECT MAX(season) AS season, MAX(week) AS latest_week FROM NFLVERSE.player_stats"
INFRA_ERROR = re.compile(r"timed out|TTransportException|Could not create ResultSet|Cannot reach|HTTP 5\d\d", re.I)


def is_infra(error: str) -> bool:
    return INFRA_ERROR.search(error) is not None


def timed(sql: str) -> tuple[float, int | None, str | None]:
    started = time.perf_counter()
    try:
        rows = len(run_sql(sql)["data"])
        return time.perf_counter() - started, rows, None
    except ZetarisError as error:
        return time.perf_counter() - started, None, str(error)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    queries: dict[str, list[str]] = {}  # sql -> where it is used

    seconds, rows, error = timed(SEASON_SQL)
    if error:
        print(f"FAILED season context: {error[:300]}")
        return 1
    season, week = (int(v) for v in run_sql(SEASON_SQL)["data"][0])
    print(f"Live cluster: season {season}, latest week {week} ({seconds:.1f}s)\n")

    lookup = fq.lookup_sql([p.lower() for p in PLAYERS], season)
    queries.setdefault(lookup, []).append("player lookup")
    players = fq.parse_players(run_sql(lookup)["data"], " ".join(PLAYERS))
    missing = [n for n in PLAYERS if not any(fq.same_player(p.name, n) for p in players)]
    if missing:
        print(f"FAILED player lookup: not found {missing}")
        return 1

    for p in players:
        for qt in fq.QUESTION_TYPES:
            if qt == "compare":
                continue  # two players: below
            for scoring in fq.SCORINGS.values():
                for planned in fq.plan(qt, p, season, week, scoring):
                    queries.setdefault(planned.sql, []).append(f"{p.name} / {qt} / {scoring.label} / {planned.factor}")
    by_name = {n: next(p for p in players if fq.same_player(p.name, n)) for n in PLAYERS}
    for scoring in fq.SCORINGS.values():
        queries.setdefault(fq.last_name_lookup_sql(LAST_NAMES, season, scoring), []).append(
            f"last-name lookup / {scoring.label}")
        for p in players:
            for named in (week, week + 1):  # already played, and the next week
                q = fq.matchup_query([p], season, week, scoring, named)
                queries.setdefault(q.sql, []).append(f"{p.name} / matchup week {named} / {scoring.label}")
    for a, b in COMPARE_PAIRS:
        for scoring in fq.SCORINGS.values():
            for planned in fq.compare_bundle([by_name[a], by_name[b]], season, week, scoring, week + 1):
                queries.setdefault(planned.sql, []).append(f"{a} vs {b} / compare / {scoring.label} / {planned.factor}")
    _, _, roster_sql = memory.resolve_players(["George Kittle", "Adams"])
    queries.setdefault(roster_sql, []).append("league memory roster lookup")

    print(f"{len(queries)} distinct queries ({sum(len(v) for v in queries.values())} uses)\n")
    failures, slow, retried = [], [], []
    for i, (sql, uses) in enumerate(queries.items(), 1):
        label = uses[0] + (f" (+{len(uses) - 1} more)" if len(uses) > 1 else "")
        seconds, rows, error = timed(sql)
        note = ""
        if error and is_infra(error):
            retried.append((label, seconds, error[:160]))
            time.sleep(RETRY_PAUSE)  # let the cluster recover before the retry
            seconds, rows, error = timed(sql)
            note = " (after a retry)"
        status = "FAIL" if error else "ok  "
        shown = "" if error else f"{rows} rows"
        print(f"[{i:>3}] {status} {seconds:5.1f}s {shown:>9}  {label}{note}", flush=True)
        if error:
            failures.append((label, uses, sql, error, "cluster" if is_infra(error) else "SQL"))
        elif seconds >= SLOW_SECONDS:
            slow.append((label, seconds))

    print()
    for label, seconds in slow:
        print(f"SLOW ({seconds:.1f}s): {label}")
    for label, first, error in retried:
        print(f"RETRIED (first try {first:.1f}s): {label}: {error}")
    for label, uses, sql, error, kind in failures:
        print()
        print(f"FAILED ({kind} error): {label}")
        print(f"  used by: {'; '.join(uses[:6])}")
        print(f"  sql: {sql}")
        print(f"  error: {error[:600]}")
    sql_errors = sum(1 for f in failures if f[4] == "SQL")
    print()
    print(f"{len(queries) - len(failures)}/{len(queries)} queries passed on live Zetaris "
          f"({sql_errors} SQL errors, {len(failures) - sql_errors} cluster errors after a retry); "
          f"{len(retried)} needed a retry; {len(slow)} slower than {SLOW_SECONDS:.0f}s.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
