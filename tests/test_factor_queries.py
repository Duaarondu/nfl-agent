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
        # A pickup or start because a player is out asks who replaces him (run 994c234341e5).
        ("Should I pick up a 49ers receiver if Evans misses time?", "replacement"),
        ("Who should I start if Kittle is ruled out?", "replacement"),
        ("Should I pick up Jauan Jennings?", "waiver"),
        # Two players, full names: start which one?
        ("I have Jameson Williams on my bench and George Pickens in my starting lineup, who should I pick?", "compare"),
        ("Jameson Williams or George Pickens this week?", "compare"),
        ("Jameson Williams vs George Pickens", "compare"),
        ("Should I start Jameson Williams over George Pickens?", "compare"),
        ("Choose between Jameson Williams and George Pickens.", "compare"),
        ("Why is George Pickens better than Jameson Williams?", "why"),
        ("Should I start George Pickens or bench him?", "start_sit"),
    ],
)
def test_guess_question_type(question, expected):
    assert fq.guess_question_type(question) == expected


@pytest.mark.parametrize("question, name, out", [
    ("Should I pick up a 49ers receiver if Evans misses time?", "Mike Evans", True),
    ("Who becomes the Bucs' WR1 if Mike Evans is out?", "Mike Evans", True),
    ("Mike Evans is out. Who becomes the 49ers' WR1?", "Mike Evans", True),
    ("If Kittle is out, should I pick up Mike Evans?", "Mike Evans", False),  # Kittle is out, not Evans
    ("Is Mike Evans worth a pickup?", "Mike Evans", False),
])
def test_says_out(question, name, out):
    assert fq.says_out(question, name) is out


def test_rule_verdict_never_picks_up_the_player_who_is_out(real_sample):
    evans, results = without_results("Mike Evans")
    usage = fq.team_bundle(evans, SEASON, WEEK)[1]
    result = run_sql(usage.sql)
    results["Team usage"] = (result["headers"], result["data"])
    # Evans leads the 49ers in target share, so the waiver rule alone says "Pick up Mike Evans".
    assert fq.rule_verdict("waiver", evans, results, [])[0] == "Pick up Mike Evans"
    verdict, _ = fq.rule_verdict("waiver", evans, results, [], out=True)
    # With no depth chart rows, the stand-in is a WR from the usage rows, not TE Kittle (QA run).
    assert verdict == "Pick up Deebo Samuel Sr. if available"


def test_plan_picks_bundle_by_question_type():
    assert [p.factor for p in fq.plan("why", WATSON, SEASON, WEEK)][1] == "Opportunity"
    assert [p.factor for p in fq.plan("other", WATSON, SEASON, WEEK)] == ["Status", "Team usage", "Depth chart"]
    for qt in ("start_sit", "waiver"):  # plus the matchup
        assert [p.factor for p in fq.plan(qt, WATSON, SEASON, WEEK)] == [
            "Status", "Team usage", "Depth chart", "Next matchup"]
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


def test_sentences_keep_name_suffixes_and_numbered_lists_whole():
    assert fq.sentences("Deebo Samuel Sr. (WR) 11.1%. Depth order: 1. Mike Evans, 2. Deebo Samuel. Longest 81. Done.") == [
        "Deebo Samuel Sr. (WR) 11.1%.", "Depth order: 1. Mike Evans, 2. Deebo Samuel.", "Longest 81.", "Done.",
    ]


