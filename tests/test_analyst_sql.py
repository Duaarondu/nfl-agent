"""The optional free-form SQL path (ANALYST_FREE_SQL=true / free_sql=True)."""

import json

import pytest
from helpers import answer, classify, query, read_trace

from app.agents import analyst
from app.agents.analyst import AnalystError, analyze

EVANS_SQL = (
    "SELECT week, targets FROM NFLVERSE.player_stats "
    "WHERE player_name = 'M.Evans' ORDER BY week"
)


def sql_analyze(question, model, *replies, **kwargs):
    """Run the SQL path: call 1 classifies (no player), then the scripted SQL turns."""
    model.replies = [classify(), *replies]
    return analyze(question, free_sql=True, **kwargs)


def test_off_by_default_and_on_by_env(sample_dir, model, monkeypatch):
    model.replies = [classify(), answer()]
    monkeypatch.setenv("ANALYST_FREE_SQL", "true")
    analyze("q")
    assert "## NFLVERSE.player_stats" in model.calls[1][0]["content"]  # the schema


def test_query_then_answer_attaches_real_evidence(sample_dir, model):
    result = sql_analyze(
        "How is Mike Evans being used?", model,
        query(EVANS_SQL), answer(claims=[{"text": "Evans had 9 then 7 targets.", "query_ids": [1]}]),
    )

    assert result.answer == "Hold him."
    assert result.queries_used == 1
    [claim] = result.claims
    [evidence] = claim.evidence
    assert evidence.sql == EVANS_SQL
    assert evidence.rows == [["1", "9"], ["2", "7"]]
    assert '"rows": [["1", "9"], ["2", "7"]]' in model.calls[2][-1]["content"]


def test_season_context_in_first_sql_turn(sample_dir, model):
    result = sql_analyze("Who should I start?", model, answer())

    assert result.queries_used == 0
    assert "latest week with stats is week 2" in result.season_context
    assert "current season 2026" in model.calls[1][1]["content"]


def test_query_budget_is_six(sample_dir, model):
    result = sql_analyze("q", model, *[query(f"SELECT {i} AS n") for i in range(1, 8)], answer())

    assert result.queries_used == analyst.MAX_QUERIES == 6
    assert "used all 6 queries" in model.calls[8][-1]["content"]


def test_sql_error_is_fed_back_and_counts(sample_dir, model):
    result = sql_analyze("q", model, query("SELECT * FROM NFLVERSE.no_such_table"), answer())

    assert result.queries[0].error
    feedback = json.loads(model.calls[2][-1]["content"])
    assert feedback["query_id"] == 1 and "error" in feedback and feedback["queries_left"] == 5


def test_non_select_is_never_run(sample_dir, model):
    result = sql_analyze("q", model, query("DROP VIEW NFLVERSE.player_stats"), query(EVANS_SQL), answer())

    assert result.queries[0].error == "Only SELECT or WITH queries are allowed."
    assert result.queries[1].rows  # the view still exists


def test_factors_ranked_with_evidence_and_unsupported_kept(sample_dir, model):
    result = sql_analyze(
        "Why is Evans scoring?", model,
        query(EVANS_SQL),
        answer(
            factors=[
                {"factor": "Opportunity", "support": "strong", "summary": "Target share 27.63%", "query_ids": [1]},
                {"factor": "Matchups", "support": "not supported", "summary": "No pattern", "query_ids": []},
                {"factor": "Big plays", "support": "moderate", "summary": "uncited", "query_ids": [9]},
            ],
            not_measurable=["route participation"],
        ),
    )

    assert [(f.factor, f.support) for f in result.factors] == [
        ("Opportunity", "strong"),
        ("Matchups", "not supported"),
    ]
    assert result.factors[0].summary == "Target share 27.6%"


def test_bad_action_repaired_once_then_raises(sample_dir, model):
    assert sql_analyze("q", model, "not json", answer("Sit him.")).answer == "Sit him."
    with pytest.raises(AnalystError, match="not a valid action"):
        sql_analyze("q", model, "not json", "still not json")


def test_planned_queries_come_first_and_keep_full_budget(real_sample, model):
    model.replies = [
        classify("Christian Watson", "why"),
        *[query(f"SELECT {i} AS n") for i in range(1, 8)],
        answer(),
    ]
    result = analyze("Why is Christian Watson scoring?", free_sql=True)

    own = [q for q in result.queries if q.factor is None]
    assert [q.query_id for q in own] == list(range(9, 15))
    assert result.queries_used == 6
    assert "Queries already run" in model.calls[1][1]["content"]


def test_sql_turns_are_traced(sample_dir, model, trace_dir):
    sql_analyze("q", model, query(EVANS_SQL), answer(), run_id="run123")

    steps = [(l["action"], l.get("step")) for l in read_trace(trace_dir)]
    assert steps == [
        ("season_context", None), ("model_call", "classify"), ("handoff", None),
        ("model_call", "sql_loop"), ("query", None), ("model_call", "sql_loop"), ("answer", None),
    ]
