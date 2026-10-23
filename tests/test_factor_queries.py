import re

import pytest

from app.adapters.zetaris import run_sql
from app.agents import factor_queries as fq

SEASON, WEEK = 2026, 6
WATSON = fq.Player("00-0038972", "Christian Watson", "GB", "WR", "ACT", 7)


def lookup(question):
    result = run_sql(fq.lookup_sql(fq.name_candidates(question), SEASON))
    return fq.parse_players(result["data"], question)


def test_name_candidates_find_full_names_any_case():
    assert "christian watson" in fq.name_candidates("why is christian watson so good?")
    assert "mike evans" in fq.name_candidates("Mike Evans's role? Is Mike Evans out.")


def test_lookup_finds_players_in_question_order(real_sample):
    players = lookup("Start George Kittle or Christian Watson?")
    assert [(p.name, p.team, p.position) for p in players] == [
        ("George Kittle", "SF", "TE"), ("Christian Watson", "GB", "WR"),
    ]


def test_lookup_quotes_apostrophes(real_sample):
    sql = fq.lookup_sql(fq.name_candidates("Is De'Zhaun Stribling worth it?"), SEASON)
    assert "'de''zhaun stribling'" in sql
    run_sql(sql)  # runs without a syntax error


@pytest.mark.parametrize("bundle", ["why", "team"])
def test_every_planned_query_runs_on_sample_data(real_sample, bundle):
    [player] = lookup("Christian Watson")
    planned = fq.why_bundle(player, SEASON) if bundle == "why" else fq.team_bundle(player, SEASON, WEEK)
    for p in planned:
        result = run_sql(p.sql)
        assert p.factor == "Status" or result["data"], p.factor


def test_planned_sql_is_portable():
    """Plain SQL only: the same text has to run on Spark SQL and DuckDB."""
    for p in fq.why_bundle(WATSON, SEASON) + fq.team_bundle(WATSON, SEASON, WEEK):
        assert not re.search(r"(?i)\bilike\b|\bqualify\b|::|\"|;", p.sql), p.factor
        assert "NFLVERSE." in p.sql


def test_why_bundle_covers_every_factor():
    assert [p.factor for p in fq.why_bundle(WATSON, SEASON)] == ["Status", *fq.WHY_FACTORS]


def test_why_question_detection():
    assert fq.is_why_question("Why is Watson scoring?")
    assert fq.is_why_question("What explains his breakout?")
    assert not fq.is_why_question("Who becomes the WR1?")


@pytest.mark.parametrize(
    "question, wrong",
    [
        ("Who becomes the Bucs' WR1 if Watson is out?", ["TB"]),
        ("Is Watson the Tampa Bay WR1?", ["TB"]),
        ("Watson vs the Bucs: start him?", []),
        ("Should I start Watson against Tampa?", []),
        ("Is Watson the Packers' WR1?", []),
        ("Watson left the Bucs for the Packers?", []),
        ("Why is Watson scoring?", []),
    ],
)
def test_wrong_teams(question, wrong):
    assert fq.wrong_teams(question, WATSON) == wrong


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Why is Watson scoring so much?", "why"),
        ("Mike Evans is out. Who becomes the 49ers' WR1?", "replacement"),
        ("Should I start Watson or Kittle?", "start_sit"),
        ("Is Watson worth a waiver claim?", "waiver"),
        ("How old is Watson?", "other"),
    ],
)
def test_guess_question_type(question, expected):
    assert fq.guess_question_type(question) == expected


def test_plan_picks_bundle_by_question_type():
    assert [p.factor for p in fq.plan("why", WATSON, SEASON, WEEK)][1] == "Opportunity"
    for qt in ("start_sit", "waiver", "other"):
        assert [p.factor for p in fq.plan(qt, WATSON, SEASON, WEEK)] == ["Status", "Team usage", "Depth chart"]
    assert [p.factor for p in fq.plan("replacement", WATSON, SEASON, WEEK)] == [
        "Status", "Team usage", "Depth chart", "Games without the player",
    ]


def test_summaries_do_the_arithmetic(real_sample):
    [player] = lookup("Christian Watson")
    lines = {}
    for p in fq.why_bundle(player, SEASON):
        result = run_sql(p.sql)
        lines[p.factor] = " ".join(fq.summarize(p.factor, result["headers"], result["data"]))

    assert "6 games, 48 targets" in lines["Opportunity"]
    assert "Target share: 25.8% in weeks 1-3 vs 18.6% in weeks 4-6." in lines["Opportunity"]
    assert "Week 3: Jayden Reed (WR, Out)." in lines["Teammate absences"]
    assert "Pass rate 76.2% in losses vs 63.2% in wins or ties." in lines["Team pass rate and game script"]
    assert "11.2 yards per target" in lines["Big plays"] and "10 plays of 20+ yards" in lines["Big plays"]
    assert "6 touchdowns = 36 of 118.8 PPR points (30.3%)" in lines["Touchdowns and red zone"]
    assert "16 PPR per game vs top-10 soft defenses (2 games)" in lines["Matchups"]