def test_same_player_ignores_suffixes_case_and_apostrophes():
    assert fq.same_player("Deebo Samuel Sr.", "deebo samuel")
    assert fq.same_player("De'Zhaun Stribling", "DeZhaun Stribling")
    assert not fq.same_player("Deebo Samuel", "Samuel")
    assert not fq.same_player("", "")


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
    for q in fq.team_bundle(nacua, SEASON, WEEK):
        r = run_sql(q.sql)
        results[q.factor] = (r["headers"], r["data"])
    ranked = [("Games without the player", "moderate", "He missed 2 team games this season. More.")]
    verdict, why = fq.rule_verdict("replacement", nacua, results, ranked)
    # A WR below Nacua who can play: not Davante Adams, who is on reserve (RES; QA run).
    assert verdict == "Pick up Konata Mumpfield if available"
    assert why == (
        "Most supported by the data: Games without the player (moderate): He missed 2 team games this season. "
        "Konata Mumpfield has the most recent target share among the WRs below Puka Nacua on the depth chart (9.4%). "
        "He averages 5.3 PPR points per game this season."
    )

    usage = fq.team_bundle(WATSON, SEASON, WEEK)[1]
    result = run_sql(usage.sql)
    team = {"Team usage": (result["headers"], result["data"])}
    assert fq.rule_verdict("start_sit", WATSON, team, [])[0] == "Start Christian Watson"  # 19.8 PPR per game
    assert fq.rule_verdict("waiver", WATSON, team, [])[0].startswith(("Pick up", "Hold off on"))
    assert fq.rule_verdict("why", WATSON, {}, [("Matchups", "not supported", "x")]) == (
        "Hold Christian Watson", "No factor is strongly supported by the data. Not supported: Matchups.",
    )


def test_planned_sql_never_orders_by_an_aggregate():
    """Spark (live Zetaris) rejects ORDER BY SUM(targets) when SUM(targets) AS targets is selected;
    DuckDB (sample mode) accepts it, so only live runs failed (run 7bfa81c3abf1, 2026-10-25)."""
    queries = [*fq.why_bundle(WATSON, SEASON), *fq.team_bundle(WATSON, SEASON, WEEK),
               fq.games_without_query(WATSON, SEASON)]
    for s in fq.SCORINGS.values():
        queries += fq.team_bundle(WATSON, SEASON, WEEK, s)
    for q in queries:
        for order_by in re.findall(r"ORDER BY ([^)]*?)(?: LIMIT|$|\))", q.sql):
            assert not re.search(r"\b(SUM|AVG|COUNT|MIN|MAX)\(", order_by), (q.factor, order_by)
    usage = fq.team_bundle(WATSON, SEASON, WEEK)[1]
    assert "ORDER BY targets DESC, carries DESC LIMIT 25" in usage.sql


# --- compare: two players head to head ---


def compare_results(scoring=fq.PPR):
    players = lookup("Jameson Williams or George Pickens?")
    results = {}
    for p in fq.compare_bundle(players, SEASON, WEEK, scoring):
        result = run_sql(p.sql)
        results[p.factor] = (result["headers"], result["data"])
    return players, results


def test_compare_bundle_runs_for_both_players(real_sample):
    players, results = compare_results()
    assert [p.name for p in players] == ["Jameson Williams", "George Pickens"]
    assert list(results) == list(fq.COMPARE_FACTORS)
    for factor, (headers, rows) in results.items():
        assert {r[headers.index("player")] for r in rows} == {"Jameson Williams", "George Pickens"}, factor
    for p in fq.compare_bundle(players, SEASON, WEEK, fq.PPR):
        assert not re.search(r"(?i)\bilike\b|\bqualify\b|::|\"|;", p.sql), p.factor


def test_compare_summaries_name_both_and_write_percentages_with_the_sign(real_sample):
    _, results = compare_results()
    for factor, (headers, rows) in results.items():
        text = " ".join(fq.summarize(factor, headers, rows))
        assert "Pickens" in text and "Williams" in text, factor
        assert not re.search(r"\d\s+(?:target|snap|air yards)\s+share", text), text
    usage = " ".join(fq.summarize("Team usage share", *results["Team usage share"]))
    assert "average target share 21.9%" in usage and "13.6 PPR points per game" in usage
    trend = " ".join(fq.summarize("Recent trend", *results["Recent trend"]))
    assert "7.6 PPR points per game in weeks 1-3 vs 17.5 from week 4 on" in trend


