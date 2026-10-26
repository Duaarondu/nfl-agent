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
    assert d.lines[0] == ("Easier matchup: George Pickens (PHI allow 31.8, rank 3) over Jameson Williams "
                          "(GB allow 26, rank 17); more points allowed and a lower rank number mean an easier matchup.")


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
    assert directions.contradictions("Bowers holds a slight edge in snap share at 82.2% versus McBride's 90.5%.", d)


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


def test_an_even_factor_or_an_ellipsis():
    d = directions.Directions(favours=EVEN)
    assert not directions.contradictions("Even.", d, favours=PICKENS)  # a level factor reverses nothing
    assert directions.contradictions("Start Trey McBride over Brock Bowers. ...", d) == ["it is unfinished (an ellipsis)"]