def test_summaries_handle_empty_and_single_rows():
    assert fq.summarize("Status", ["week"], []) == ["No injury report entries this season."]
    assert fq.summarize("Opportunity", ["week"], []) == ["No rows."]
    one = fq.summarize(
        "Opportunity",
        ["week", "snap_pct", "targets", "target_share_pct", "ppr_points"],
        [["1", "80.0", "8", "20.0", "12.5"]],
    )
    assert one[0].startswith("1 games, 8 targets") and len(one) == 2  # no early/late split


def test_summary_numbers_have_at_most_one_decimal(real_sample):
    [player] = lookup("Christian Watson")
    for p in fq.why_bundle(player, SEASON) + fq.team_bundle(player, SEASON, WEEK):
        result = run_sql(p.sql)
        for line in fq.summarize(p.factor, result["headers"], result["data"]):
            assert not re.search(r"\d\.\d{2,}", line), line


def watson_results():
    [player] = lookup("Christian Watson")
    out = {}
    for p in fq.why_bundle(player, SEASON):
        result = run_sql(p.sql)
        out[p.factor] = (result["headers"], result["data"])
    return out


def test_rule_ratings_on_sample_data(real_sample):
    results = watson_results()
    ratings = {f: fq.rule_rating(f, results) for f in fq.WHY_FACTORS}

    assert ratings["Opportunity"][0] == "strong"  # 22.2% target share, 80.3% snaps
    assert ratings["Big plays"][0] == "strong"  # 11.2 yards per target
    assert ratings["Touchdowns and red zone"][0] == "moderate"  # 30.3% of PPR from TDs
    assert ratings["Matchups"][0] == "not supported"  # 16 vs soft, 21.7 vs the rest
    # Absence weeks 3, 5, 6: 21.4 PPR per game vs 18.2 in weeks 1, 2, 4.
    assert ratings["Teammate absences"] == (
        "moderate",
        "PPR per game in weeks with a teammate out minus other weeks: 3.2 (strong >= 5, moderate >= 2, weak > 0)",
    )
    assert all(r[0] in ("strong", "moderate", "weak", "not supported") and r[1] for r in ratings.values())


def test_rule_ratings_without_data():
    assert fq.rule_rating("Big plays", {}) == ("not supported", "no rows")
    assert fq.rule_rating("Teammate absences", {})[0] == "not supported"
    assert fq.rule_rating("Opportunity", {"Opportunity": (["week", "target_share_pct", "snap_pct"], [["1", "30.0", "50.0"]])})[0] == "moderate"


def test_corrected_question_swaps_in_the_actual_team():
    assert fq.corrected_question("Who becomes the Bucs' WR1 if Evans is out?", ["TB"], "SF") == (
        "Who becomes the 49ers' WR1 if Evans is out?"
    )
    assert fq.corrected_question("Is he the Tampa Bay WR1?", ["TB"], "GB") == "Is he the Packers WR1?"


def without_results(name):
    [player] = lookup(name)
    p = fq.games_without_query(player, SEASON)
    result = run_sql(p.sql)
    return player, {p.factor: (result["headers"], result["data"])}


def test_games_without_the_player_splits_teammates_targets(real_sample):
    player, results = without_results("Puka Nacua")  # missed 2 of LA's 6 games
    headers, rows = results["Games without the player"]

    assert {r[0] for r in rows} == {"missed", "played"}
    lines = fq.summarize("Games without the player", headers, rows)
    assert lines[0] == "He missed 2 team games this season."
    assert lines[1].startswith("Target share in the games he missed: Davante Adams (WR) 29.9% (vs 16.4% with him)")
    assert fq.rule_rating("Games without the player", results) == (
        "moderate", "2 games without him (strong >= 3, moderate 2, weak 1)",
    )


def test_games_without_when_he_never_missed(real_sample):
    _, results = without_results("Mike Evans")
    headers, rows = results["Games without the player"]
    assert fq.summarize("Games without the player", headers, rows) == [
        "He played every team game this season; there are no games without him to compare."
    ]
    assert fq.rule_rating("Games without the player", results)[0] == "not supported"


def test_rule_verdicts(real_sample):
    nacua, results = without_results("Puka Nacua")
    ranked = [("Games without the player", "moderate", "He missed 2 team games this season. More.")]
    verdict, why = fq.rule_verdict("replacement", nacua, results, ranked)
    assert verdict == "Pick up Davante Adams if available"
    assert why == "Most supported by the data: Games without the player (moderate): He missed 2 team games this season."

    usage = fq.team_bundle(WATSON, SEASON, WEEK)[1]
    result = run_sql(usage.sql)
    team = {"Team usage": (result["headers"], result["data"])}
    assert fq.rule_verdict("start_sit", WATSON, team, [])[0] == "Start Christian Watson"  # 19.8 PPR per game
    assert fq.rule_verdict("waiver", WATSON, team, [])[0].startswith(("Pick up", "Hold off on"))
    assert fq.rule_verdict("why", WATSON, {}, [("Matchups", "not supported", "x")]) == (
        "Hold Christian Watson", "No factor is strongly supported by the data. Not supported: Matchups.",
    )