def test_compare_ratings_are_head_to_head(real_sample):
    _, results = compare_results()
    assert fq.compare_rating("Weekly opportunity", results)[:2] == ("George Pickens", "strong")
    favours, support, rule = fq.compare_rating("Team usage share", results)
    assert (favours, support) == ("George Pickens", "strong") and "21.9% vs Jameson Williams 15.2%" in rule
    assert fq.compare_rating("Touchdown share", results)[0] == "George Pickens"  # lower is steadier
    assert fq.compare_rating("Recent trend", results)[:2] == ("Jameson Williams", "weak")
    assert fq.compare_rating("Recent trend", {})[:2] == (fq.EVEN, "not supported")


def test_compare_rule_verdict_uses_league_scoring_then_trend(real_sample):
    players, results = compare_results(fq.SCORINGS["half"])
    verdict, why = fq.rule_verdict("compare", players[0], results, [], players=players)
    assert verdict == "Start George Pickens over Jameson Williams"
    assert "half-PPR points per game" in why and "Decided by points per game." in why
    # Level on points per game: the later weeks decide.
    headers, rows = results["Team usage share"]
    col = headers.index("half_ppr_per_game")
    for row in rows:
        row[col] = 10.0
    verdict, why = fq.rule_verdict("compare", players[0], results, [], players=players)
    assert verdict == "Start Jameson Williams over George Pickens" and "Decided by recent trend." in why


# --- last names, the week in the question, the matchup, position labels ---

MCBRIDE = fq.Player("00-0037744", "Trey McBride", "ARI", "TE", "ACT", 7)
UI_QUESTION = "Who should I start Trey Mcbride or Bowers for week 7"


@pytest.mark.parametrize("question, found, words", [
    (UI_QUESTION, [MCBRIDE], ["Bowers"]),
    ("Start McBride or Brock Bowers?", [], ["McBride"]),  # "Brock Bowers" is a full name, not a last name
    ("Should I start Watson or Kittle this week?", [], ["Watson", "Kittle"]),
    ("Should I start the Bucs WR or bowers?", [], ["bowers"]),  # lowercase, next to "or"
    ("Should I start George Pickens or Nobody Atall?", [], []),  # an unknown full name
    ("Who should I start in week 7?", [], []),
])
def test_last_name_words(question, found, words):
    assert fq.last_name_words(question, found) == words


def test_compare_question_counts_last_names_that_resolved():
    assert not fq.is_compare_question(UI_QUESTION)
    assert fq.is_compare_question(UI_QUESTION, ["Bowers"])
    assert not fq.is_compare_question("Should I start Trey McBride this week?", ["Bowers"])  # no choice cue


@pytest.mark.parametrize("question, week", [
    (UI_QUESTION, 7), ("Start McBride in Week 12?", 12), ("Start McBride this week?", None), ("week 40", None),
])
def test_question_week(question, week):
    assert fq.question_week(question) == week


def last_names(words, others=()):
    result = run_sql(fq.last_name_lookup_sql(words, SEASON))
    return fq.resolve_last_names(words, result["headers"], result["data"], list(others))


def test_one_match_resolves_and_says_so(real_sample):
    [bowers] = last_names(["Bowers"], [MCBRIDE])
    assert bowers.player.name == "Brock Bowers" and bowers.note() == "Bowers = Brock Bowers, LV TE."


def test_shared_last_name_prefers_the_other_players_position_then_points(real_sample):
    [johnson] = last_names(["Johnson"], [MCBRIDE])  # a TE: Juwan (65.8 PPR) over Theo (15.5)
    assert johnson.player.name == "Juwan Johnson" and "same position as Trey McBride" in johnson.rule
    [johnson] = last_names(["Johnson"])  # no other player: the most points of all 14
    assert johnson.player.name == "Juwan Johnson" and len(johnson.options) >= 10


