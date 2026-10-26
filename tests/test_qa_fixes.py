"""QA run on the real data (26 Oct 2026): each repro question, in sample mode with no model."""

import pytest

from app import pipeline
from app.adapters import meterless
from app.agents import factor_queries
from app.agents.analyst import AnalystError

DISCLAIMER = "\n\nInformational only, based on nflverse data; not betting advice."


@pytest.fixture
def no_model(real_sample, model, monkeypatch, trace_dir):
    """Sample mode with no model configured, as QA ran it."""
    monkeypatch.delenv("METERLESS_BASE_URL", raising=False)

    def respond(messages):
        raise meterless.MeterlessError("down")
    model.respond = respond
    return model


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    return tmp_path / "memory"


def ask(question: str):
    run = pipeline.answer(question, model_review=False)
    return run, run.result.answer.removesuffix(DISCLAIMER)


# --- two or more players without the model: any capitals, any choice cue ---


@pytest.mark.parametrize("question, players, start", [
    ("Should I start bucky irving or Jonathan Taylor", ["Bucky Irving", "Jonathan Taylor"], "Jonathan Taylor"),
    ("Bijan Robinson or CeeDee Lamb half ppr", ["Bijan Robinson", "CeeDee Lamb"], None),
    ("Should I sit Lamb for Nacua?", ["CeeDee Lamb", "Puka Nacua"], "Puka Nacua"),
    ("Gibbs, Achane", ["Jahmyr Gibbs", "De'Von Achane"], None),
    ("Hubbard/Henry half ppr", ["Chuba Hubbard", "Derrick Henry"], None),
    ("Pickens or Olave, I'm in a .5ppr league", ["George Pickens", "Chris Olave"], None),
])
def test_two_players_and_a_choice_cue_is_a_compare(no_model, question, players, start):
    run, answer = ask(question)
    assert run.result.question_type == "compare" and [p.name for p in run.result.players] == players
    assert run.approved
    if start:
        assert answer.startswith(f"Start {start} over ")


def test_bucky_irving_or_jonathan_taylor_quotes_the_points(no_model):
    _, answer = ask("Should I start bucky irving or Jonathan Taylor")
    assert "Bucky Irving 14.3 vs Jonathan Taylor 19.8" in answer


@pytest.mark.parametrize("question, players, start", [
    ("James Cook, Bijan Robinson or CeeDee Lamb?", ["James Cook", "Bijan Robinson", "CeeDee Lamb"], "CeeDee Lamb"),
    ("PPR need one flex: Zay Flowers, Javonte Williams, Kyren Williams",
     ["Zay Flowers", "Javonte Williams", "Kyren Williams"], "Kyren Williams"),
])
def test_three_players_are_all_compared(no_model, question, players, start):
    run, answer = ask(question)
    assert [p.name for p in run.result.players] == players and run.approved
    assert answer.startswith(f"Start {start} over ")
    assert all(p in answer.split(".")[0] for p in players)  # nobody dropped silently


# --- name parsing ---


@pytest.mark.parametrize("question, name", [
    ("Should I start A.J. Brown?", "A.J. Brown"),
    ("Should I start C.J. Stroud?", "C.J. Stroud"),
    ("Should I start Amon-Ra St. Brown?", "Amon-Ra St. Brown"),
])
def test_initials_and_st_are_found(no_model, question, name):
    run, _ = ask(question)
    assert run.result.player.name == name


def test_sentences_do_not_break_after_initials_or_st():
    assert factor_queries.sentences("Start A.J. Brown. Amon-Ra St. Brown is next.") == [
        "Start A.J. Brown.", "Amon-Ra St. Brown is next."]


def test_or_hold_is_not_a_player(no_model):
    run, _ = ask("Should I start Jaylen Waddle or hold?")
    assert run.result.player.name == "Jaylen Waddle" and run.result.question_type == "start_sit"


# --- QBs ---


def test_a_qb_start_sit_has_a_points_per_game_basis(no_model):
    _, answer = ask("Should I start Jared Goff this week?")
    assert answer.startswith("Start Jared Goff.") and "n/a" not in answer
    assert "he averages 23." in answer


def test_touchdown_share_counts_passing_touchdowns(no_model):
    _, answer = ask("Why is Josh Allen scoring so many points?")
    assert "17 touchdowns = 84 of 161.3 PPR points" in answer


