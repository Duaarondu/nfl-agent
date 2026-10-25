"""Run one question end to end through app/pipeline.py (Analyst, then the Critic loop),
with the live Meterless model:
    python scripts/try_pipeline.py [--live] [--user USER_ID] ["question"]
Data comes from sample mode (data/sample/) unless --live, which queries the live Zetaris
cluster (SAMPLE_MODE=false). --user turns on league memory for that user (stored in
MEMORY_DIR, default data/memory/).

A successful run is saved to examples/<question-slug>/<timestamp>-<run_id>/:
answer.md (what is printed: where the data came from, which steps were model vs
rule-based, the answer before and after the critic, each critic round and its issues),
response.json (the POST /run reply), result.json (the full result) and trace.jsonl.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
LIVE = "--live" in sys.argv[1:]
os.environ["SAMPLE_MODE"] = "false" if LIVE else "true"  # the model calls are live either way

from app import trace as trace_module  # noqa: E402
from app.agents.analyst import AnalystError  # noqa: E402
from app.pipeline import PipelineResult, answer  # noqa: E402

DEFAULT_QUESTION = "Why is Christian Watson scoring so many fantasy points this season?"
EXAMPLES_DIR = REPO_ROOT / "examples"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].rstrip("-")


def rows_text(headers: list[str], rows: list[list], limit: int = 20) -> list[str]:
    lines = ["      " + " | ".join(headers)]
    lines += ["      " + " | ".join("" if v is None else str(v) for v in row) for row in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"      ... {len(rows) - limit} more rows")
    return lines


def report(run: PipelineResult) -> str:
    result = run.result
    out = [*run_header(run), "",
        f"Question: {result.question}",
        f"Run {result.run_id}: {len(result.queries)} queries, {len(run.critiques)} critic rounds, {run.seconds:.1f}s",
        result.season_context,
    ]
    ctx = result.user_context
    if ctx:
        roster = ", ".join(f"{p.name} ({p.team}, {p.position})" for p in ctx.roster) or "none"
        teams = f"{ctx.teams}-team, " if ctx.teams else ""
        out += ["", f"League memory for {ctx.user_id}: {teams}{ctx.scoring_label} scoring; roster: {roster} "
                f"({len(ctx.memory_ids)} memories retrieved)"]
        if ctx.context:
            out.append(ctx.context)
    if result.premise_correction:
        out += ["", f"Premise correction: {result.premise_correction}"]
    out += ["", "Answer before the critic:", run.first_answer]

    out += ["", "Critic rounds:"]
    for c in run.critiques:
        out.append(f"  Round {c.round}: {c.status} (review: {c.reviewed_by}), "
                   f"{len(c.blocking)} blocking of {len(c.issues)} issues")
        for i in c.issues:
            kind = "blocking" if i.blocking else "recorded"
            out.append(f"    - [{kind}] {i.check} in {i.where}: {i.reason}")
            out.append(f"      claim: {i.claim}")

    status = "approved" if run.approved else f"unresolved after {len(run.critiques)} rounds"
    out += ["", f"Final answer ({status}; {result.verdict_by} verdict):", result.answer, "", f"_{result.disclaimer}_"]

    out += ["", "Factors (most to least supported):"]
    for i, f in enumerate(result.factors, 1):
        ids = ", ".join(str(e.query_id) for e in f.evidence) or "-"
        rated = f"rule-based: {f.rule}" if f.rated_by == "rule-based" else "model"
        rating = f"{f.support}" if not f.favours else ("even" if f.favours == "even" else f"favours {f.favours}, {f.support}")
        out.append(f"  {i}. {f.factor} [{rating}, {rated}] (queries {ids}): {f.summary}")
    if result.not_measurable:
        out += ["", "Not measurable with this data:", *(f"  - {item}" for item in result.not_measurable)]

    out += ["", "Claims:"]
    for i, claim in enumerate(result.claims, 1):
        out.append(f"  {i}. {claim.text}  (queries {', '.join(str(e.query_id) for e in claim.evidence)})")

    out += ["", "Queries:"]
    for q in result.queries:
        out.append(f"  [{q.query_id}] {q.purpose}\n      {q.sql}")
        out += [f"      ERROR: {q.error}"] if q.error else rows_text(q.headers, q.rows)
    return "\n".join(out)


def run_reply(run: PipelineResult) -> dict:
    """The POST /run reply for this run (run.py), from its saved trace lines."""
    import run as entry  # repo root, on sys.path above

    lines = [json.loads(l) for l in trace_lines(run.result.run_id)]
    return entry.to_json(run, lines, run.seconds)


def run_header(run: PipelineResult) -> list[str]:
    reply = run_reply(run)
    steps, t = reply["steps"], reply["timings"]
    source = ("live Zetaris cluster (SAMPLE_MODE=false)" if os.environ.get("SAMPLE_MODE") == "false"
              else "sample mode: cached nflverse slice in data/sample/ (SAMPLE_MODE=true)")
    factors = steps["factors"]
    by_model = [f for f, by in factors.items() if by == "model"]
    by_rule = [f for f, by in factors.items() if by != "model"]
    models = sorted({c["model"] for c in t["model_calls"] if c.get("model")})
    lines = [
        f"Data: {source}.",
        f"Models: Meterless Nightshift ({', '.join(models) or 'no successful model call'}).",
        "Steps (model vs rule-based):",
        f"  planner: {steps['planner']}",
    ]
    if steps["memory_mining"]:
        lines.append(f"  memory mining: {steps['memory_mining']}")
    lines += [
        f"  factors by model: {', '.join(by_model) or 'none'}",
        f"  factors by rules: {', '.join(by_rule) or 'none'}",
        f"  first verdict: {steps['first_verdict']}; final verdict: {steps['final_verdict']}",
        f"  critic reviews: {', '.join(steps['critic_reviews'])}",
        f"Timings: total {t['total_ms'] / 1000:.1f}s; "
        + ", ".join(f"{k} {v / 1000:.1f}s" for k, v in sorted(t["agent_busy_ms"].items()))
        + " (busy time; factor agents run in parallel)",
    ]
    failed = [c for c in t["model_calls"] if c["status"] != "ok"]
    if failed:
        lines.append("Failed or skipped model calls: " + "; ".join(
            f"{c['agent']} {c['step']} ({c['status']}, {c['duration_ms'] / 1000:.1f}s)" for c in failed))
    return lines


def trace_lines(run_id: str) -> list[str]:
    lines = []
    for path in sorted(trace_module.LOG_DIR.glob("trace-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if f'"run_id": "{run_id}"' in line:
                lines.append(line)
    return lines


def save(run: PipelineResult, text: str, group: str | None = None) -> Path:
    """Write the run to examples/<group or question slug>/<timestamp>-<run_id>/."""
    result = run.result
    folder = EXAMPLES_DIR / (group or slug(result.question)) / f"{datetime.now():%Y%m%d-%H%M%S}-{result.run_id}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "answer.md").write_text(f"```\n{text}\n```\n", encoding="utf-8")
    (folder / "result.json").write_text(
        json.dumps(dataclasses.asdict(run), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (folder / "trace.jsonl").write_text("\n".join(trace_lines(result.run_id)) + "\n", encoding="utf-8")
    (folder / "response.json").write_text(
        json.dumps(run_reply(run), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return folder


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # model text can hold characters cp1252 lacks
    args = [a for a in sys.argv[1:] if a != "--live"]
    user_id = None
    if args[:1] == ["--user"]:
        user_id, args = args[1], args[2:]
    question = args[0] if args else DEFAULT_QUESTION
    print(f"Question: {question}\n--- trace ---")
    started = time.perf_counter()
    try:
        run = answer(question, user_id=user_id)
    except AnalystError as error:
        print(f"FAILED after {time.perf_counter() - started:.1f}s: {error}")
        return 1

    text = report(run)
    print(f"\n--- result ---\n{text}")
    print(f"\nSaved to {save(run, text).relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
