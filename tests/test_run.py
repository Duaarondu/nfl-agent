"""run.py: POST /run, GET /health and the CLI, with the model stubbed."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from helpers import classify

import run as app_run
from app.adapters import meterless
from app.agents import analyst, critic

WATSON = "Why is Christian Watson scoring so many fantasy points this season?"
BUCS = "Who becomes the Bucs' WR1 if Mike Evans is out?"


def scripted(model, verdict="Hold Christian Watson", why="He scored 6 touchdowns."):
    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classify("Christian Watson", "why")
        if system == analyst.FACTOR_PROMPT:
            return json.dumps({"support": "moderate", "summary": "Facts."})
        if system == analyst.VERDICT_PROMPT:
            return json.dumps({"verdict": verdict, "why": why})
        if system == critic.REVIEW_PROMPT:
            return json.dumps({"issues": []})
        raise AssertionError(system[:60])
    model.respond = respond


def all_fail(model):
    def respond(messages):
        raise meterless.MeterlessError("down")
    model.respond = respond


@pytest.fixture
def server(real_sample):
    srv = app_run.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, method=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_health(server):
    status, body = call(server, "/health")
    assert status == 200 and body["status"] == "ok" and body["sample_mode"] is True


def test_run_returns_the_full_answer(server, model):
    scripted(model)
    status, body = call(server, "/run", {"question": WATSON})
    assert status == 200
    assert body["answer"].endswith("\n\nInformational only, based on nflverse data; not betting advice.")
    assert "Verdict: hold Christian Watson." in body["answer"]
    assert body["player"] == {"name": "Christian Watson", "team": "GB", "position": "WR"}
    assert body["premise_correction"] is None and body["question_type"] == "why"
    assert len(body["factors"]) == 6 and body["factors"][0]["evidence"][0]["sql"].startswith("SELECT")
    assert body["claims"] and all(c["evidence"][0]["rows"] for c in body["claims"])
    assert body["critic"]["approved"] and body["critic"]["rounds"][0]["status"] == "approved"
    assert body["memory"] is None
    assert body["steps"] == {
        "planner": "model", "memory_mining": None,
        "factors": {f["factor"]: "model" for f in body["factors"]},
        "first_verdict": "model", "final_verdict": "model", "critic_reviews": ["model"],
    }
    t = body["timings"]
    assert t["total_ms"] >= 0 and {"planner", "analyst", "factor_agent", "critic"} <= set(t["agent_busy_ms"])
    assert {c["agent"] for c in t["model_calls"]} >= {"planner", "analyst", "critic"}
    assert "trace" not in body


def test_run_with_no_model_is_all_rule_based(server, model):
    all_fail(model)
    status, body = call(server, "/run", {"question": WATSON, "include_trace": True})
    assert status == 200 and body["answer"]
    steps = body["steps"]
    assert (steps["planner"], steps["first_verdict"], steps["final_verdict"]) == ("keyword", "rule-based", "rule-based")
    assert set(steps["factors"].values()) == {"rule-based"} and set(steps["critic_reviews"]) == {"rule-based"}
    assert body["trace"] and {l["run_id"] for l in body["trace"]} == {body["run_id"]}


def test_run_with_memory(server, model, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    all_fail(model)
    q = "12-team half-PPR, my TE is George Kittle and my WR is Davante Adams. " + BUCS
    status, body = call(server, "/run", {"question": q, "user_id": "u1"})
    assert status == 200
    m = body["memory"]
    assert (m["scoring"], m["teams"], [p["name"] for p in m["roster"]]) == ("half", 12, ["George Kittle", "Davante Adams"])
    assert len(m["stored_this_run"]) == 4 and body["steps"]["memory_mining"] == "code"
    assert "so for fantasy: pick up Christian McCaffrey" in body["answer"]
    assert body["premise_correction"].startswith("Mike Evans is on SF")


@pytest.mark.parametrize("payload, raw, status, error", [
    (None, b"not json", 400, "bad_json"),
    (["a list"], None, 400, "bad_request"),
    ({"question": ""}, None, 400, "bad_request"),
    ({"question": "x" * 501}, None, 400, "bad_request"),
    ({"question": WATSON, "user_id": "../etc"}, None, 400, "bad_request"),
])
def test_bad_requests_get_json_errors(server, payload, raw, status, error):
    got, body = call(server, "/run", payload, raw=raw)
    assert (got, body["error"]) == (status, error) and body["message"]


def test_unknown_routes(server):
    assert call(server, "/nope")[0] == 404
    assert call(server, "/run")[0] == 405
    assert call(server, "/health", {"x": 1})[0] == 404


def test_unanswerable_question_is_a_422(server, model):
    all_fail(model)
    status, body = call(server, "/run", {"question": "Who is the best kicker in history?"})
    assert status == 422 and body["error"] == "could_not_answer"
    assert "Could not find the NFL player" in body["message"] and body["run_id"]


def test_unexpected_errors_never_leak_a_stack_trace(server, model, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(app_run.pipeline, "answer", boom)
    status, body = call(server, "/run", {"question": WATSON})
    assert status == 500 and body["error"] == "internal_error"
    assert "Traceback" not in json.dumps(body) and "secret internals" not in json.dumps(body)


def test_cli(real_sample, model, capsys):
    all_fail(model)
    assert app_run.main([WATSON]) == 0
    out = capsys.readouterr().out
    reply = json.loads(out.split("--- result ---\n", 1)[1])
    assert reply["answer"] and reply["steps"]["planner"] == "keyword"


def test_cli_error_exit_code(real_sample, capsys):
    assert app_run.main(["   "]) == 1
    reply = json.loads(capsys.readouterr().out.split("--- result ---\n", 1)[1])
    assert reply["error"] == "bad_request"
