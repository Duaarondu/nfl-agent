"""Run the Analyst live (Meterless model, sample-mode data): python scripts/try_analyst.py ["question"]

A successful run is saved to examples/<question-slug>/<timestamp>-<run_id>/:
answer.md (what is printed), result.json (the full result) and trace.jsonl.
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
os.environ["SAMPLE_MODE"] = "true"  # data from data/sample/; the model call is live

from app import trace as trace_module  # noqa: E402
from app.agents.analyst import AnalystError, AnalystResult, analyze  # noqa: E402

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


def report(result: AnalystResult, seconds: float) -> str:
    out = [
        f"Question: {result.question}",
        f"Run {result.run_id}: {len(result.queries)} queries, {seconds:.1f}s",
        result.season_context,
    ]
    if result.premise_correction:
        out += ["", f"Premise correction: {result.premise_correction}"]
    out += ["", f"Answer ({result.verdict_by} verdict):", result.answer, "", f"_{result.disclaimer}_"]

    out += ["", "Factors (most to least supported):"]
    for i, f in enumerate(result.factors, 1):
        ids = ", ".join(str(e.query_id) for e in f.evidence) or "-"
        rated = f"rule-based: {f.rule}" if f.rated_by == "rule-based" else "model"
        out.append(f"  {i}. {f.factor} [{f.support}, {rated}] (queries {ids}): {f.summary}")
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


def trace_lines(run_id: str) -> list[str]:
    lines = []
    for path in sorted(trace_module.LOG_DIR.glob("trace-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if f'"run_id": "{run_id}"' in line:
                lines.append(line)
    return lines


def save(result: AnalystResult, text: str) -> Path:
    folder = EXAMPLES_DIR / slug(result.question) / f"{datetime.now():%Y%m%d-%H%M%S}-{result.run_id}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "answer.md").write_text(f"```\n{text}\n```\n", encoding="utf-8")
    (folder / "result.json").write_text(
        json.dumps(dataclasses.asdict(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (folder / "trace.jsonl").write_text("\n".join(trace_lines(result.run_id)) + "\n", encoding="utf-8")
    return folder


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # model text can hold characters cp1252 lacks
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print(f"Question: {question}\n--- trace ---")
    started = time.perf_counter()
    try:
        result = analyze(question)
    except AnalystError as error:
        print(f"FAILED after {time.perf_counter() - started:.1f}s: {error}")
        return 1

    text = report(result, time.perf_counter() - started)
    print(f"\n--- result ---\n{text}")
    print(f"\nSaved to {save(result, text).relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
