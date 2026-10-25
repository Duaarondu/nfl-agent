import json
from pathlib import Path


def classify(player_name=None, question_type="other"):
    return json.dumps({"player_name": player_name, "question_type": question_type})


def query(sql, purpose="check"):
    return json.dumps({"action": "query", "purpose": purpose, "sql": sql})


def answer(text="Hold him.", claims=(), factors=(), **extra):
    return json.dumps(
        {"action": "answer", "answer": text, "claims": list(claims), "factors": list(factors), **extra}
    )


def read_trace(trace_dir):
    return [json.loads(line) for f in trace_dir.glob("*.jsonl") for line in f.read_text().splitlines()]


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(slug_start, run=""):
    """A saved examples/<slug>/<run>/result.json as an AnalystResult (the oldest run,
    or the one whose folder ends with run)."""
    from app.agents.analyst import result_from_dict

    [path] = sorted(EXAMPLES.glob(f"{slug_start}*/*{run}/result.json"))[:1]
    return result_from_dict(json.loads(path.read_text(encoding="utf-8")))
