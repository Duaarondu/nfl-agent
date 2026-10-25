"""The web UI server (port 8080), GET /trace/<run_id>, CORS and client-made run IDs."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from test_run import WATSON, all_fail, call, scripted

import run as app_run
from app.agents import analyst

UI_ORIGIN = "http://localhost:8080"


@pytest.fixture
def servers(real_sample, monkeypatch):
    """The API and the UI on two free ports, as run.serve() starts them."""
    monkeypatch.setattr(app_run, "RUNS", app_run.RunStore())
    monkeypatch.delenv("UI_ORIGINS", raising=False)
    monkeypatch.delenv("UI_PORT", raising=False)
    api = app_run.make_server("127.0.0.1", 0)
    ui = app_run.make_ui_server("127.0.0.1", 0, api_port=api.server_address[1])
    for srv in (api, ui):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{api.server_address[1]}", f"http://127.0.0.1:{ui.server_address[1]}"
    for srv in (api, ui):
        srv.shutdown()
        srv.server_close()


def get(url, headers=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode("utf-8")


# --- the UI server ---


@pytest.mark.parametrize("path, content_type, marker", [
    ("/", "text/html", "<title>NFL Fantasy Agent</title>"),
    ("/index.html", "text/html", 'id="timeline"'),
    ("/app.js", "text/javascript", "/trace/"),
    ("/style.css", "text/css", ".timeline"),
])
def test_ui_serves_its_files(servers, path, content_type, marker):
    _, ui = servers
    status, headers, text = get(ui + path)
    assert status == 200 and headers["Content-Type"].startswith(content_type) and marker in text


def test_ui_page_has_the_inputs_chips_and_sponsors(servers):
    _, ui = servers
    _, _, page = get(ui + "/")
    assert 'id="question"' in page and 'id="user-id"' in page
    assert "Why is Christian Watson scoring so many fantasy points this season?" in page
    assert "Who becomes the Bucs' WR1 if Mike Evans is out?" in page
    assert 'data-user="demo"' in page and "12-team half-PPR" in page
    for sponsor in ("Zetaris", "Meterless Nightshift", "NVIDIA Nemotron", "Meterless H-MEM"):
        assert sponsor in page
    assert "Download trace (JSONL)" in page


def test_ui_config_points_at_the_api_port(servers):
    api, ui = servers
    status, _, text = get(ui + "/config.js")
    assert status == 200 and f'"apiPort": {api.rsplit(":", 1)[1]}' in text


@pytest.mark.parametrize("path", ["/missing.js", "/../run.py", "/%2e%2e/run.py", "/app/ui/index.html", "/.env"])
def test_ui_serves_nothing_else(servers, path):
    _, ui = servers
    status, _, text = get(ui + path)
    assert status == 404 and "SAMPLE_MODE" not in text


# --- GET /trace/<run_id> ---


def test_trace_of_a_finished_run(servers, model):
    api, _ = servers
    scripted(model)
    status, reply = call(api, "/run", {"question": WATSON, "run_id": "0123456789ab"})
    assert status == 200 and reply["run_id"] == "0123456789ab"

    status, t = call(api, "/trace/0123456789ab")
    assert status == 200 and t["done"] is True and t["status"] == 200
    assert t["result"]["answer"] == reply["answer"]
    actions = [(l["agent_name"], l["action"]) for l in t["lines"]]
    assert ("planner", "handoff") in actions and ("critic", "final") in actions
    assert all(l["run_id"] == "0123456789ab" for l in t["lines"])


def test_trace_download_is_jsonl(servers, model):
    api, _ = servers
    all_fail(model)
    call(api, "/run", {"question": WATSON, "run_id": "00000000beef"})
    status, headers, text = get(api + "/trace/00000000beef.jsonl")
    assert status == 200 and headers["Content-Type"].startswith("application/x-ndjson")
    assert headers["Content-Disposition"] == 'attachment; filename="trace-00000000beef.jsonl"'
    lines = [json.loads(line) for line in text.splitlines()]
    assert lines and lines[-1]["action"] == "final"


@pytest.mark.parametrize("path, status", [
    ("/trace/abcdefabcdef", 404),  # well formed, but never run here
    ("/trace/not-a-run", 400),
    ("/trace/ABCDEFABCDEF", 400),
    ("/trace/", 400),
])
def test_trace_errors(servers, path, status):
    api, _ = servers
    code, reply = call(api, path)
    assert code == status and reply["error"] in ("not_found", "bad_request")


def test_trace_answers_while_the_run_is_still_running(servers, model):
    """The UI polls GET /trace/<run_id> during a POST /run: neither blocks the other."""
    api, ui = servers
    release = threading.Event()
    scripted(model)
    answer_normally = model.respond

    def slow(messages):
        if messages[0]["content"] == analyst.CLASSIFY_PROMPT:
            assert release.wait(30), "never released"
        return answer_normally(messages)

    model.respond = slow
    posted = {}
    post = threading.Thread(target=lambda: posted.update(reply=call(api, "/run", {"question": WATSON, "run_id": "feedfacecafe"})))
    post.start()
    try:
        deadline = time.monotonic() + 10
        while True:  # the run is registered as soon as the POST arrives
            status, t = call(api, "/trace/feedfacecafe")
            if status == 200 or time.monotonic() > deadline:
                break
            time.sleep(0.05)
        assert status == 200 and t["done"] is False and "result" not in t
        assert post.is_alive()  # the POST is still waiting on the Planner's model call
        assert call(api, "/health")[0] == 200
        assert get(ui + "/")[0] == 200
    finally:
        release.set()
        post.join(30)
    assert posted["reply"][0] == 200
    status, t = call(api, "/trace/feedfacecafe")
    assert t["done"] is True and t["result"]["run_id"] == "feedfacecafe"


# --- client-made run IDs ---


@pytest.mark.parametrize("run_id", ["short", "0123456789AB", 12, "0123456789abc"])
def test_bad_run_id_is_a_400(servers, run_id):
    api, _ = servers
    status, reply = call(api, "/run", {"question": WATSON, "run_id": run_id})
    assert status == 400 and "run_id" in reply["message"]


def test_reused_run_id_is_a_409(servers, model):
    api, _ = servers
    all_fail(model)
    assert call(api, "/run", {"question": WATSON, "run_id": "aaaaaaaaaaaa"})[0] == 200
    status, reply = call(api, "/run", {"question": WATSON, "run_id": "aaaaaaaaaaaa"})
    assert status == 409 and reply["error"] == "duplicate_run_id"


def test_run_store_keeps_the_last_runs():
    store = app_run.RunStore(keep=2)
    for run_id in ("a" * 12, "b" * 12, "c" * 12):
        store.start(run_id)
    assert store.get("a" * 12) is None and store.get("c" * 12)["done"] is False


# --- CORS: the UI's origin only ---


def test_cors_allows_the_ui_origin_only(servers):
    api, _ = servers
    _, headers, _ = get(api + "/health", {"Origin": UI_ORIGIN})
    assert headers["Access-Control-Allow-Origin"] == UI_ORIGIN
    _, headers, _ = get(api + "/health", {"Origin": "http://127.0.0.1:8080"})
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:8080"
    _, headers, _ = get(api + "/health", {"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in headers


def test_cors_preflight_for_post_run(servers):
    api, _ = servers
    status, headers, _ = get(api + "/run", {"Origin": UI_ORIGIN, "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "content-type"}, method="OPTIONS")
    assert status == 204 and headers["Access-Control-Allow-Origin"] == UI_ORIGIN
    assert "POST" in headers["Access-Control-Allow-Methods"] and "Content-Type" in headers["Access-Control-Allow-Headers"]
    _, headers, _ = get(api + "/run", {"Origin": "http://evil.example"}, method="OPTIONS")
    assert "Access-Control-Allow-Origin" not in headers


def test_ui_origins_can_be_configured(monkeypatch):
    monkeypatch.setenv("UI_ORIGINS", "https://demo.example, http://10.0.0.5:8080/")
    assert app_run.ui_origins() == {"https://demo.example", "http://10.0.0.5:8080"}
    monkeypatch.delenv("UI_ORIGINS")
    monkeypatch.setenv("UI_PORT", "9090")
    assert app_run.ui_origins() == {"http://localhost:9090", "http://127.0.0.1:9090"}
