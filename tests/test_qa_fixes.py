"""QA run on the real data (26 Oct 2026): each repro question, in sample mode with no model."""

import pytest

from concurrent.futures import ThreadPoolExecutor

from app import pipeline
from app.adapters import meterless, zetaris
from app.agents import factor_queries, memory
from app.engines.hmem import HMEM
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


# --- batch 2: the stand-in is his position, below him on the depth chart, able to play ---


@pytest.mark.parametrize("question, lead", [
    ("Christian McCaffrey is out. Who replaces him?",
     "Kaelon Black is next at RB on the depth chart (45 carries), so for fantasy: pick up Kaelon Black if available."),
    ("Lamar Jackson is out. Who is the Ravens' QB?",
     "Tyler Huntley is next at QB on the depth chart, so for fantasy: pick up Tyler Huntley if available."),
    ("Who becomes the Bucs' WR1 if Mike Evans is out?",
     "Deebo Samuel is next at WR on the depth chart (11.1% recent target share), "
     "so for fantasy: pick up Deebo Samuel if available."),
    ("Who replaces Chris Godwin?",
     "Ted Hurst III is next at WR on the depth chart (14.6% recent target share), "
     "so for fantasy: pick up Ted Hurst III if available."),
])
def test_replacement_is_the_next_player_at_his_position(no_model, question, lead):
    run, answer = ask(question)
    assert answer.startswith(lead) and run.approved
    assert "Kittle" not in answer.split(". ")[0] and "Egbuka" not in answer.split(". ")[0]


# --- batch 2: status questions come from the injury report ---


@pytest.mark.parametrize("question, opening", [
    ("Is Kyle Monangai playing this week?", "No: Kyle Monangai is listed Out for week 7 (thumb)."),
    ("Is Davante Adams out?", "Yes: Davante Adams is on reserve (RES)."),
])
def test_status_questions_use_the_injury_report(no_model, question, opening):
    run, answer = ask(question)
    assert run.result.question_type == "status" and answer.startswith(opening)
    assert "Source: the week 7 injury report and the rosters table." in answer


# --- batch 2: scoring phrases ---


@pytest.mark.parametrize("text, scoring", [
    (".5 ppr league", "half"), ("I'm in a .5ppr league", "half"), ("1/2 ppr", "half"), ("we're in half", "half"),
    ("half point per catch", "half"), ("we play PPR", "ppr"), ("we switched to PPR", "ppr"),
    ("We switched from half-PPR to full PPR", "ppr"), ("standard, should I start Derrick Henry?", "standard"),
    ("is he a standard WR3?", None),
])
def test_scoring_phrases(text, scoring):
    assert memory.scoring_in(text) == scoring


def test_one_half_ppr_question_quotes_half_ppr(no_model):
    _, answer = ask("1/2 ppr, should I start Bijan Robinson?")
    assert "half-PPR per game; he averages 19.7" in answer


def test_te_premium_says_standard_rules_apply(no_model):
    _, answer = ask("TE premium league: should I start Trey McBride?")
    assert answer.endswith("Note: TE premium is not modelled; this answer uses standard scoring rules for it.")


# --- batch 2: premise checks ---


def test_the_opponent_is_not_a_wrong_team(no_model):
    run, answer = ask("Should I start CeeDee Lamb against PHI?")
    assert run.result.premise_correction is None and answer.startswith("Start CeeDee Lamb.")


def test_a_false_bye_claim_is_corrected_and_the_other_player_answered(no_model):
    run, _ = ask("Jalen Hurts is on bye, should I start Jared Goff?")
    assert run.result.player.name == "Jared Goff"
    assert run.result.premise_correction == "Jalen Hurts is not on bye in week 7: PHI plays DAL."


@pytest.mark.parametrize("question, team", [("Should I start Mike Evans on TB?", "SF"),
                                            ("Should I start Puka Nacua for Los Angeles?", None)])
def test_team_codes_and_los_angeles(no_model, question, team):
    run, _ = ask(question)
    note = run.result.premise_correction
    assert (note is not None and f"Mike Evans is on {team}" in note) if team else note is None


# --- batch 2: start/sit is about the player asked about; the backing is his ---


def test_start_sit_answers_the_player_asked_about(no_model):
    run, answer = ask("I have Dalton Kincaid. Should I start Trey McBride?")
    assert run.result.player.name == "Trey McBride" and answer.startswith("Start Trey McBride.")
    assert "Team usage (strong): Trey McBride's recent target share is 24.1%" in answer


def test_most_supported_lists_only_the_picks_factors(no_model):
    _, answer = ask("Should I start bucky irving or Jonathan Taylor")
    assert answer.startswith("Start Jonathan Taylor over Bucky Irving. Most supported by the data for Jonathan Taylor: "
                             "Recent trend (moderate): Jonathan Taylor: 21.2 PPR points per game")
    supported = answer.split("Not supported:")[0]
    assert "Bucky Irving:" not in supported


def test_team_usage_is_rated_on_his_own_share():
    results = {"Team usage": (["player_display_name", "recent_target_share_pct"], [["A B", "30"], ["C D", "9"]])}
    assert factor_queries.rule_rating("Team usage", results)[0] == "strong"
    assert factor_queries.rule_rating("Team usage", results, "C D")[0] == "weak"


# --- batch 2: concurrency ---


def test_parallel_sample_queries(real_sample):
    sql = "SELECT COUNT(*) AS n FROM NFLVERSE.player_stats"
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: zetaris.run_sql(sql), range(32)))
    assert len({str(r["data"]) for r in results}) == 1


def test_parallel_hmem_saves_use_unique_temp_files(tmp_path):
    mem = HMEM(clock=lambda: 1_750_000_000_000, persist_dir=tmp_path / "store", ledger_path=tmp_path / "ledger.jsonl")
    mem.add("12-team half-PPR league.", "test")
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: mem.store.persist(), range(32)))
    assert (tmp_path / "store" / "state.json").is_file()
    assert not list((tmp_path / "store").glob("*.tmp"))
