"""Entry point: POST /run (JSON in, JSON out), GET /health, and a CLI.

    python run.py                          serve on 0.0.0.0:8000 (PORT overrides the port)
    python run.py --serve [--port N]       the same
    python run.py "question" [--user ID]   answer one question and print the JSON reply

POST /run takes {"question": "...", "user_id": "..." (optional, turns on league memory),
"include_trace": false (optional)} and returns the answer with its disclaimer, the
premise correction, the ranked factors and claims with their SQL and rows, every
critic round and its issues, the league memory used, timings, and which steps a model
or the code rules produced. Errors come back as {"error", "message"} JSON with a
4xx/5xx status, never a stack trace.

SAMPLE_MODE defaults to true here (data from data/sample/, no Zetaris credentials);
.env or the environment can still set it. With no Meterless settings every model step
falls back to its code rules, so a run needs no credentials at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


class RequestError(Exception):
    def __init__(self, status: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status, self.error, self.message = status, error, message


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

    run_id = new_run_id()
    lines: list[dict[str, Any]] = []
    unsubscribe = trace.subscribe(lambda line: lines.append(line) if line.get("run_id") == run_id else None)
    started = time.perf_counter()
    try:
        run = pipeline.answer(question.strip(), run_id=run_id, user_id=user_id)
    except AnalystError as error:
        return 422, {"error": "could_not_answer", "message": str(error), "run_id": run_id}
    except Exception as error:  # noqa: BLE001 - the reply never carries a stack trace
        trace.trace(run_id, "run", "request", "error", error=f"{type(error).__name__}: {str(error)[:300]}")
        return 500, {"error": "internal_error", "run_id": run_id,
                     "message": f"The run failed ({type(error).__name__}). The trace for run {run_id} in logs/ has details."}
    finally:
        unsubscribe()
    reply = to_json(run, lines, time.perf_counter() - started)
    if body.get("include_trace"):
        reply["trace"] = lines
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
        "season_context": r.season_context,
        "factors": [{"factor": f.factor, "support": f.support, "summary": f.summary, "rated_by": f.rated_by,
                     "rule": f.rule, "evidence": evidence(f.evidence)} for f in r.factors],
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


class Handler(BaseHTTPRequestHandler):
    server_version = "nfl-agent"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] == "/health":
            self._send(200, health())
        elif self.path.split("?")[0] == "/run":
            self._send(405, {"error": "method_not_allowed", "message": "Use POST /run."})
        else:
            self._send(404, {"error": "not_found", "message": "Routes: POST /run, GET /health."})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/run":
            self._send(404, {"error": "not_found", "message": "Routes: POST /run, GET /health."})
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
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{self.address_string()} {format % args}\n")  # access log on stderr; stdout is the trace


def make_server(host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def serve(port: int) -> None:
    server = make_server(port=port)
    print(json.dumps({"event": "listening", "host": "0.0.0.0", "port": port, **health()}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NFL fantasy agent: Planner, Analyst, Critic.")
    parser.add_argument("question", nargs="?", help="answer this question and print the JSON reply")
    parser.add_argument("--user", help="user ID for league memory (scoring and roster)")
    parser.add_argument("--serve", action="store_true", help="serve POST /run and GET /health")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or DEFAULT_PORT))
    args = parser.parse_args(argv)
    if args.serve or args.question is None:
        serve(args.port)
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
