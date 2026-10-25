"""Planner agent: classify the question, hand off to the Analyst."""

from helpers import classify, read_trace

from app.adapters import meterless
from app.agents import planner


def test_model_route_and_handoff(model, trace_dir):
    model.replies = [classify("Mike Evans", "replacement")]
    route = planner.plan("r1", "Who becomes the Bucs' WR1 if Mike Evans is out?")
    assert route == planner.Route("Mike Evans", "replacement", "model")
    assert model.calls[0][0]["content"] == planner.PROMPT and model.kwargs[0]["timeout"] == planner.TIMEOUT
    assert model.kwargs[0]["max_tokens"] == planner.MAX_TOKENS == 4096
    lines = read_trace(trace_dir)
    assert [(l["agent_name"], l["action"], l["status"], l["target_agent"]) for l in lines] == [
        ("planner", "model_call", "ok", None),
        ("planner", "handoff", "ok", "analyst"),
    ]


def test_keyword_fallback_still_hands_off(model, trace_dir):
    model.replies = [meterless.MeterlessError("down")]
    route = planner.plan("r1", "Should I start Christian Watson this week?")
    assert route == planner.Route(None, "start_sit", "keyword")
    handoff = [l for l in read_trace(trace_dir) if l["action"] == "handoff"]
    assert [(h["classified_by"], h["question_type"]) for h in handoff] == [("keyword", "start_sit")]


C2 = "Should I pick up a 49ers receiver if Evans misses time?"


def test_pickup_because_a_player_is_out_is_a_replacement_question(model):
    assert "if Evans misses time?\" is replacement, about Evans" in planner.PROMPT
    model.replies = [meterless.MeterlessError("down")]
    assert planner.plan("r1", C2) == planner.Route(None, "replacement", "keyword")


COMPARE = ("I have Jameson Williams on my bench and George Pickens in my starting lineup, "
           "who should I pick?")


def test_compare_route_carries_both_names(model, trace_dir):
    model.replies = ['{"player_name": "Jameson Williams", "player_names": ["Jameson Williams", "George Pickens"], '
                     '"question_type": "compare"}']
    route = planner.plan("r1", COMPARE)
    assert route == planner.Route("Jameson Williams", "compare", "model", ("Jameson Williams", "George Pickens"))
    assert '"compare"' in planner.PROMPT and "player_names" in planner.PROMPT
    [handoff] = [l for l in read_trace(trace_dir) if l["action"] == "handoff"]
    assert handoff["player_names"] == ["Jameson Williams", "George Pickens"]


def test_names_are_dropped_for_a_single_player_type(model):
    model.replies = ['{"player_name": "Mike Evans", "player_names": ["Mike Evans"], "question_type": "start_sit"}']
    assert planner.plan("r1", "Should I start Mike Evans?").player_names == ()


def test_compare_keyword_fallback(model):
    model.replies = [meterless.MeterlessError("down")]
    assert planner.plan("r1", COMPARE) == planner.Route(None, "compare", "keyword")
