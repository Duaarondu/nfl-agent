import json


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
