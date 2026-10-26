"""DEMO: the live Critic loop on a SAVED Analyst answer: python scripts/demo_critic.py

This does not run the Analyst. It loads the Oct 22 Bucs/Evans run, whose model
verdict was "Start Deebo Samuel" (with copied support labels and backed only by the
depth chart), and feeds that saved answer into the live
critique -> revise loop (app.pipeline.review): the Critic's checks and model review,
and the Analyst's verdict revisions, all call the live Meterless model.

The run is saved to examples/critic-demo-<question-slug>/<timestamp>-<run_id>/, and
answer.md says at the top that it starts from a saved Analyst answer.
"""

from __future__ import annotations

import json
import sys
import time

import try_pipeline  # same folder; sets SAMPLE_MODE and the repo import path

from app.agents.analyst import result_from_dict
from app.pipeline import review
from app.trace import new_run_id, trace

SOURCE = try_pipeline.EXAMPLES_DIR / "archive" / "who-becomes-the-bucs-wr1-if-mike-evans-is-out" / "20261022-234321-d52e2e813360"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    result = result_from_dict(json.loads((SOURCE / "result.json").read_text(encoding="utf-8")))
    saved_run = result.run_id
    result.run_id = new_run_id()  # this demo's own trace lines
    source = SOURCE.relative_to(try_pipeline.REPO_ROOT).as_posix()
    trace(result.run_id, "demo", "load_saved_answer", "ok", source=source, saved_run_id=saved_run,
          answer=result.answer[:300])
    print(f"DEMO: critic loop on the saved Analyst answer from {source}\n--- trace ---")

    run = review(result, time.perf_counter())
    header = "\n".join([
        "DEMO - starts from a SAVED Analyst answer, not a fresh Analyst run.",
        f"Source: {source} (Analyst run {saved_run}, Oct 22). Its answer, factors and query rows",
        "were loaded as saved; only the critique -> revise loop below ran live.",
        "",
    ])
    text = header + "\n" + try_pipeline.report(run)
    print(f"\n--- result ---\n{text}")
    folder = try_pipeline.save(run, text, group="critic-demo-" + try_pipeline.slug(result.question))
    print(f"\nSaved to {folder.relative_to(try_pipeline.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