def test_unknown_or_tied_last_names_do_not_guess(real_sample):
    [nobody] = last_names(["Zzyzx"])
    assert nobody.player is None and not nobody.options
    headers = ["gsis_id", "full_name", "team", "position", "status", "week", "season_ppr_points"]
    rows = [["a", "Al Smith", "NYJ", "WR", "ACT", 7, 50.0], ["b", "Bo Smith", "DAL", "WR", "ACT", 7, 50.0]]
    [smith] = fq.resolve_last_names(["Smith"], headers, rows, [])
    assert smith.player is None and [p.name for p, _ in smith.options] == ["Al Smith", "Bo Smith"]
    message = fq.clarify_message([nobody, smith])
    assert 'couldn\'t find a skill player called "Zzyzx"' in message
    assert '"Smith" could be 2 players: Al Smith (NYJ, WR); Bo Smith (DAL, WR).' in message
    assert message.endswith("Which player do you mean? Please give their full name.")


def matchup(players, week=None, scoring=fq.PPR):
    q = fq.matchup_query(players, SEASON, WEEK, scoring, week)
    result = run_sql(q.sql)
    return q, (result["headers"], result["data"])


def test_matchup_next_game_and_named_week_match_the_schedule(real_sample):
    _, rows = matchup([MCBRIDE])
    [line] = fq.summarize("Next matchup", *rows)
    assert line.startswith("Trey McBride (ARI) plays DEN in week 7: DEN allow ") and "to TEs (rank " in line
    assert "of 32, 1 = most allowed; from 6 games so far)." in line
    q, rows = matchup([MCBRIDE], week=6)  # LA 16, ARI 18: already played
    assert "week 6 opponent" in q.purpose
    assert fq.summarize("Next matchup", *rows)[0].startswith(
        "Trey McBride (ARI) already played LA in week 6 (that game is in the data): LA allow ")


def test_matchup_on_bye(real_sample):
    [cook] = lookup("James Cook")  # BUF: bye in week 7
    _, rows = matchup([cook], week=7)
    assert fq.summarize("Next matchup", *rows) == ["James Cook (BUF) is on bye in week 7."]
    results = {"Next matchup": rows}
    assert fq.rule_rating("Next matchup", results) == ("not supported", "on bye in week 7")
    usage = fq.team_bundle(cook, SEASON, WEEK)[1]
    result = run_sql(usage.sql)
    results["Team usage"] = (result["headers"], result["data"])
    verdict, why = fq.rule_verdict("start_sit", cook, results, [])
    assert verdict == "Sit James Cook" and "he is on bye in week 7" in why


def test_matchup_in_league_scoring_and_rated_by_rank(real_sample):
    _, rows = matchup([MCBRIDE], scoring=fq.SCORINGS["half"])
    assert "half-PPR points per game to TEs" in fq.summarize("Next matchup", *rows)[0]
    support, rule = fq.rule_rating("Next matchup", {"Next matchup": rows})
    rank = int(rows[1][0][rows[0].index("allowed_rank")])
    expected = "strong" if rank <= 8 else "moderate" if rank <= 16 else "weak" if rank <= 24 else "not supported"
    assert support == expected and f"DEN rank {rank} of 32" in rule and "strong 1-8, moderate 9-16, weak 17-24" in rule


def test_start_sit_and_waiver_plan_the_named_week(real_sample):
    for qt in ("start_sit", "waiver"):
        q = fq.plan(qt, MCBRIDE, SEASON, WEEK, week=8)[-1]
        assert q.factor == "Next matchup" and "week 8 opponent" in q.purpose and "8 AS week" in q.sql
    # No week named: the week after the latest stats week, not each team's next game.
    assert "week 7 opponent" in fq.plan("start_sit", MCBRIDE, SEASON, WEEK)[-1].purpose


def test_no_week_named_means_the_week_after_the_stats_so_a_bye_shows(real_sample):
    # Smoke run: "Should I start Josh Allen this week?" got BAL, BUF's week 8 game; BUF has no week 7 game.
    [allen] = lookup("Josh Allen")
    q = fq.plan("start_sit", allen, SEASON, WEEK)[-1]
    r = run_sql(q.sql)
    assert fq.on_bye({"Next matchup": (r["headers"], r["data"])}) == {"Josh Allen": "7"}


