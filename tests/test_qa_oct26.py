"""Answer-correctness fixes from the QA sweep of 26 October 2026.

Each test runs the real pipeline on the committed sample data with no model (the rule-based
path a judge without credentials sees) and asserts the fixed behaviour.
"""

import pytest

from app import pipeline
from app.adapters import meterless


@pytest.fixture
def no_model(real_sample, model, monkeypatch, trace_dir):
    monkeypatch.delenv("METERLESS_BASE_URL", raising=False)

    def respond(messages):
        raise meterless.MeterlessError("down")
    model.respond = respond
    return model


def ask(question: str, **kwargs):
    return pipeline.answer(question, model_review=False, **kwargs)


# --- injuries: most teams' week 7 report has practice rows only, no game status yet ---


@pytest.mark.parametrize("question, player", [
    ("Is Deebo Samuel playing this week?", "Deebo Samuel Sr."),   # Out week 6 (hamstring), DNP week 7
    ("Is Rashee Rice playing this week?", "Rashee Rice"),
])
def test_out_last_week_and_not_practising_is_likely_out(no_model, question, player):
    run = ask(question)
    assert run.result.answer.startswith(f"No: {player} is likely out: listed Out for week 6 and did not practice "
                                        "for week 7 (hamstring).")
    assert run.approved and ".." not in run.result.answer


def test_not_practising_without_a_game_status_is_uncertain(no_model):
    # Before: "Yes: Tyler Warren has no game status ... (Did Not Participate In Practice)".
    answer = ask("Is Tyler Warren healthy?").result.answer
    assert answer.startswith("Uncertain: Tyler Warren has no game status yet for week 7, and did not practice.")


def test_a_likely_out_player_is_sat(no_model):
    answer = ask("Should I start Breece Hall this week?").result.answer  # Out weeks 5-6, DNP week 7
    assert answer.startswith("Sit Breece Hall.") and "is likely out" in answer


def test_a_player_listed_out_is_not_a_pickup(no_model):
    # Before: "Pick up Kyle Monangai ... his are n/a% and 15", ending with a Critic note.
    run = ask("Should I pick up Kyle Monangai?")
    assert run.result.answer.startswith("Hold off on Kyle Monangai.")
    assert "is listed Out for week 7 (thumb), so he can't help you this week" in run.result.answer
    assert run.approved and "n/a" not in run.result.answer


def test_the_stand_in_skips_a_player_who_is_likely_out(no_model):
    run = ask("Who becomes the Bucs' WR1 if Mike Evans is out?")
    assert run.result.answer.startswith(
        "Deebo Samuel is next at WR on the depth chart but is likely out: listed Out last week and did not "
        "practice this week; Brandin Cooks has the most recent target share of those who can play (7.2%), "
        "so for fantasy: pick up Brandin Cooks if available.")
    assert run.approved


# --- missing values: never "n/a" in a rule line ---


@pytest.mark.parametrize("question, snap", [
    ("Why is Luther Burden III scoring so many points?", "average snap share 60.5%"),  # "Luther Burden" in snap counts
    ("Why is DK Metcalf scoring so many points?", "average snap share 95.3%"),         # "D.K. Metcalf"
])
def test_snap_share_is_found_whatever_the_name_spelling(no_model, question, snap):
    answer = ask(question).result.answer
    assert snap in answer and "n/a" not in answer


@pytest.mark.parametrize("question, line", [
    # Low-target players fell off the Team usage list (LIMIT 12): "his are n/a% and n/a".
    ("Should I drop Kaleb Johnson?", "he has 0% recent target share, 4.7 carries per game and 1.7 PPR points per game."),
    ("Should I pick up Jordan James?", "he has"),
    # A QB is judged on his points, not target share ("his is n/a%").
    ("Should I pick up Josh Allen?", "Rule: pick up a QB at 12+ PPR points per game; he has 26.9 PPR points per game."),
    ("Should I start Odell Beckham Jr.?", "he has no games for MIN this season."),
    ("Should I pick up Hunter Luepke?", "he has 2.8% recent target share and 0.6 carries per game."),
])
def test_rule_lines_quote_only_values_the_data_has(no_model, question, line):
    run = ask(question)
    assert line in run.result.answer
    assert "n/a" not in run.result.answer and run.approved


# --- stand-ins ---


def test_a_player_already_on_reserve_still_gets_a_stand_in(no_model):
    # Hurts is fourth on PHI's chart, on reserve: nobody was "below" him, so "Hold until ...".
    run = ask("Jalen Hurts is out. Who replaces him?")
    assert run.result.answer.startswith("Tanner McKee is the top QB on the PHI depth chart without Jalen Hurts, "
                                        "so for fantasy: pick up Tanner McKee if available.")
    assert run.approved


def test_a_player_not_on_the_chart_is_not_said_to_have_players_below_him(no_model):
    answer = ask("Who replaces Odell Beckham Jr. if he's out?").result.answer
    assert answer.startswith("Justin Jefferson is the top WR on the MIN depth chart without Odell Beckham Jr.")
    assert "below Odell Beckham Jr." not in answer


@pytest.mark.parametrize("question", [
    "I dropped Deebo Samuel. Who becomes the 49ers' WR1 if Mike Evans is out?",
    "With Deebo Samuel on my bench, who replaces Mike Evans if he is out?",
    "Brandin Cooks is fine but who becomes the 49ers WR1 if Mike Evans is out?",
])
def test_the_replacement_is_for_the_player_who_is_out(no_model, question):
    # Before: the first-named player (Samuel or Cooks) was treated as the one out.
    run = ask(question)
    assert run.result.player.name == "Mike Evans"
    assert "so for fantasy: pick up Brandin Cooks if available" in run.result.answer


@pytest.mark.parametrize("question", [
    "Who becomes the 49ers' WR1 if Mike Evans and Brandin Cooks are out?",
    "Mike Evans is out and Brandin Cooks is out. Who becomes the 49ers WR1?",
])
def test_two_players_out_neither_is_the_pickup(no_model, question):
    answer = ask(question).result.answer
    assert "so for fantasy: pick up Jacob Cowing if available" in answer