# --- availability ---


@pytest.mark.parametrize("question, reason", [
    ("Should I start Kyle Monangai?", "he is listed Out for week 7 (thumb)"),
    ("Should I start Davante Adams?", "he is on reserve (RES)"),
])
def test_out_or_reserve_is_sit(no_model, question, reason):
    _, answer = ask(question)
    assert answer.startswith("Sit ") and f"Rule: {reason}." in answer


def test_both_on_bye_neither_plays(no_model):
    run, answer = ask("Olave or Kamara in week 8?")
    assert answer.startswith("Sit Chris Olave and Alvin Kamara: neither plays.") and run.approved


def test_a_player_named_as_context_is_not_compared(no_model):
    run, answer = ask("Josh Allen on bye, Goff or Bryce Young?")
    assert [p.name for p in run.result.players] == ["Jared Goff", "Bryce Young"]
    assert answer.startswith("Start Jared Goff over Bryce Young.")


# --- unsupported questions are honest ---


@pytest.mark.parametrize("question, opening", [
    ("should I trade Malik Nabers for Davante Adams?",
     "I can't evaluate trades yet. For week 7 only: start Malik Nabers over Davante Adams."),
    ("how much FAAB for Matthew Golden? I have $63 left", "I can't evaluate FAAB bids yet. For week 7 only: start Matthew Golden."),
    ("sell high on Christian Watson or hold?", "I can't evaluate rest-of-season value yet. For week 7 only: "),
])
def test_unsupported_questions_say_so(no_model, question, opening):
    run, answer = ask(question)
    assert run.result.question_type == "unsupported" and answer.startswith(opening)
    assert "Hold " not in answer.split(".")[0]


def test_defense_streaming_is_out_of_scope(no_model):
    with pytest.raises(AnalystError, match="I cover QB, RB, WR and TE only"):
        ask("what defense should i stream this week")


# --- start/sit cues; keep/drop; no bare Hold ---


@pytest.mark.parametrize("question", [
    "is Bucky Irving startable", "CeeDee Lamb @ PHI too tempting?",
    "is Philadelphia a good matchup for CeeDee Lamb?", "is Jonathan Taylor worth a flex",
])
def test_start_sit_cues(no_model, question):
    run, answer = ask(question)
    assert run.result.question_type == "start_sit" and answer.split()[0] in ("Start", "Sit")


@pytest.mark.parametrize("question, verdict", [
    ("Should I drop Dalton Kincaid?", "Keep Dalton Kincaid."),
    ("I have Dalton Kincaid. Should I hold Dalton Kincaid?", "Keep Dalton Kincaid."),
    ("Is Matthew Golden worth adding?", "Pick up Matthew Golden."),
])
def test_keep_drop_and_add(no_model, question, verdict):
    run, answer = ask(question)
    assert run.result.question_type == "waiver" and answer.startswith(verdict) and run.approved


def test_hold_a_rostered_player_is_accepted(real_sample, memory_dir, no_model):
    run = pipeline.answer("I have Dalton Kincaid on my roster. Should I pick up Dalton Kincaid?",
                          user_id="qa-hold", model_review=False)
    assert run.result.answer.startswith("Hold Dalton Kincaid (already on your roster)") and run.approved


def test_an_unrecognised_question_never_gets_hold(no_model):
    verdict, why = factor_queries.rule_verdict(
        "other", factor_queries.Player("x", "Dalton Kincaid", "BUF", "TE", "ACT", 7), {}, [])
    assert verdict == "No call on Dalton Kincaid" and "ask whether to start, sit, pick up or drop" in why


# --- the compare tie-break is the app's own rule, not a reversed claim ---


@pytest.mark.parametrize("question", ["Christian Watson or Jonathan Taylor", "Malik Nabers or Trey McBride?"])
def test_the_tie_break_passes_the_critic(no_model, question):
    run, answer = ask(question)
    assert "they are within 0.5, so the later weeks decide" in answer and run.approved


# --- sample-mode wording ---


def test_no_model_says_so(no_model):
    _, answer = ask("Should I start Jared Goff this week?")
    assert answer.endswith("(Rule-based: no model configured (sample mode).)")
    assert "model call failed" not in answer and "the model recommended" not in answer