def test_a_qb_gets_no_team_usage_query(real_sample):
    [allen] = lookup("Josh Allen")
    assert "Team usage" not in [q.factor for q in fq.plan("start_sit", allen, SEASON, WEEK)]
    assert "Team usage" in [q.factor for q in fq.plan("start_sit", MCBRIDE, SEASON, WEEK)]


@pytest.mark.parametrize("asked", ["Deebo Samuel", "Deebo Samuel Sr.", "deebo samuel sr"])
def test_names_match_with_or_without_a_suffix(real_sample, asked):
    # Smoke run eef583ef739b: "Should I pick up Deebo Samuel?" found nobody; the roster says "Deebo Samuel Sr.".
    r = run_sql(fq.lookup_sql(fq.name_candidates(f"Should I pick up {asked}?"), SEASON))
    assert [row[1] for row in r["data"]] == ["Deebo Samuel Sr."]


@pytest.mark.parametrize("rank, label", [(1, "favorable"), (10, "favorable"), (11, "neutral"), (15, "neutral"),
                                         (22, "neutral"), (23, "tough"), (31, "tough"), (32, "tough")])
def test_matchup_labels_from_the_allowed_rank(rank, label):
    assert fq.matchup_label(rank, 32) == label


@pytest.mark.parametrize("question, pickup", [
    ("Should I pick up Deebo Samuel?", True),
    ("Should I pick up a 49ers receiver if Evans misses time?", False),  # says Evans is out
    ("Who becomes the Bucs' WR1 if Mike Evans is out?", False),
])
def test_a_pickup_question_is_waiver_unless_a_player_is_out(question, pickup):
    assert fq.is_pickup_question(question) is pickup


def test_compare_rule_starts_the_player_who_is_not_on_bye(real_sample):
    [cook] = lookup("James Cook")
    players = [cook, MCBRIDE]
    results = {}
    for p in fq.compare_bundle(players, SEASON, WEEK, fq.PPR, week=7):
        r = run_sql(p.sql)
        results[p.factor] = (r["headers"], r["data"])
    verdict, why = fq.rule_verdict("compare", cook, results, [], players=players)
    assert verdict == "Start Trey McBride over James Cook" and "James Cook is on bye in week 7" in why


def test_depth_chart_summary_labels_the_position():
    t = (["pos_abb", "pos_rank", "player_name"], [["TE", "1", "Trey McBride"], ["TE", "2", "Elijah Higgins"]])
    assert fq.summarize("Depth chart", *t) == ["TE depth chart: 1. Trey McBride (TE1), 2. Elijah Higgins (TE2)."]


@pytest.mark.parametrize("text, problems", [
    ("Trey McBride is the Cardinals' WR1.", [("WR1", "Trey McBride", "TE")]),
    ("WR1 Trey McBride is a lock.", [("WR1", "Trey McBride", "TE")]),
    ("Trey McBride is the TE1 and Kendrick Bourne the WR1.", []),
    ("With Mike Evans out, the WR1 role goes to the target leader.", []),
    ("He has a 24.1% target share (TE) 24 times.", []),
])
def test_position_label_problems(text, problems):
    positions = {"Trey McBride": "TE", "Kendrick Bourne": "WR", "Mike Evans": "WR"}
    assert [(l, n, p) for _, l, n, p in fq.position_label_problems(text, positions)] == problems


def test_known_positions_from_lookup_usage_and_depth_tables():
    tables = [
        (["gsis_id", "full_name", "team", "position"], [["1", "Trey McBride", "ARI", "TE"]]),
        (["player_display_name", "position"], [["Kendrick Bourne", "WR"]]),
        (["pos_abb", "pos_rank", "player_name"], [["TE", "2", "Elijah Higgins"]]),
    ]
    assert fq.known_positions(tables) == {"Trey McBride": "TE", "Kendrick Bourne": "WR", "Elijah Higgins": "TE"}
