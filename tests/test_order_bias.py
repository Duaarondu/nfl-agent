"""Player order must not change a head-to-head answer (QA, 26 October 2026).

The reported bug: whichever player was typed first got favoured, or was the only one named.
These run the real pipeline on the committed sample data, with no model and with a scripted
model that always favours one side, and ask each question both ways round.
"""

import json
import re

import pytest

from app import pipeline
from app.adapters import meterless
from app.agents import analyst, critic, factor_queries, planner

START = re.compile(r"\bStart ([A-Z][\w.'-]*(?: [A-Z][\w.'-]*)*?) over\b")
PAIRS = [("Chris Olave", "Zay Flowers"), ("Jonathan Taylor", "Kyren Williams"), ("Davante Adams", "Jalen Coker"),
         ("Sam LaPorta", "George Kittle"), ("Patrick Mahomes", "Tyler Shough"), ("Puka Nacua", "Bijan Robinson")]


@pytest.fixture
def no_model(real_sample, model, monkeypatch, trace_dir):
    """Sample mode with no model configured."""
    monkeypatch.delenv("METERLESS_BASE_URL", raising=False)

    def respond(messages):
        raise meterless.MeterlessError("down")
    model.respond = respond
    return model


def start(question: str) -> str | None:
    match = START.search(pipeline.answer(question, model_review=False).result.answer)
    return match.group(1) if match else None


@pytest.mark.parametrize("a, b", PAIRS)
def test_the_pick_does_not_depend_on_the_order(no_model, a, b):
    for phrasing in ("Should I start {} or {}?", "{} vs {}"):
        assert start(phrasing.format(a, b)) == start(phrasing.format(b, a)) is not None


@pytest.mark.parametrize("question", [
    "Mike Evans or George Kittle if Evans is out?",
    "George Kittle or Mike Evans if Evans is out?",
])
def test_the_player_the_question_says_is_out_is_never_started(no_model, question):
    # Before the fix: "Start Mike Evans" both ways; named first, the Critic objected for 3
    # rounds but the code rules repeated it; named second, the Critic approved it.
    run = pipeline.answer(question, model_review=False)
    assert START.search(run.result.answer).group(1) == "George Kittle"
    assert run.approved and "Critic note" not in run.result.answer


def test_a_question_out_player_counts_whichever_he_is_named_as(real_sample):
    results = {"Next matchup": (["player", "game_week", "opponent", "report_status", "report_primary_injury",
                                 "roster_status"],
                                [["George Kittle", "7", "ATL", "", "", "ACT"], ["Mike Evans", "7", "ATL", "", "", "ACT"]])}
    for question in ("Kittle or Evans if Evans is out?", "Evans or Kittle if Evans is out?"):
        assert factor_queries.unavailable(results, question) == {"Mike Evans": factor_queries.QUESTION_OUT}
    assert factor_queries.unavailable(results) == {}  # without the question, as before


@pytest.mark.parametrize("favoured", ["first", "last"])
def test_a_biased_model_cannot_move_the_pick_or_win_an_even_factor(real_sample, model, trace_dir, favoured):
    """A model that always favours one named side (the bug report) ends on the numbers' pick,
    and every factor card agrees with the code rule, in both orders."""
    names = {}

    def respond(messages):
        system = messages[0]["content"]
        side = names["order"][0] if favoured == "first" else names["order"][-1]
        other = [n for n in names["order"] if n != side][0]
        if system == planner.PROMPT:
            return json.dumps({"player_name": names["order"][0], "player_names": names["order"],
                               "question_type": "compare"})
        if system == analyst.COMPARE_FACTOR_PROMPT:
            return json.dumps({"favours": side, "support": "strong", "summary": f"{side} has the clear edge here."})
        if system == analyst.VERDICT_PROMPT:
            return json.dumps({"verdict": f"Start {side} over {other}", "why": f"{side} is the safer start."})
        if system == critic.REVIEW_PROMPT:
            return json.dumps({"issues": []})
        return "[]"

    model.respond = respond
    picks = []
    for order in (["Chris Olave", "Zay Flowers"], ["Zay Flowers", "Chris Olave"]):
        names["order"] = order
        run = pipeline.answer(f"Should I start {order[0]} or {order[1]}?")
        results = {q.factor: (q.headers, q.rows) for q in run.result.queries if not q.error}
        for f in run.result.factors:
            if f.favours:
                code_side = factor_queries.compare_rating(f.factor, results)[0]
                assert f.favours == code_side or factor_queries.same_player(f.favours, code_side), f.factor
        picks.append(START.search(run.result.answer).group(1))
    assert picks == ["Zay Flowers", "Zay Flowers"]  # 18.9 vs 18.8 PPR, and 17.7 vs 14.2 in the later weeks
