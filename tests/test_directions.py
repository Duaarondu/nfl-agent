"""Factor direction computed in code (app/agents/directions.py), and the text checks that
catch a summary contradicting it: the reversed factors from the 25 October 2026 reruns."""

import pytest

from app.agents import directions
from app.agents.factor_queries import EVEN

PICKENS, WILLIAMS = "George Pickens", "Jameson Williams"

MATCHUP = (["player", "team", "position", "game_week", "opponent", "played", "opp_avg_half_ppr_allowed",
            "allowed_rank", "teams_ranked", "opp_games"],
           [[PICKENS, "DAL", "WR", "7", "PHI", "0", "31.8", "3", "32", "6"],
            [WILLIAMS, "DET", "WR", "7", "GB", "0", "26.0", "17", "32", "6"]])
USAGE_SHARE = (["player", "team", "games", "targets", "avg_target_share_pct", "avg_air_yards_share_pct", "carries",
                "half_ppr_per_game"],
               [[PICKENS, "DAL", "6", "52", "21.9", "31.9", "0", "10.9"],
                [WILLIAMS, "DET", "5", "29", "15.2", "34.1", "0", "9.7"]])
TEAM_USAGE = (["player_display_name", "position", "recent_target_share_pct"],
              [["Mike Evans", "WR", "27.1"], ["George Kittle", "TE", "24.9"], ["Christian McCaffrey", "RB", "22.8"],
               ["Deebo Samuel Sr.", "WR", "11.1"]])
# Christian Watson's weeks 1-6, and the weeks a teammate was out (3, 5, 6)
OPPORTUNITY = (["week", "snap_pct", "targets", "target_share_pct", "ppr_points"],
               [["1", "76.0", "8", "20.0", "32.7"], ["2", "90.0", "11", "37.9", "14.1"], ["3", "80.0", "10", "19.6", "22.6"],
                ["4", "68.0", "3", "10.0", "7.7"], ["5", "80.0", "8", "25.8", "32.3"], ["6", "88.0", "8", "20.0", "9.4"]])
BIG_PLAYS = (["week", "targets", "receiving_yards", "air_yards_share_pct", "yards_per_target", "plays_20_plus"],
             [["1", "8", "147", "27.1", "18.4", "2"], ["2", "11", "41", "39.8", "3.7", "1"],
              ["3", "10", "96", "23.2", "9.6", "2"], ["4", "3", "47", "10.7", "15.7", "0"],
              ["5", "8", "143", "56.1", "17.9", "3"], ["6", "8", "64", "37.5", "8.0", "2"]])
ABSENCES = (["week", "full_name", "position", "report_status"],
            [["3", "Jayden Reed", "WR", "Out"], ["5", "Chris Brooks", "RB", "Out"], ["6", "Skyy Moore", "WR", "Out"]])


def matchup():
    return directions.directions("Next matchup", {"Next matchup": MATCHUP})


# --- the directions given to the factor agents ---


def test_more_points_allowed_is_the_easier_matchup():
    d = matchup()
    assert d.favours == PICKENS
    assert ("Easier matchup: George Pickens (PHI allow 31.8, rank 3) over Jameson Williams "
            "(GB allow 26, rank 17); more points allowed and a lower rank number mean an easier matchup.") in d.lines
    assert d.lines[0].startswith("George Pickens's week 7 opponent PHI: rank 3 of 32, favorable matchup")
    assert d.lines[1].startswith("Jameson Williams's week 7 opponent GB: rank 17 of 32, neutral matchup")


# --- matchup labels from code (smoke run, 25 October 2026) ---

BOWERS_PICKENS = (["player", "team", "position", "game_week", "opponent", "played", "opp_avg_ppr_allowed",
                   "allowed_rank", "teams_ranked", "opp_games"],
                  [["Brock Bowers", "LV", "TE", "7", "LA", "0", "8.3", "31", "32", "6"],
                   ["George Pickens", "DAL", "WR", "7", "PHI", "0", "38.3", "3", "32", "6"]])
ONE = lambda row: (BOWERS_PICKENS[0], [row])
MCBRIDE_DEN = ["Trey McBride", "ARI", "TE", "7", "DEN", "0", "13.2", "15", "32", "6"]


