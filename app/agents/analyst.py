"""Analyst agent: answers a fantasy question with claims backed by SQL and rows.

Takes the Planner's route (app.agents.planner: {player_name, question_type}), then code
looks the player up, checks the question's premise and runs the factor queries
(app.agents.factor_queries) through app.adapters.zetaris. Model calls (via
app.adapters.meterless) rate each factor in parallel and write the verdict; none sees
the schema.

Optional (off by default, ANALYST_FREE_SQL=true): instead of call 2, the model
may write its own SQL with the schema in its prompt, one JSON action per turn.

Evidence attached to claims and factors is the real SQL and rows from queries
this module ran, never text from the model.

With a UserContext from league memory (app.agents.memory), the factor queries compute
points in the user's league scoring, and the verdict is written for their roster.
"""

from __future__ import annotations

import json
import os
import re
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.adapters import meterless
from app.adapters.zetaris import ZetarisError, run_sql
from app.agents import factor_queries, planner
from app.agents.memory import UserContext, user_context_from_dict
from app.trace import new_run_id, trace

AGENT_NAME = "analyst"
MAX_QUERIES = 6
MAX_REPAIRS = 1
MAX_TURNS = MAX_QUERIES + 4
ROWS_SHOWN_TO_MODEL = 50
# Nemotron spends its whole token budget thinking unless this is off. Meterless does
# not forward it yet (checked 2026-10-22); sent anyway so it works once it does.
MODEL_PARAMS = {"temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False}}
# The model still thinks before replying; these leave room for that plus the JSON.
FACTOR_MAX_TOKENS = 4096
VERDICT_MAX_TOKENS = 4096
# Time limits (seconds). Each model request times out on its own; the factor agents
# share one window, and whatever is left of the total goes to the verdict call.
CALL_TIMEOUT = 60
CLASSIFY_TIMEOUT = planner.TIMEOUT
TOTAL_BUDGET = 150
FACTOR_WINDOW = 85
VERDICT_RESERVE = 45
MIN_RETRY_SECONDS = 20  # a repair retry needs at least this long to be worth starting
SUPPORT_LEVELS = ("strong", "moderate", "weak", "not supported")
SCHEMA = (Path(__file__).parent / "schema.md").read_text(encoding="utf-8")
# What the factor queries cannot see; listed with every answer.
NOT_MEASURABLE = (
    "Route participation and alignment",
    "Coverage faced and quality of the cornerbacks",
    "Coaching intent and play-calling plans",
    "Injury severity beyond the official report",
)

CLASSIFY_PROMPT = planner.PROMPT  # the Planner's classify prompt

FACTOR_PROMPT = """\
You rate one factor for a fantasy football question, from facts computed from nflverse
data. Reply with only this JSON:
{"support": "strong" | "moderate" | "weak" | "not supported",
 "summary": "<one sentence with numbers from the facts>"}
support: how well these facts explain or answer the question. Use only numbers in the
facts, at most 1 decimal place. If a change matters, say in which week it started."""

VERDICT_PROMPT = """\
You write the verdict for a fantasy football manager from factors already rated
against nflverse data. Reply with only this JSON:
{"verdict": "<short action phrase, e.g. Pick up Deebo Samuel / Start Christian Watson / Hold Mike Evans>",
 "why": "<2-3 complete sentences>"}
verdict starts with one of: Pick up, Add, Start, Sit, Bench, Hold, Drop, Stash.
In "why", lead with the most supported factors and their numbers; use only numbers
given, at most 1 decimal place. If a premise check is given, answer the corrected
question. If a user context is given, quote points in its scoring and never recommend
picking up a player already on its roster. Do not add a disclaimer."""
VERDICT_ACTIONS = ("pick up", "add", "start", "sit", "bench", "hold", "drop", "stash")
DISCLAIMER = "Informational only, based on nflverse data; not betting advice."

SQL_SYSTEM_PROMPT = """\
You are the Analyst in a multi-agent assistant for fantasy football managers making
waiver and lineup decisions. You answer from nflverse data by writing SQL.

# How to reply
Every reply is exactly one JSON object and nothing else.

To run a query:
{"action": "query", "purpose": "<what this checks>", "sql": "<one SELECT statement>"}

To answer:
{"action": "answer",
 "premise_correction": null or "<what the question got wrong, per the data>",
 "answer": "<verdict or recommendation first, then the explanation>",
 "claims": [{"text": "<one factual claim with its numbers>", "query_ids": [1]}],
 "factors": [{"factor": "<name>", "support": "strong|moderate|weak|not supported",
              "summary": "<what the data shows, with numbers>", "query_ids": [2]}],
 "not_measurable": ["<things that matter but the data cannot measure>"]}

# Queries already run
Before your first turn the system looks up the player the question names and runs
standard queries for them; their results come with the question, numbered from
query_id 1. They do not count toward your budget, and you cite them like your own.
For a "why" question they cover every factor listed below, so only query for what
they miss. A "Premise check" line with the question is a contradiction found in the
data: put it in premise_correction and answer the corrected question.

# Queries
- At most %(max_queries)d queries of your own per question. Each result comes back with a query_id.
  A failed query still uses up one of your queries.
- One SELECT (or WITH ... SELECT) statement per query, no semicolon. Tables: NFLVERSE.<table>.
- The SQL must run on both Spark SQL and DuckDB. Use only standard SQL: SELECT, WHERE,
  JOIN, GROUP BY, ORDER BY, LIMIT, CASE, CAST, COALESCE, LOWER, LIKE, SUM, AVG, COUNT,
  MIN, MAX, ROUND, window functions with OVER. Do not use ILIKE, QUALIFY, ::, or quoted
  identifiers. String literals use single quotes.
- Round every non-integer column to 1 decimal place in the SQL: ROUND(x, 1).
  Show shares as percentages: ROUND(100 * target_share, 1) AS target_share_pct.
- Keep results small: filter, aggregate, and use LIMIT 25 or less.
- Look players up by player_stats.player_display_name (full name), then use player_id.
- Check several things in one query where you can (e.g. targets, target share, air
  yards, touchdowns and fantasy points by week in a single player_stats query).

# Rules for the answer
- Check the question's premise first: the player's team, position and status in the
  data. If the question gets something wrong (e.g. the wrong team), set
  premise_correction to what the data shows and answer the corrected question.
- Only state numbers that appear in your query results. Every claim and factor lists
  the query_ids that support it.
- Quote numbers with at most 1 decimal place.
- Give a clear verdict or recommendation (e.g. pick up / start / sit / hold).
- When a change explains something, say in which week it started.
- Do not add a disclaimer; one is added later.

# "Why" questions
Do not settle on one explanation. Test these factors, rank them in "factors" from most
to least supported by the data, and mark any the data does not back as "not supported":
1. Opportunity: snap %%, targets, target share.
2. Teammate absences: injuries to teammates and when they happened.
3. Team pass rate and game script.
4. Big plays: air yards, yards per target.
5. Touchdowns and red-zone usage.
6. Matchups: the opponents faced.
List in "not_measurable" what matters but this data cannot measure (e.g. route
participation, coverage faced, coaching intent). For other questions, "factors" may be [].

# Data
Season context is given with the question. Schema:

%(schema)s
"""


class AnalystError(RuntimeError):
    pass


@dataclass
class Evidence:
    query_id: int
    sql: str
    headers: list[str]
    rows: list[list[Any]]


@dataclass
class Claim:
    text: str
    evidence: list[Evidence]


@dataclass
class Factor:
    factor: str
    support: str
    summary: str
    evidence: list[Evidence]
    rated_by: str = "model"  # "model" (its factor agent) or "rule-based" (code thresholds)
    rule: str | None = None  # the threshold applied, when rule-based


@dataclass
class QueryRecord:
    query_id: int
    purpose: str
    sql: str
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    error: str | None = None
    factor: str | None = None  # set for queries run in code before the model's turn


@dataclass
class AnalystResult:
    run_id: str
    question: str
    answer: str
    premise_correction: str | None
    claims: list[Claim]
    factors: list[Factor]
    not_measurable: list[str]
    queries: list[QueryRecord]
    season_context: str
    verdict_by: str = "model"  # "model" or "rule-based" (the verdict call failed)
    disclaimer: str = DISCLAIMER
    question_type: str = "other"
    player: factor_queries.Player | None = None
    asked: str = ""  # the question the agents answered, with any wrong premise corrected
    user_context: UserContext | None = None  # league memory the answer was written for

    @property
    def queries_used(self) -> int:
        """Queries the model wrote (the planned ones run in code are not counted)."""
        return sum(1 for q in self.queries if q.factor is None)


@dataclass
class Plan:
    """What code runs between the model calls: player lookup, premise check, factor queries."""

    question_type: str = "other"
    player: factor_queries.Player | None = None
    queries: list[QueryRecord] = field(default_factory=list)
    wrong_teams: list[str] = field(default_factory=list)

    def corrected_question(self, question: str) -> str:
        if not (self.player and self.wrong_teams):
            return question
        return factor_queries.corrected_question(question, self.wrong_teams, self.player.team)

    def premise_note(self) -> str | None:
        if not (self.player and self.wrong_teams):
            return None
        p = self.player
        return (
            f"{p.name} is on {p.team} in the data (rosters, week {p.roster_week}), "
            f"not {' or '.join(self.wrong_teams)}."
        )


def analyze(
    question: str, run_id: str | None = None, free_sql: bool | None = None, memory: UserContext | None = None,
    route: planner.Route | None = None,
) -> AnalystResult:
    """Answer one fantasy question. Raises AnalystError if no valid answer comes back.

    free_sql (default: ANALYST_FREE_SQL env, off) lets the model write its own SQL
    instead of interpreting only the factor queries. memory is the user's league
    context (scoring and roster), if any. route is the Planner's handoff; without one
    the Planner runs here.
    """
    run_id = run_id or new_run_id()
    started = time.perf_counter()
    if free_sql is None:
        free_sql = os.environ.get("ANALYST_FREE_SQL", "").strip().lower() in ("1", "true", "yes")
    context, season, week = _season_context(run_id)
    route = route or planner.plan(run_id, question)
    player_name, question_type = route.player_name, route.question_type
    scoring = factor_queries.SCORINGS[memory.scoring] if memory else factor_queries.PPR
    plan = _run_plan(run_id, question, player_name, question_type, season, week, scoring, memory)

    if free_sql:
        return _sql_loop(run_id, question, context, plan)
    if not plan.queries:
        trace(run_id, AGENT_NAME, "answer", "error", reason="no player found")
        raise AnalystError(
            "Could not find the NFL player this question is about in this season's rosters. "
            "Name the player in full."
        )

    deadline = started + TOTAL_BUDGET
    window = max(1.0, min(FACTOR_WINDOW, deadline - time.perf_counter() - VERDICT_RESERVE))
    # The agents get the question with its wrong premise already corrected from the data.
    asked = plan.corrected_question(question)
    factors = _rate_factors(run_id, asked, plan, window=window)
    facts = _verdict_facts(asked, context, plan.premise_note(), plan.queries, factors, memory)
    verdict = _verdict(run_id, plan.question_type, plan.player, facts, plan.queries, factors, deadline=deadline,
                       memory=memory)
    result = _assemble(run_id, question, asked, context, plan, factors, verdict, started)
    result.user_context = memory
    return result


def result_from_dict(data: dict[str, Any]) -> AnalystResult:
    """An AnalystResult from its saved JSON (examples/*/result.json).

    Accepts a pipeline run (the result sits under "result"). Runs saved before the
    Critic existed lack question_type, player and asked; they are rebuilt from the
    question and the player lookup rows.
    """
    data = data.get("result", data)
    ev = lambda items: [Evidence(**e) for e in items]
    queries = [QueryRecord(**q) for q in data["queries"]]
    player = data.get("player")
    player = factor_queries.Player(**player) if player else factor_queries.parse_players(queries[0].rows, data["question"])[0]
    return AnalystResult(**{
        **data,
        "claims": [Claim(c["text"], ev(c["evidence"])) for c in data["claims"]],
        "factors": [Factor(**{**f, "evidence": ev(f["evidence"])}) for f in data["factors"]],
        "queries": queries,
        "question_type": data.get("question_type") or factor_queries.guess_question_type(data["question"]),
        "player": player,
        "asked": data.get("asked") or data["question"],
        "user_context": user_context_from_dict(data.get("user_context")),
    })


def revise_verdict(result: AnalystResult, issues: list[str], deadline: float, round: int) -> None:
    """Rerun only the verdict step, with the critic's issues in the prompt; updates result.

    The factor agents are not rerun. If the call fails, the rule-based verdict is used.
    """
    if result.player is None:  # free-SQL answers have no planned facts to re-verdict from
        trace(result.run_id, AGENT_NAME, "revise", "skipped", target_agent="critic", round=round,
              reason="no planned factor queries")
        return
    facts = _verdict_facts(
        result.asked or result.question, result.season_context, result.premise_correction,
        result.queries, result.factors, result.user_context,
    )
    answer, by = _verdict(
        result.run_id, result.question_type, result.player, facts, result.queries, result.factors,
        deadline=deadline, revision=(result.answer, issues), memory=result.user_context,
    )
    result.answer, result.verdict_by = answer, by
    trace(result.run_id, AGENT_NAME, "revise", "ok" if by == "model" else "fallback", target_agent="critic",
          round=round, verdict_by=by, issues=len(issues))


def _player_line(plan: Plan) -> str:
    line = _summary(plan.queries[0])
    note = plan.premise_note()
    return f"{line} Premise check: {note} Answer for the team in the data." if note else line


def _summary(record: QueryRecord) -> str:
    if record.error:
        return "Query failed; no data."
    return " ".join(factor_queries.summarize(record.factor or "", record.headers, record.rows))


def _evidence(record: QueryRecord) -> list[Evidence]:
    return [] if record.error else [Evidence(record.query_id, record.sql, record.headers, record.rows)]


def _rate_factors(run_id: str, question: str, plan: Plan, window: float) -> list[Factor]:
    """One factor agent (model call) per factor, all in parallel, sharing one time window.

    A factor whose agent fails after its retry, or has no reply when the window
    closes, is rated with the fixed rules in factor_queries.rule_rating.
    Returns the factors ranked from most to least supported.
    """
    rated = [q for q in plan.queries if q.factor in factor_queries.RATED_FACTORS]
    player_line = _player_line(plan)
    replies: dict[int, dict[str, Any] | Exception] = {}
    deadline = time.perf_counter() + window

    def work(record: QueryRecord) -> None:
        try:
            replies[record.query_id] = _factor_agent(run_id, question, player_line, record, deadline)
        except Exception as error:  # noqa: BLE001 - any failure means the rules take over
            replies[record.query_id] = error

    # Daemon threads: an agent still waiting when the window closes must not hold up exit.
    threads = [
        threading.Thread(target=work, args=(q,), name=f"factor_agent:{q.factor}", daemon=True)
        for q in rated if not q.error
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(max(0.0, deadline - time.perf_counter()))

    results = {q.factor: (q.headers, q.rows) for q in plan.queries if not q.error}
    factors = []
    for q in rated:
        agent = f"factor_agent:{q.factor}"
        reply = replies.get(q.query_id)
        if isinstance(reply, dict):
            factor = Factor(q.factor, reply["support"], round_numbers(reply["summary"]), _evidence(q))
            trace(run_id, agent, "rate_factor", "ok", rated_by="model", support=factor.support, query_id=q.query_id)
        else:
            reason = "query failed" if q.error else (str(reply) if reply else f"no reply within {window:.0f}s")
            support, rule = factor_queries.rule_rating(q.factor, results)
            factor = Factor(q.factor, support, _summary(q), _evidence(q), rated_by="rule-based", rule=rule)
            trace(run_id, agent, "rate_factor", "fallback", rated_by="rule-based", support=support,
                  rule=rule, query_id=q.query_id, reason=reason[:300])
        factors.append(factor)
    return sorted(factors, key=lambda f: SUPPORT_LEVELS.index(f.support))


def _factor_agent(
    run_id: str, question: str, player_line: str, record: QueryRecord, deadline: float
) -> dict[str, Any]:
    facts = "\n".join(f"- {line}" for line in factor_queries.summarize(record.factor or "", record.headers, record.rows))
    messages = [
        {"role": "system", "content": FACTOR_PROMPT},
        {"role": "user", "content": f"Question: {question}\nPlayer: {player_line}\nFactor: {record.factor}\nFacts:\n{facts}"},
    ]
    return _ask_json(
        run_id, "factor", messages, FACTOR_MAX_TOKENS, _check_rating,
        agent_name=f"factor_agent:{record.factor}", timeout=CALL_TIMEOUT, deadline=deadline,
    )


def _check_rating(reply: dict[str, Any]) -> None:
    support = str(reply.get("support", "")).strip().lower()
    if support not in SUPPORT_LEVELS:
        raise ValueError(f"support must be one of {', '.join(SUPPORT_LEVELS)}")
    if not isinstance(reply.get("summary"), str) or not reply["summary"].strip():
        raise ValueError("needs a non-empty 'summary' string")
    reply["support"] = support


def _verdict(
    run_id: str, question_type: str, player: factor_queries.Player, facts: list[str],
    queries: list[QueryRecord], factors: list[Factor], deadline: float,
    revision: tuple[str, list[str]] | None = None, memory: UserContext | None = None,
) -> tuple[str, str]:
    """(answer, verdict_by): the model's verdict, or the code rules' if that call fails.

    revision is (previous answer, critic issues) when the critic sent the answer back.
    The rule-based stand-in skips players already on the user's roster (memory).
    """
    note = ""
    try:
        reply = _model_verdict(run_id, facts, deadline, revision)
        verdict, why, by = reply["verdict"], reply["why"], "model"
    except AnalystError as error:
        results = {q.factor: (q.headers, q.rows) for q in queries if not q.error}
        ranked = [(f.factor, f.support, f.summary) for f in factors]
        roster = memory.roster_names if memory else ()
        verdict, why = factor_queries.rule_verdict(question_type, player, results, ranked, roster)
        note = "(Rule-based verdict: the verdict model call failed, so fixed thresholds were applied.)"
        by = "rule-based"
        trace(run_id, AGENT_NAME, "verdict", "fallback", rated_by=by, verdict=verdict,
              step="revise" if revision else "verdict", reason=str(error)[:300])
    return round_numbers(_compose(question_type, verdict, why, note)), by


def _compose(question_type: str, verdict: str, why: str, note: str = "") -> str:
    """Join verdict and why with sentence case and one period each.

    A "why" question gets the explanation first and the action last
    ("He ... Verdict: hold Christian Watson."); every other type leads with the action.
    """
    verdict, why = verdict.strip().rstrip(".").strip(), why.strip()
    why = why[:1].upper() + why[1:]
    if why and not why.endswith((".", "!", "?")):
        why += "."
    if question_type == "why" and why:
        text = f"{why} Verdict: {verdict[:1].lower() + verdict[1:]}."
    else:
        verdict = verdict[:1].upper() + verdict[1:]
        text = f"{verdict}. {why}" if why else f"{verdict}."
    return f"{text} {note}" if note else text


def _check_verdict(reply: dict[str, Any]) -> None:
    verdict, why = reply.get("verdict"), reply.get("why")
    if not isinstance(verdict, str) or not verdict.strip().lower().startswith(VERDICT_ACTIONS):
        raise ValueError(f"'verdict' must start with one of: {', '.join(VERDICT_ACTIONS)}")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("needs a non-empty 'why' string")


def _verdict_facts(
    question: str, context: str, premise_note: str | None, queries: list[QueryRecord], factors: list[Factor],
    memory: UserContext | None = None,
) -> list[str]:
    lines = [context]
    if memory and memory.prompt_block():
        lines.append(memory.prompt_block())
    lines.append(f"Question: {question}")
    if premise_note:
        lines.append(f"Premise check: {premise_note}")
    lines.append(f"Player: {_summary(queries[0])}")
    status = next((q for q in queries if q.factor == "Status"), None)
    if status:
        lines.append(f"Injury status: {_summary(status)}")
    lines.append("Rated factors (most supported first):")
    lines += [f"- {f.factor} [{f.support}]: {f.summary}" for f in factors]
    return lines


def _model_verdict(
    run_id: str, facts: list[str], deadline: float, revision: tuple[str, list[str]] | None = None
) -> dict[str, Any]:
    content = "\n".join(facts)
    if revision:
        previous, issues = revision
        content += (
            f"\n\nYour previous answer:\n{previous}\n"
            "A critic checked it against the data and found these problems. Fix every one "
            "and keep what was right:\n" + "\n".join(f"- {issue}" for issue in issues)
        )
    messages = [
        {"role": "system", "content": VERDICT_PROMPT},
        {"role": "user", "content": content},
    ]
    return _ask_json(
        run_id, "revise" if revision else "verdict", messages, VERDICT_MAX_TOKENS, _check_verdict,
        timeout=CALL_TIMEOUT, deadline=deadline,
    )


def _assemble(
    run_id: str, question: str, asked: str, context: str, plan: Plan,
    factors: list[Factor], verdict: tuple[str, str], started: float,
) -> AnalystResult:
    """Claims are the code-computed facts of each query that bears on the answer."""
    claims = [
        Claim(_summary(q), _evidence(q))
        for q in plan.queries
        if q.factor in ("Player lookup", "Status") and not q.error
    ]
    claims += [Claim(f.summary, f.evidence) for f in factors if f.evidence and f.support != "not supported"]
    answer, verdict_by = verdict
    result = AnalystResult(
        run_id=run_id,
        question=question,
        answer=answer,
        premise_correction=plan.premise_note(),
        claims=claims,
        factors=factors,
        not_measurable=list(NOT_MEASURABLE),
        queries=plan.queries,
        season_context=context,
        verdict_by=verdict_by,
        question_type=plan.question_type,
        player=plan.player,
        asked=asked,
    )
    trace(
        run_id, AGENT_NAME, "answer", "ok", duration_ms=_ms(started),
        claims=len(claims), factors=len(factors), queries=len(plan.queries),
        rule_based=[f.factor for f in factors if f.rated_by == "rule-based"],
        verdict_by=verdict_by, premise_corrected=result.premise_correction is not None,
    )
    return result


def _check_answer(reply: dict[str, Any]) -> None:
    if not isinstance(reply.get("answer"), str) or not reply["answer"].strip():
        raise ValueError("needs a non-empty 'answer' string")


def _ask_json(
    run_id: str, step: str, messages: list[dict[str, Any]], max_tokens: int, check,
    agent_name: str = AGENT_NAME, timeout: float | None = None, deadline: float | None = None,
) -> dict[str, Any]:
    """One model call that must return a JSON object passing check(); one repair retry.

    Each attempt gets at most `timeout` seconds and must end by `deadline`
    (a time.perf_counter() value); a repair is only tried with MIN_RETRY_SECONDS left.
    (Within an attempt, the adapter also retries once on a 5xx or an empty reply.)
    """
    messages = list(messages)
    for repairs in range(MAX_REPAIRS + 1):
        limit = timeout
        if deadline is not None:
            left = deadline - time.perf_counter()
            if left <= 0 or (repairs and left < MIN_RETRY_SECONDS):
                trace(run_id, agent_name, "model_call", "skipped", retry_count=repairs, step=step,
                      reason=f"only {max(left, 0):.0f}s left in the time budget")
                raise AnalystError(f"Model call ({step}) skipped: the time budget is used up.")
            limit = left if limit is None else min(limit, left)
        reply = _call_model(
            messages, run_id, repairs, step=step, max_tokens=max_tokens, agent_name=agent_name, timeout=limit
        )
        try:
            parsed = _parse_json(reply)
            check(parsed)
            return parsed
        except ValueError as error:
            status = "retry" if repairs < MAX_REPAIRS else "error"
            trace(run_id, agent_name, "parse_reply", status, retry_count=repairs + 1, step=step, error=str(error))
            if status == "error":
                raise AnalystError(f"Model reply ({step}) was not valid: {error}") from error
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That reply was invalid ({error}). Reply with only the JSON object as specified."},
            ]
    raise AssertionError("unreachable")


def _sql_loop(run_id: str, question: str, context: str, plan: Plan) -> AnalystResult:
    """Optional free-form SQL path: the model sees the schema and writes its own queries."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SQL_SYSTEM_PROMPT % {"max_queries": MAX_QUERIES, "schema": SCHEMA}},
        {"role": "user", "content": _first_message(context, question, plan)},
    ]
    queries: list[QueryRecord] = list(plan.queries)
    model_queries = 0
    repairs = 0

    for _ in range(MAX_TURNS):
        reply = _call_model(messages, run_id, repairs, step="sql_loop")
        try:
            action = _parse_action(reply)
        except ValueError as error:
            if repairs >= MAX_REPAIRS:
                trace(run_id, AGENT_NAME, "parse_reply", "error", retry_count=repairs, error=str(error))
                raise AnalystError(f"Model reply was not a valid action: {error}") from error
            repairs += 1
            trace(run_id, AGENT_NAME, "parse_reply", "retry", retry_count=repairs, error=str(error))
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That reply was invalid ({error}). Reply with exactly one JSON object as specified."},
            ]
            continue

        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        if action["action"] == "answer":
            return _build_result(run_id, question, context, action, queries, plan)

        if model_queries >= MAX_QUERIES:
            trace(run_id, AGENT_NAME, "query", "refused", sql=action["sql"], reason="query budget used up")
            messages.append({"role": "user", "content": f"You have used all {MAX_QUERIES} queries. Reply now with the answer action."})
            continue
        sql = action["sql"].strip().rstrip(";").strip()
        record = QueryRecord(query_id=len(queries) + 1, purpose=str(action.get("purpose", "")), sql=sql)
        _run_query(run_id, record)
        queries.append(record)
        model_queries += 1
        messages.append({"role": "user", "content": _format_result(record, MAX_QUERIES - model_queries)})

    trace(run_id, AGENT_NAME, "answer", "error", reason="turn limit reached")
    raise AnalystError(f"No answer after {MAX_TURNS} model turns.")


def _season_context(run_id: str) -> tuple[str, int | None, int | None]:
    """Latest season and week with stats; run in code, not counted toward the query budget."""
    sql = "SELECT MAX(season) AS season, MAX(week) AS latest_week FROM NFLVERSE.player_stats"
    started = time.perf_counter()
    try:
        result = run_sql(sql)
        season, week = (int(v) for v in result["data"][0])
    except (ZetarisError, LookupError, TypeError, ValueError) as error:
        trace(run_id, AGENT_NAME, "season_context", "error", sql=sql, duration_ms=_ms(started), error=str(error))
        return "Season context: unknown (query it if you need it).", None, None
    trace(run_id, AGENT_NAME, "season_context", "ok", sql=sql, rows_returned=1, duration_ms=_ms(started))
    text = (
        f"Season context: current season {season}; the latest week with stats is week {week}. "
        f'"This season" means season {season}.'
    )
    return text, season, week


def _run_plan(
    run_id: str, question: str, player_name: str | None, question_type: str,
    season: int | None, week: int | None, scoring: factor_queries.Scoring = factor_queries.PPR,
    memory: UserContext | None = None,
) -> Plan:
    """Look the player up (the model's name first, then names in the question) and run their factor queries.

    Without a name from the model, a player the question names who is not on the user's
    roster comes first ("my TE is George Kittle. Who replaces Mike Evans?" is about Evans).
    """
    plan = Plan(question_type=question_type)
    candidates = factor_queries.name_candidates(question)
    if player_name:
        candidates = [player_name.lower(), *[c for c in candidates if c != player_name.lower()]]
    if season is None or week is None or not candidates:
        return plan

    lookup = QueryRecord(1, "team, position and roster status", factor_queries.lookup_sql(candidates, season))
    lookup.factor = "Player lookup"
    _run_query(run_id, lookup, action="player_lookup")
    if lookup.error or not lookup.rows:
        return plan
    try:
        players = factor_queries.parse_players(lookup.rows, question)
    except (IndexError, TypeError, ValueError) as error:
        trace(run_id, AGENT_NAME, "player_lookup", "error", error=f"bad lookup rows: {error}")
        return plan

    named = [p for p in players if player_name and p.name.lower() == player_name.lower()]
    not_owned = [p for p in players if not (memory and memory.owns(p.name))]
    plan.player = (named or not_owned or players)[0]
    plan.queries.append(lookup)
    plan.wrong_teams = factor_queries.wrong_teams(question, plan.player)
    for planned in factor_queries.plan(question_type, plan.player, season, week, scoring):
        record = QueryRecord(len(plan.queries) + 1, planned.purpose, planned.sql, factor=planned.factor)
        _run_query(run_id, record, action="factor_query")
        plan.queries.append(record)
    return plan


def _first_message(context: str, question: str, plan: Plan) -> str:
    parts = [context, f"Question: {question}"]
    note = plan.premise_note()
    if note:
        parts.append(f"Premise check: {note} (query 1)")
    if plan.queries:
        results = [json.loads(_format_result(q)) | {"factor": q.factor, "purpose": q.purpose} for q in plan.queries]
        parts.append(
            "Queries already run (not counted toward your budget):\n"
            + "\n".join(json.dumps(r, ensure_ascii=False) for r in results)
        )
    return "\n\n".join(parts)


def _call_model(
    messages: list[dict[str, Any]], run_id: str, retry_count: int,
    step: str = "", max_tokens: int | None = None,
    agent_name: str = AGENT_NAME, timeout: float | None = None,
) -> str:
    started = time.perf_counter()
    params = dict(MODEL_PARAMS, **({"max_tokens": max_tokens} if max_tokens else {}))
    prompt_chars = sum(len(m["content"]) for m in messages)
    try:
        response = _chat_within(messages, timeout, params, name=f"model_call:{agent_name}")
    except meterless.MeterlessError as error:
        trace(run_id, agent_name, "model_call", "error", retry_count=retry_count, duration_ms=_ms(started),
              step=step, prompt_chars=prompt_chars, error=str(error))
        raise AnalystError(f"Model call failed: {error}") from error
    model = (response.get("meterless") or {}).get("routed_model") or response.get("model")
    try:
        text = response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as error:
        trace(run_id, agent_name, "model_call", "error", model=model, duration_ms=_ms(started), step=step, error="bad response shape")
        raise AnalystError("Unexpected chat response shape.") from error
    usage = response.get("usage") or {}
    trace(run_id, agent_name, "model_call", "ok", retry_count=retry_count, model=model, duration_ms=_ms(started),
          step=step, prompt_chars=prompt_chars, completion_tokens=usage.get("completion_tokens"))
    return text


def _chat_within(messages: list[dict[str, Any]], timeout: float | None, params: dict[str, Any], name: str) -> Any:
    """meterless.chat with a wall-clock limit on the whole call.

    The adapter's own timeout only bounds each socket read, and its retry adds a
    second attempt, so a call can otherwise run well past `timeout`.
    """
    if timeout is None:
        return meterless.chat(messages, **params)
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["response"] = meterless.chat(messages, timeout=timeout, **params)
        except Exception as error:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = error

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise meterless.MeterlessError(f"No reply within {timeout:.0f}s.")
    if "error" in box:
        raise box["error"]
    return box["response"]


def _parse_json(reply: str) -> dict[str, Any]:
    """The first JSON object in a reply, ignoring <think> blocks and code fences."""
    text = re.sub(r"(?s)<think>.*?</think>", "", reply)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object in the reply")


def _parse_action(reply: str) -> dict[str, Any]:
    text = re.sub(r"(?s)<think>.*?</think>", "", reply)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            action, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(action, dict) and "action" in action:
            break
    else:
        raise ValueError("no JSON object with an 'action' field")

    if action["action"] == "query":
        if not isinstance(action.get("sql"), str) or not action["sql"].strip():
            raise ValueError("query action needs a non-empty 'sql' string")
        return action
    if action["action"] == "answer":
        if not isinstance(action.get("answer"), str) or not action["answer"].strip():
            raise ValueError("answer action needs a non-empty 'answer' string")
        return action
    raise ValueError(f"unknown action {action['action']!r}")


def _run_query(run_id: str, record: QueryRecord, action: str = "query") -> None:
    """Run record.sql and fill in its rows or error."""
    started = time.perf_counter()
    if not re.match(r"(?is)\s*(select|with)\b", record.sql):
        record.error = "Only SELECT or WITH queries are allowed."
    else:
        try:
            result = run_sql(record.sql)
            record.headers, record.rows = result["headers"], result["data"]
        except ZetarisError as error:
            record.error = str(error)
    extra = {"factor": record.factor} if record.factor else {}
    trace(
        run_id, AGENT_NAME, action, "error" if record.error else "ok",
        sql=record.sql, rows_returned=None if record.error else len(record.rows),
        duration_ms=_ms(started), query_id=record.query_id, error=record.error, **extra,
    )


def _format_result(record: QueryRecord, remaining: int | None = None) -> str:
    payload: dict[str, Any] = {"query_id": record.query_id}
    if remaining is not None:
        payload["queries_left"] = remaining
    if record.error:
        payload["error"] = record.error
    else:
        payload |= {
            "headers": record.headers,
            "rows": record.rows[:ROWS_SHOWN_TO_MODEL],
            "row_count": len(record.rows),
            "truncated": len(record.rows) > ROWS_SHOWN_TO_MODEL,
        }
    return json.dumps(payload, ensure_ascii=False)


def _build_result(
    run_id: str, question: str, context: str, action: dict[str, Any], queries: list[QueryRecord], plan: Plan
) -> AnalystResult:
    by_id = {q.query_id: q for q in queries if not q.error}

    def evidence_for(item: dict[str, Any]) -> list[Evidence]:
        ids = [i for i in item.get("query_ids") or [] if isinstance(i, int) and i in by_id]
        return [Evidence(i, by_id[i].sql, by_id[i].headers, by_id[i].rows) for i in ids]

    def drop(kind: str, label: str) -> None:
        trace(run_id, AGENT_NAME, f"{kind}_dropped", "warning", reason="no successful query cited", text=label)

    claims = []
    for item in action.get("claims") or []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        evidence = evidence_for(item)
        if evidence:
            claims.append(Claim(round_numbers(item["text"]), evidence))
        else:
            drop("claim", item["text"])

    factors = []
    for item in action.get("factors") or []:
        if not isinstance(item, dict) or not isinstance(item.get("factor"), str):
            continue
        support = str(item.get("support", "")).lower()
        if support not in SUPPORT_LEVELS:
            support = "not supported"
        evidence = evidence_for(item)
        # A supported factor needs evidence; one ruled out may cite queries or none.
        if evidence or support == "not supported":
            factors.append(Factor(item["factor"], support, round_numbers(str(item.get("summary", ""))), evidence))
        else:
            drop("factor", item["factor"])

    planned_factors = {q.factor for q in plan.queries if q.factor in factor_queries.WHY_FACTORS}
    missing = [f for f in factor_queries.WHY_FACTORS if f in planned_factors and not any(_same_factor(f, x.factor) for x in factors)]
    if missing:
        trace(run_id, AGENT_NAME, "factors_missing", "warning", factors=missing)

    correction = action.get("premise_correction")
    if isinstance(correction, str) and correction.strip():
        correction = round_numbers(correction)
    else:
        # The data contradicts the question; correct it even if the model did not.
        correction = plan.premise_note()
        if correction:
            trace(run_id, AGENT_NAME, "premise_correction", "fallback", reason="model left it empty")
    result = AnalystResult(
        run_id=run_id,
        question=question,
        answer=round_numbers(action["answer"]),
        premise_correction=correction,
        claims=claims,
        factors=factors,
        not_measurable=[str(x) for x in action.get("not_measurable") or []],
        queries=queries,
        season_context=context,
        question_type=plan.question_type,
        asked=plan.corrected_question(question),
    )
    trace(
        run_id, AGENT_NAME, "answer", "ok",
        claims=len(claims), factors=len(factors), queries=len(queries),
        premise_corrected=result.premise_correction is not None,
    )
    return result


def _same_factor(planned: str, given: str) -> bool:
    """Loose match of the model's factor name to a planned factor ("Opportunity" ~ "opportunity: snaps")."""
    return planned.lower()[:5] in given.lower()


def round_numbers(text: str) -> str:
    """Round any decimal with more than one place to one place (safety net for the rule)."""
    return re.sub(
        r"(?<![\w.])(-?\d+\.\d{2,})(?![\w.]|\.\d)",
        lambda m: f"{float(m.group(1)):.1f}",
        text,
    )


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
