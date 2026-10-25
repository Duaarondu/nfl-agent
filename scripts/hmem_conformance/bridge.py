"""One H-MEM operation per process, for the conformance shim (index.ts next to this file).

Reads {"dir", "clock", "op", "args", "overrides"} as JSON on stdin, runs the op on
app.engines.hmem.HMEM persisted in dir (state.json + ledger.jsonl, plus dreams.json and
backups/ for the dreaming and sleep services), and writes {"ok": result} or
{"error": message} as JSON on stdout.

overrides is the ro-001 shortcut: the runner sets supersededBy directly on record
objects it got back, which a cross-process shim cannot see, so the shim sends those
fields before each query and they are applied here without a ledger entry (the runner's
direct assignment is not ledgered in the reference either).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.engines.hmem import HMEM  # noqa: E402

ADD_ARGS = {"type": "type", "layer": "layer", "tags": "tags", "confidence": "confidence",
            "supersedes": "supersedes", "derivedFrom": "derived_from", "chatId": "chat_id"}


def record(r) -> dict:
    return None if r is None else dataclasses.asdict(r)


def run(req: dict):
    folder = Path(req["dir"])
    mem = HMEM(clock=lambda: req["clock"], persist_dir=folder, ledger_path=folder / "ledger.jsonl")
    for memory_id, fields in (req.get("overrides") or {}).items():
        r = mem.store.get(memory_id)
        if r is not None:
            r.supersededBy = fields.get("supersededBy")
    mem.store.persist()
    op, args = req["op"], req.get("args") or {}
    if op == "add":
        kwargs = {ADD_ARGS[k]: v for k, v in args.items() if k in ADD_ARGS and v is not None}
        return record(mem.add(args.get("content", ""), args.get("source") or "", **kwargs))
    if op == "feedback":
        mem.feedback(args["id"], args["kind"])
        return None
    if op == "query":
        result = mem.query(args["query"], top_n=args.get("topN"), threshold=args.get("threshold"))
        return {"memories": [{"memory": record(m.memory), "relevance": m.relevance} for m in result.memories],
                "context": result.context, "trace": result.trace}
    if op == "get":
        return record(mem.store.get(args["id"]))
    if op == "all":
        return [record(r) for r in mem.store.all()]
    if op == "history":
        return mem.ledger.history(args["id"])
    if op == "sleep_preview":
        return dataclasses.asdict(mem.sleep.preview())
    if op == "sleep_execute":
        return dataclasses.asdict(mem.sleep.execute(args.get("preview")))
    if op == "sleep_restore":
        mem.sleep.restore(args["backupId"])
        return None
    if op == "conflicts_scan":
        return [dataclasses.asdict(c) for c in mem.conflicts.scan()]
    if op == "conflicts_auto_resolve":
        return mem.conflicts.auto_resolve(args["conflict"])
    if op == "dream":
        return [dataclasses.asdict(p) for p in mem.dreaming.dream()]
    if op == "dream_approve":
        return record(mem.dreaming.approve(args["id"]))
    if op == "dream_reject":
        mem.dreaming.reject(args["id"])
        return None
    raise ValueError(f"unknown op {op}")


def main() -> int:
    req = json.loads(sys.stdin.read())
    try:
        out = {"ok": run(req)}
    except Exception as error:  # noqa: BLE001 - reported to the shim, which throws it
        out = {"error": f"{type(error).__name__}: {error}"}
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