def test_he_is_the_sentences_first_named_player():
    d = directions.directions("Next matchup", {"Next matchup": BOWERS_PICKENS})
    # Smoke question 7: approved with the matchup reversed ("he" is Bowers; LA is rank 31, tough).
    text = ("Bowers also outperforms in recent trend, averaging 18.2 PPR points per game from week 4 onward versus "
            "Pickens's 16.9, and he faces a significantly easier matchup with Los Angeles allowing 8.3 PPR points "
            "to tight ends (rank 31) versus Philadelphia allowing 38.3 to wide receivers (rank 3).")
    problems = directions.contradictions(text, d)
    # A TE and a WR: the ranks are compared, not the points allowed (QA run).
    assert ("it gives Brock Bowers the easier matchup, but Brock Bowers's opponent ranks 31 against his position to "
            "George Pickens's 3; a lower rank is easier") in problems
    assert ("'easier' does not fit Brock Bowers's matchup: LA is rank 31 of 32 in points allowed, a tough matchup "
            "(rank 1 allows the most)") in problems


@pytest.mark.parametrize("row, text, word", [
    # Smoke question 9: "LA ... 31st of 32 ... making it the easiest matchup", approved in round 1.
    (BOWERS_PICKENS[1][0], "He faces LA, which ranks 31st of 32 in points allowed to TEs, surrendering only 8.3 PPR "
                           "points per game, making it the easiest matchup for the position.", "easiest"),
    # Smoke question 2: rank 15 is neutral, not bottom-third.
    (MCBRIDE_DEN, "His opponent DEN ranks 15th of 32 in points allowed to TEs, which is a bottom-third matchup.",
     "bottom-third"),
    (BOWERS_PICKENS[1][1], "Pickens faces a tough PHI defense (rank 3).", "tough"),
])
def test_matchup_words_must_fit_the_code_label(row, text, word):
    d = directions.directions("Next matchup", {"Next matchup": ONE(row)})
    [problem] = directions.contradictions(text, d)
    assert problem.startswith(f"'{word}' does not fit")


@pytest.mark.parametrize("row, text", [
    (MCBRIDE_DEN, "He faces a moderately favorable matchup, with DEN ranking 15th of 32."),  # neutral: not tough
    (BOWERS_PICKENS[1][0], "LA is a tough matchup: rank 31 of 32."),
    (BOWERS_PICKENS[1][0], "It is not an easy matchup against LA."),  # negated
    (BOWERS_PICKENS[1][1], "Pickens has a top-third matchup against PHI."),
])
def test_matchup_words_that_fit_the_label_pass(row, text):
    d = directions.directions("Next matchup", {"Next matchup": ONE(row)})
    assert not directions.contradictions(text, d)


def test_the_label_is_in_the_facts_and_a_bye_is_said():
    d = directions.directions("Next matchup", {"Next matchup": ONE(BOWERS_PICKENS[1][0])})
    assert d.lines == ["Brock Bowers's week 7 opponent LA: rank 31 of 32, tough matchup (rank 1 allows the most "
                       "points; 1-10 favorable, 11-22 neutral, 23-32 tough)."]
    bye = directions.directions("Next matchup", {"Next matchup": ONE(
        ["Josh Allen", "BUF", "QB", "7", None, "0", None, None, None, None])})
    assert bye.lines == ["Josh Allen is on bye in week 7: no game."]


def test_a_number_not_in_the_rows_is_found_but_a_difference_is_not():
    # Smoke question 10: "4.4 more half-PPR points per game (17.1 vs 13.1)"; the gap is 4.0.
    allowed = directions.numbers_in(["17.1", "13.1", "29.7", "29.3"])
    assert directions.unknown_numbers("Bowers has 4.4 more points per game (17.1 vs 13.1).", allowed) == \
        [("Bowers has 4.4 more points per game (17.1 vs 13.1).", "4.4")]
    assert not directions.unknown_numbers("Bowers has 4 more points per game (17.1 vs 13.1).", allowed)


