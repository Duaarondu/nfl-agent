"""Planner agent: classify the question, hand off to the Analyst."""

from helpers import classify, read_trace

from app.adapters import meterless
from app.agents import planner


def test_model_route_and_handoff(model, trace_dir):
    model.replies = [classify("Mike Evans", "replacement")]
    route = planner.plan("r1", "Who becomes the Bucs' WR1 if Mike Evans is out?")
    assert route == planner.Route("Mike Evans", "replacement", "model")
    assert model.calls[0][0]["content"] == planner.PROMPT and model.kwargs[0]["timeout"] == planner.TIMEOUT
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
