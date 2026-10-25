"""Entry point: the API (POST /run, GET /trace/<run_id>, GET /health), the web UI, and a CLI.

    python run.py                          API on 0.0.0.0:8000 (PORT), web UI on 0.0.0.0:8080 (UI_PORT)
    python run.py --serve [--port N] [--ui-port N] [--no-ui]   the same
    python run.py "question" [--user ID]   answer one question and print the JSON reply

The API and the UI are two ThreadingHTTPServers on separate ports, so neither blocks
the other, and every request gets its own thread: GET /trace/<run_id> answers while a
POST /run is still running. The UI (app/ui/, plain HTML/JS/CSS) calls the API from the
browser; the API allows CORS for the UI's origin only (UI_ORIGINS overrides it).

POST /run takes {"question": "...", "user_id": "..." (optional, turns on league memory),
"run_id": "<12 hex characters>" (optional; the UI makes one so it can poll the trace),
"include_trace": false (optional)} and returns the answer with its disclaimer, the
premise correction, the ranked factors and claims with their SQL and rows, every
critic round and its issues, the league memory used, timings, and which steps a model
or the code rules produced. Errors come back as {"error", "message"} JSON with a
4xx/5xx status, never a stack trace.

GET /trace/<run_id> returns {"run_id", "done", "lines": [trace lines so far]} for a run
this server is running or ran (the last MAX_RUNS), plus "status" and "result" (the POST
/run reply) once it is done. GET /trace/<run_id>.jsonl downloads the lines as JSONL.

SAMPLE_MODE defaults to true here (data from data/sample/, no Zetaris credentials);
.env or the environment can still set it. With no Meterless settings every model step
falls back to its code rules, so a run needs no credentials at all.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.config import load_env

load_env()  # .env first, so the default below never overrides it
os.environ.setdefault("SAMPLE_MODE", "true")

from app import pipeline, trace  # noqa: E402
from app.agents import memory  # noqa: E402
from app.agents.analyst import AnalystError  # noqa: E402
from app.pipeline import PipelineResult  # noqa: E402
from app.trace import new_run_id  # noqa: E402

MAX_QUESTION_CHARS = 500
MAX_BODY_BYTES = 64 * 1024
DEFAULT_PORT = 8000
DEFAULT_UI_PORT = 8080
UI_DIR = Path(__file__).resolve().parent / "app" / "ui"
UI_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}
RUN_ID = re.compile(r"[0-9a-f]{12}")
TRACE_PATH = re.compile(r"/trace/(?P<run_id>[^/]+?)(?P<jsonl>\.jsonl)?")
MAX_RUNS = 50  # runs whose trace GET /trace/<run_id> keeps in memory


class RequestError(Exception):
    def __init__(self, status: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status, self.error, self.message = status, error, message


class RunStore:
    """Trace lines of the runs this process is running or ran, for GET /trace/<run_id>."""

    def __init__(self, keep: int = MAX_RUNS) -> None:
        self._runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._keep = keep

    def start(self, run_id: str) -> list[dict[str, Any]]:
        """Register a run; returns the list its trace lines are appended to."""
        with self._lock:
            if run_id in self._runs:
                raise RequestError(409, "duplicate_run_id", f"Run {run_id} already exists; send a new run_id.")
            self._runs[run_id] = {"lines": [], "done": False, "status": None, "result": None}
            while len(self._runs) > self._keep:
                self._runs.popitem(last=False)
            return self._runs[run_id]["lines"]

    def finish(self, run_id: str, status: int, reply: dict[str, Any]) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(done=True, status=status, result=reply)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return None if run is None else {**run, "lines": list(run["lines"])}


RUNS = RunStore()


def handle_run(body: Any) -> tuple[int, dict[str, Any]]:
    """(HTTP status, JSON reply) for one /run request body (already parsed)."""
    if not isinstance(body, dict):
        raise RequestError(400, "bad_request", 'Send a JSON object: {"question": "...", "user_id": "..."}.')
    question = body.get("question")
    if not isinstance(question, str) or not question.strip():
        raise RequestError(400, "bad_request", '"question" must be a non-empty string.')
    if len(question) > MAX_QUESTION_CHARS:
        raise RequestError(400, "bad_request", f'"question" must be at most {MAX_QUESTION_CHARS} characters.')
    user_id = body.get("user_id")
    if user_id is not None and (not isinstance(user_id, str) or not memory.USER_ID.fullmatch(user_id)):
        raise RequestError(400, "bad_request", '"user_id" must be 1-64 letters, digits, "_" or "-".')

    run_id = body.get("run_id")
    if run_id is None:
        run_id = new_run_id()
    elif not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise RequestError(400, "bad_request", '"run_id" must be 12 lowercase hex characters.')
    lines = RUNS.start(run_id)
    unsubscribe = trace.subscribe(lambda line: lines.append(line) if line.get("run_id") == run_id else None)
    try:
        status, reply = _answer(run_id, question.strip(), user_id, lines)
    finally:
        unsubscribe()
    RUNS.finish(run_id, status, reply)
    if status == 200 and body.get("include_trace"):
        reply = {**reply, "trace": list(lines)}
    return status, reply


def _answer(run_id: str, question: str, user_id: str | None, lines: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    started = time.perf_counter()
    try:
        run = pipeline.answer(question, run_id=run_id, user_id=user_id)
    except AnalystError as error:
        return 422, {"error": "could_not_answer", "message": str(error), "run_id": run_id}
    except Exception as error:  # noqa: BLE001 - the reply never carries a stack trace
        trace.trace(run_id, "run", "request", "error", error=f"{type(error).__name__}: {str(error)[:300]}")
        return 500, {"error": "internal_error", "run_id": run_id,
                     "message": f"The run failed ({type(error).__name__}). The trace for run {run_id} in logs/ has details."}
    return 200, to_json(run, lines, time.perf_counter() - started)


def handle_trace(path: str) -> tuple[int, dict[str, Any] | str]:
    """(HTTP status, JSON reply, or JSONL text for .jsonl) for GET /trace/<run_id>[.jsonl]."""
    m = TRACE_PATH.fullmatch(path)
    if not m or not RUN_ID.fullmatch(m.group("run_id")):
        raise RequestError(400, "bad_request", "Use GET /trace/<run_id>, where run_id is 12 lowercase hex characters.")
    run_id = m.group("run_id")
    run = RUNS.get(run_id)
    if run is None:
        raise RequestError(404, "not_found", f"No run {run_id} on this server (it keeps the last {MAX_RUNS}).")
    if m.group("jsonl"):
        return 200, "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in run["lines"])
    reply = {"run_id": run_id, "done": run["done"], "lines": run["lines"]}
    if run["done"]:
        reply.update(status=run["status"], result=run["result"])
    return 200, reply


def to_json(run: PipelineResult, lines: list[dict[str, Any]], seconds: float) -> dict[str, Any]:
    r = run.result
    evidence = lambda items: [{"query_id": e.query_id, "sql": e.sql, "headers": e.headers, "rows": e.rows} for e in items]
    ctx = r.user_context
    handoff = next((l for l in lines if l["action"] == "handoff"), {})
    stored = next((l for l in lines if l["agent_name"] == "memory" and l["action"] == "store"), None)
    first_verdict = next((l for l in lines if l["action"] == "verdict" and l["status"] == "fallback"
                          and l.get("step") == "verdict"), None)
    return {
        "run_id": r.run_id,
        "question": r.question,
        "answer": f"{r.answer}\n\n{r.disclaimer}",
        "disclaimer": r.disclaimer,
        "approved": run.approved,
        "answer_before_critic": run.first_answer,
        "premise_correction": r.premise_correction,
        "question_type": r.question_type,
        "player": None if r.player is None else
                  {"name": r.player.name, "team": r.player.team, "position": r.player.position},
        "players": [{"name": p.name, "team": p.team, "position": p.position} for p in r.players],
        "season_context": r.season_context,
        "factors": [{"factor": f.factor, "support": f.support, "summary": f.summary, "rated_by": f.rated_by,
                     "rule": f.rule, "favours": f.favours, "evidence": evidence(f.evidence)} for f in r.factors],
        "claims": [{"text": c.text, "evidence": evidence(c.evidence)} for c in r.claims],
        "not_measurable": r.not_measurable,
        "critic": {
            "approved": run.approved,
            "rounds": [{"round": c.round, "status": c.status, "reviewed_by": c.reviewed_by, "answer": c.answer,
                        "issues": [{"check": i.check, "where": i.where, "claim": i.claim, "reason": i.reason,
                                    "blocking": i.blocking} for i in c.issues]} for c in run.critiques],
        },
        "memory": None if ctx is None else {
            "user_id": ctx.user_id, "remembered": ctx.remembered, "scoring": ctx.scoring,
            "scoring_label": ctx.scoring_label, "teams": ctx.teams,
            "roster": [{"name": p.name, "team": p.team, "position": p.position, "player_id": p.player_id}
                       for p in ctx.roster],
            "memory_ids": ctx.memory_ids, "context": ctx.context,
            "stored_this_run": stored.get("record_ids", []) if stored else [],
        },
        "steps": {
            "planner": handoff.get("classified_by"),  # "model" or "keyword"
            "memory_mining": stored.get("by") if stored else None,  # "code" or "model"
            "factors": {f.factor: f.rated_by for f in r.factors},  # "model" or "rule-based"
            "first_verdict": "rule-based" if first_verdict else "model",
            "final_verdict": r.verdict_by,
            "critic_reviews": [c.reviewed_by for c in run.critiques],  # "model" or "rule-based" (code checks only)
        },
        "timings": _timings(lines, seconds),
    }


def _timings(lines: list[dict[str, Any]], seconds: float) -> dict[str, Any]:
    """Wall-clock total, plus the time each agent spent in model calls and queries.

    Factor agents run in parallel, so their times add up to more than the wall clock.
    """
    by_agent: dict[str, int] = {}
    model_calls = []
    for l in lines:
        ms = l.get("duration_ms")
        if not isinstance(ms, int) or l["action"] in ("answer", "final", "store", "retrieve"):
            continue  # these durations already include their steps
        agent = l["agent_name"].split(":")[0]
        by_agent[agent] = by_agent.get(agent, 0) + ms
        if l["action"] == "model_call":
            model_calls.append({"agent": l["agent_name"], "step": l.get("step"), "status": l["status"],
                                "duration_ms": ms, "model": l.get("model")})
    memory_ms = sum(l["duration_ms"] for l in lines if l["agent_name"] == "memory"
                    and l["action"] in ("store", "retrieve") and isinstance(l.get("duration_ms"), int))
    return {"total_ms": round(seconds * 1000), "memory_ms": memory_ms, "agent_busy_ms": by_agent,
            "model_calls": model_calls}


def health() -> dict[str, Any]:
    sample = os.environ.get("SAMPLE_MODE", "").strip().lower() in ("1", "true", "yes")
    configured = all(os.environ.get(k) for k in ("METERLESS_BASE_URL", "METERLESS_RUNTIME_TOKEN", "METERLESS_MODEL"))
    return {"status": "ok", "sample_mode": sample, "model_configured": configured}


ROUTES = "Routes: POST /run, GET /trace/<run_id>, GET /health."


def ui_origins() -> set[str]:
    """Browser origins allowed to call the API: the UI's (UI_ORIGINS, comma-separated, overrides)."""
    configured = os.environ.get("UI_ORIGINS")
    if configured:
        return {o.strip().rstrip("/") for o in configured.split(",") if o.strip()}
    port = os.environ.get("UI_PORT") or DEFAULT_UI_PORT
    return {f"http://localhost:{port}", f"http://127.0.0.1:{port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "nfl-agent"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if path == "/health":
                self._send(200, health())
            elif path == "/run":
                self._send(405, {"error": "method_not_allowed", "message": "Use POST /run."})
            elif path.startswith("/trace/"):
                status, reply = handle_trace(path)
                if isinstance(reply, str):
                    run_id = TRACE_PATH.fullmatch(path).group("run_id")
                    self._send_text(status, reply, "application/x-ndjson; charset=utf-8",
                                    {"Content-Disposition": f'attachment; filename="trace-{run_id}.jsonl"'})
                else:
                    self._send(status, reply)
            else:
                self._send(404, {"error": "not_found", "message": ROUTES})
        except RequestError as error:
            self._send(error.status, {"error": error.error, "message": error.message})

    def do_OPTIONS(self) -> None:  # noqa: N802 - CORS preflight for the UI's POST /run
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/run":
            self._send(404, {"error": "not_found", "message": ROUTES})
            return
        try:
            body = self._read_json()
            status, reply = handle_run(body)
        except RequestError as error:
            status, reply = error.status, {"error": error.error, "message": error.message}
        except Exception as error:  # noqa: BLE001 - never a stack trace in the reply
            status, reply = 500, {"error": "internal_error", "message": f"Unexpected {type(error).__name__}."}
        self._send(status, reply)

    def _read_json(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise RequestError(400, "bad_request", "Bad Content-Length.") from None
        if length <= 0:
            raise RequestError(400, "bad_request", 'Send a JSON body: {"question": "..."}.')
        if length > MAX_BODY_BYTES:
            raise RequestError(413, "too_large", f"The body must be at most {MAX_BODY_BYTES} bytes.")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestError(400, "bad_json", f"The body is not valid JSON: {error}.") from None

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        self._send_text(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def _send_text(self, status: int, text: str, content_type: str, headers: dict[str, str] | None = None) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _cors_headers(self) -> None:
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if origin and origin in ui_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition")
        self.send_header("Vary", "Origin")

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{self.address_string()} {format % args}\n")  # access log on stderr; stdout is the trace


class UIHandler(BaseHTTPRequestHandler):
    """The web UI: a fixed set of static files from app/ui/, plus /config.js (the API's port)."""

    server_version = "nfl-agent-ui"
    api_port = DEFAULT_PORT

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/config.js":
            self._send(200, f"window.NFL_AGENT_CONFIG = {json.dumps({'apiPort': self.api_port})};\n", ".js")
            return
        name = UI_FILES.get(path)  # only these files: no path from the request reaches the filesystem
        if name is None:
            self._send(404, "Not found. The UI is at /.", ".txt")
            return
        self._send(200, (UI_DIR / name).read_text(encoding="utf-8"), Path(name).suffix)

    def _send(self, status: int, text: str, suffix: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "text/plain; charset=utf-8"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"ui {self.address_string()} {format % args}\n")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second server bind a port already in use, and the
    # first one keeps getting the requests; without it a busy port fails at start.
    allow_reuse_address = os.name != "nt"


def make_server(host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return Server((host, port), Handler)


def make_ui_server(host: str = "0.0.0.0", port: int = DEFAULT_UI_PORT, api_port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    handler = type("ConfiguredUIHandler", (UIHandler,), {"api_port": api_port})
    return Server((host, port), handler)


def serve(port: int, ui_port: int | None = DEFAULT_UI_PORT) -> None:
    """The API on port and (unless ui_port is None) the UI on ui_port, each in its own thread."""
    servers = [make_server(port=port)]
    if ui_port is not None:
        servers.append(make_ui_server(port=ui_port, api_port=port))
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    print(json.dumps({"event": "listening", "host": "0.0.0.0", "port": port, "ui_port": ui_port, **health()}),
          flush=True)
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)  # the servers run in their threads; this one only waits for Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NFL fantasy agent: Planner, Analyst, Critic.")
    parser.add_argument("question", nargs="?", help="answer this question and print the JSON reply")
    parser.add_argument("--user", help="user ID for league memory (scoring and roster)")
    parser.add_argument("--serve", action="store_true", help="serve the API and the web UI")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or DEFAULT_PORT))
    parser.add_argument("--ui-port", type=int, default=int(os.environ.get("UI_PORT") or DEFAULT_UI_PORT))
    parser.add_argument("--no-ui", action="store_true", help="serve the API only")
    args = parser.parse_args(argv)
    if args.serve or args.question is None:
        serve(args.port, None if args.no_ui else args.ui_port)
        return 0
    body = {"question": args.question, **({"user_id": args.user} if args.user else {})}
    try:
        status, reply = handle_run(body)
    except RequestError as error:
        status, reply = error.status, {"error": error.error, "message": error.message}
    sys.stdout.reconfigure(encoding="utf-8")
    print("--- result ---")  # the lines above are the run's trace
    print(json.dumps(reply, indent=2, ensure_ascii=False))
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