def test_head_to_head_lines_say_who_leads_each_metric():
    d = directions.directions("Team usage share", {"Team usage share": USAGE_SHARE})
    assert "Average air yards share: George Pickens 31.9% vs Jameson Williams 34.1% (Jameson Williams higher)." in d.lines
    assert "Half-PPR points per game: George Pickens 10.9 vs Jameson Williams 9.7 (George Pickens higher)." in d.lines
    assert d.lines[-1].endswith("this factor favours George Pickens.")


def test_target_share_in_the_weeks_a_teammate_was_out():
    d = directions.directions("Teammate absences", {"Teammate absences": ABSENCES, "Opportunity": OPPORTUNITY,
                                                    "Big plays": BIG_PLAYS})
    assert d.lines == ["In the weeks a teammate was out (3, 5, 6) vs the other weeks: target share 21.8% vs 22.6% "
                       "(lower); PPR points per game 21.4 vs 18.2 (higher); yards per target 11.8 vs 12.6 (lower)."]
    assert d.trends == {"target share": -0.8, "points per game": 3.2, "yards per target": -0.8}


def test_target_share_rose_or_fell_between_the_halves():
    d = directions.directions("Opportunity", {"Opportunity": OPPORTUNITY})
    assert "Target share fell: 25.8% in weeks 1-3 vs 18.6% in weeks 4-6." in d.lines


# --- the reversed summaries from the reruns are caught ---


def test_williams_easier_matchup_is_reversed():
    summary = ("Jameson Williams faces a significantly easier matchup in week 7, with GB allowing 26 half-PPR points "
               "per game to WRs (rank 17) compared to PHI allowing 31.8 to George Pickens (rank 3).")
    problems = directions.contradictions(summary, matchup(), favours=WILLIAMS)
    assert problems == [
        "it says this factor favours Jameson Williams, but the numbers favour George Pickens",
        "it gives Jameson Williams the easier matchup, but Jameson Williams's opponent allows 26 to George Pickens's "
        "31.8; more points allowed is easier",
    ]
    assert not directions.contradictions("George Pickens has the easier matchup: PHI allow 31.8 to GB's 26.",
                                         matchup(), favours=PICKENS)


def test_higher_for_the_lower_number_of_a_pair():
    d = directions.Directions()
    bad = "Pickens has a higher average target share (21.9% vs 15.2%) and air yards share (31.9% vs 34.1%)."
    assert directions.contradictions(bad, d) == ["'higher' does not fit 31.9 vs 34.1"]
    assert directions.contradictions("Bowers has more targets per game (10.8 vs 10.8).", d) == \
        ["'more targets' does not fit 10.8 vs 10.8"]
    # "edge" is vague: it does not say which number is which, so it is not checked
    assert not directions.contradictions("Bowers holds a slight edge in snap share at 82.2% versus McBride's 90.5%.", d)


def test_a_vague_word_is_not_checked_and_ends_an_earlier_words_reach():
    # Run c6522e90539f was blocked in rounds 1 and 3 on "'edge' does not fit 17.5 vs 21.9", but a
    # lower touchdown share is McBride's edge, and rank 15 is the easier matchup.
    answer = ("Brock Bowers leads PPR points per game (20.6 vs 17.2) and points in later weeks (18.2 vs 14.7), "
              "with a higher recent average that outweighs Trey McBride's touchdown share edge (17.5% vs 21.9%) "
              "and easier defensive matchup (DEN rank 15 vs LA rank 31).")
    assert not directions.contradictions(answer, directions.Directions())


@pytest.mark.parametrize("text, problem", [
    ("Bowers has the easier matchup (LA rank 31 vs DEN rank 15).",
     "'easier' does not fit 31 vs 15: for defense rank, the lower number is the easier matchup"),
    ("Williams has a more favorable matchup, with GB allowing 26 versus PHI's 31.8.",
     "'more favorable' does not fit 26 vs 31.8: for points allowed, the higher number is the easier matchup"),
    ("Bowers is steadier, with a touchdown share of 21.9% vs 17.5%.",
     "'steadier' does not fit 21.9 vs 17.5: for touchdown share, the lower number is the steadier, "
     "less touchdown-dependent side"),
])
def test_good_words_follow_the_metrics_polarity(text, problem):
    assert directions.contradictions(text, directions.Directions()) == [problem]


