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
    or the one whose folder ends with run).

    Runs saved before the Critic existed lack question_type, player and asked;
    they are rebuilt from the question and the player lookup rows.
    """
    from app.agents import factor_queries as fq
    from app.agents.analyst import AnalystResult, Claim, Evidence, Factor, QueryRecord

    [path] = sorted(EXAMPLES.glob(f"{slug_start}*/*{run}/result.json"))[:1]
    data = json.loads(path.read_text(encoding="utf-8"))
    data = data.get("result", data)  # pipeline runs wrap the Analyst result
    ev = lambda items: [Evidence(**e) for e in items]
    queries = [QueryRecord(**q) for q in data["queries"]]
    player = data.get("player")
    player = fq.Player(**player) if player else fq.parse_players(queries[0].rows, data["question"])[0]
    return AnalystResult(**{
        **data,
        "claims": [Claim(c["text"], ev(c["evidence"])) for c in data["claims"]],
        "factors": [Factor(**{**f, "evidence": ev(f["evidence"])}) for f in data["factors"]],
        "queries": queries,
        "question_type": data.get("question_type") or fq.guess_question_type(data["question"]),
        "player": player,
        "asked": data.get("asked") or data["question"],
    })
