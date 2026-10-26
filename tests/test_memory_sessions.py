"""The H-MEM engine test: league memory carries across two separate processes.

Session 1 tells the agent the league settings and roster; session 2 is a fresh Python
process that asks only the Bucs question. Both share one MEMORY_DIR and nothing else.
Meterless points at a closed port, so every model call fails fast and the code
fallbacks run: no credentials, deterministic, and the code-first path is what is tested.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SESSION_1 = ("12-team half-PPR, my TE is George Kittle and my WR is Davante Adams. "
             "Who becomes the Bucs' WR1 if Mike Evans is out?")
SESSION_2 = "Who becomes the Bucs' WR1 if Mike Evans is out?"

CHILD = """
import dataclasses, json, sys
from pathlib import Path
from app import pipeline, trace
trace.LOG_DIR = Path(sys.argv[1])
run = pipeline.answer(sys.argv[2], user_id="u1", session_id=sys.argv[3])
Path(sys.argv[4]).write_text(json.dumps(dataclasses.asdict(run)), encoding="utf-8")
"""


def session(tmp_path, n, question):
    env = {
        **os.environ,
        "SAMPLE_MODE": "true",
        "MEMORY_DIR": str(tmp_path / "memory"),
        "METERLESS_BASE_URL": "http://127.0.0.1:9",  # closed port: every model call fails fast
        "METERLESS_RUNTIME_TOKEN": "unused",
        "METERLESS_MODEL": "unused",
        "CRITIC_MODEL_REVIEW": "true",
    }
    out = tmp_path / f"session{n}.json"
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(tmp_path / "logs"), question, f"s{n}", str(out)],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    traces = [json.loads(l) for l in proc.stdout.splitlines() if l.startswith("{")]
    return json.loads(out.read_text(encoding="utf-8")), traces


def test_league_memory_carries_across_processes(tmp_path):
    first, traces_1 = session(tmp_path, 1, SESSION_1)
    [stored] = [t for t in traces_1 if (t["agent_name"], t["action"]) == ("memory", "store")]
    assert (stored["status"], stored["by"], len(stored["record_ids"])) == ("ok", "code", 4)
    assert first["result"]["user_context"]["scoring"] == "half"

    second, traces_2 = session(tmp_path, 2, SESSION_2)
    memory_lines = [(t["action"], t["status"]) for t in traces_2 if t["agent_name"] == "memory"]
    assert memory_lines == [("store", "none"), ("retrieve", "ok")]  # nothing new; all of it remembered
    [retrieved] = [t for t in traces_2 if t["action"] == "retrieve"]
    assert retrieved["count"] == 4 and retrieved["roster"] == ["George Kittle", "Davante Adams"]

    result = second["result"]
    ctx = result["user_context"]
    assert (ctx["scoring"], ctx["teams"]) == ("half", 12)
    # Half-PPR points in the SQL and in the answer, never PPR.
    sql = " ".join(q["sql"] for q in result["queries"])
    assert "(fantasy_points + fantasy_points_ppr) / 2" in sql and "AS ppr_" not in sql
    answer = result["answer"]
    assert "half-PPR points per game" in answer
    assert "PPR" not in answer.replace("half-PPR", "")
    # The stand-in is a WR below Evans (QA run: TE Kittle, then RB McCaffrey, were picked on target share).
    assert "so for fantasy: pick up Brandin Cooks" in answer
    assert "pick up George Kittle" not in answer
    assert second["approved"] and result["verdict_by"] == "rule-based"

    # The H-MEM audit ledger was appended by both processes.
    ledger = [json.loads(l) for l in (tmp_path / "logs" / "hmem" / "u1.ledger.jsonl").read_text().splitlines()]
    assert [e["action"] for e in ledger].count("create") == 4
    assert {e["actor"] for e in ledger} == {"user:u1"}
    state = json.loads((tmp_path / "memory" / "u1" / "state.json").read_text(encoding="utf-8"))
    assert {r["chatId"] for r in state["records"]} == {"s1"}
    assert all(r["accessCount"] == 2 for r in state["records"])  # read once per session