@pytest.mark.parametrize("text", [
    "McBride has the easier matchup (DEN rank 15 vs LA rank 31).",
    "Pickens has a more favorable matchup, with PHI allowing 31.8 versus GB's 26.",
    "McBride is steadier, with a touchdown share of 17.5% vs 21.9%.",
    "McBride has the higher-ranked matchup (rank 15 vs rank 31).",  # a size word on ranks: ambiguous
])
def test_good_words_that_fit_the_polarity_pass(text):
    assert not directions.contradictions(text, directions.Directions())


@pytest.mark.parametrize("text", [
    "McBride has a 0.4% higher average target share (29.7% vs 29.3%) and a 10.1% lower air yards share (23.8% vs 33.9%).",
    "McBride is less touchdown-dependent (17.5% vs 21.9%).",
    "Pickens has a higher target share, with 52 targets and 0 carries in 6 games compared to Williams's 29 targets.",
    "Rank 3 vs rank 17 in points allowed.",
])
def test_comparison_words_that_fit_pass(text):
    assert not directions.contradictions(text, directions.Directions())


def test_from_a_to_b_must_match_the_verb():
    d = directions.Directions()
    assert not directions.contradictions("His target share fell from 25.8% to 18.6%.", d)
    assert directions.contradictions("His target share rose from 25.8% to 18.6%.", d) == \
        ["'rose' does not fit from 25.8 to 18.6"]
    assert not directions.contradictions("Yards per target rose from 10.6 in weeks 1-3 to 13.9 in weeks 4-6.", d)


def test_absences_increased_his_share_is_reversed():
    d = directions.directions("Teammate absences", {"Teammate absences": ABSENCES, "Opportunity": OPPORTUNITY,
                                                    "Big plays": BIG_PLAYS})
    summary = ("Teammate absences in Weeks 3-6 increased Watson's target share and yards per target, "
               "contributing to his elevated scoring.")
    assert directions.contradictions(summary, d) == [
        "it says target share rose, but it fell in the weeks a teammate was out vs the other weeks (-0.8)",
        "it says yards per target rose, but it fell in the weeks a teammate was out vs the other weeks (-0.8)",
    ]
    assert not directions.contradictions("With a teammate out he scored more PPR points per game (21.4 vs 18.2).", d)


def test_kittle_and_mccaffrey_do_not_rank_higher_than_evans():
    d = directions.directions("Team usage", {"Team usage": TEAM_USAGE})
    bad = ("Mike Evans has the highest target share at 27.1%, but George Kittle (24.9%) and Christian McCaffrey "
           "(22.8%) rank higher on the 49ers' offense, making Evans' absence impactful but not decisive.")
    assert directions.contradictions(bad, d) == [
        "it puts George Kittle above Mike Evans, but by recent target share George Kittle has 24.9% to Mike Evans's 27.1%",
        "it puts Christian McCaffrey above Mike Evans, but by recent target share Christian McCaffrey has 22.8% to "
        "Mike Evans's 27.1%",
    ]
    fine = ("Mike Evans has the highest target share at 27.1%, but George Kittle's 24.9% ranks second, ahead of "
            "McCaffrey and Samuel, indicating Kittle would become the primary target if Evans is out.")
    assert not directions.contradictions(fine, d)


def test_a_ranking_word_compares_the_names_after_the_last_comma():
    # Run 6b5c3a81c4f9 was blocked on "it puts Mike Evans below George Kittle": the subject of
    # "behind" is Deebo Samuel, after the comma.
    d = directions.directions("Team usage", {"Team usage": TEAM_USAGE})
    text = ("If Mike Evans is out, Deebo Samuel is next on the depth chart and has a lower target share (11.1%) "
            "behind George Kittle (24.9%).")
    assert not directions.contradictions(text, d)


def test_an_even_factor_or_an_ellipsis():
    d = directions.Directions(favours=EVEN)
    assert not directions.contradictions("Even.", d, favours=PICKENS)  # a level factor reverses nothing
    assert directions.contradictions("Start Trey McBride over Brock Bowers. ...", d) == ["it is unfinished (an ellipsis)"]
