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
from app.agents import directions, factor_queries, planner
from app.agents.memory import UserContext, scoring_in, user_context_from_dict
from app.trace import new_run_id, trace

AGENT_NAME = "analyst"
MAX_QUERIES = 6
MAX_REPAIRS = 1
MAX_TURNS = MAX_QUERIES + 4
ROWS_SHOWN_TO_MODEL = 50
# Nemotron spends its whole token budget thinking unless this is off. Nightshift 1.2.7
# forwards it (1.2.1 did not, checked 2026-10-22, and still works, only slower).
MODEL_PARAMS = {"temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False}}
# Room for the JSON, and for the thinking Nightshift 1.2.1 does anyway.
FACTOR_MAX_TOKENS = 4096
VERDICT_MAX_TOKENS = 4096
REVISE_MAX_TOKENS = 8192
# Time limits (seconds). Each model request times out on its own. After the queries
# finish, the factor agents share one window: what is left of TOTAL_BUDGET minus the
# verdict's reserve, capped at FACTOR_WINDOW, but never under MIN_FACTOR_WINDOW, so
# slow live queries do not squeeze it. The verdict call then gets what is left of
# TOTAL_BUDGET, but never under VERDICT_RESERVE. With thinking off (Nightshift 1.2.7) a
# factor call took 0.4-1.5s, a first verdict up to 46s and a review up to 34s (2026-10-25).
CALL_TIMEOUT = 60  # the first verdict
FACTOR_TIMEOUT = 10
CLASSIFY_TIMEOUT = planner.TIMEOUT
REVISE_TIMEOUT = 65  # the critic's revision call; the run budget (pipeline.RUN_BUDGET) still caps it
TOTAL_BUDGET = 150
FACTOR_WINDOW = 15
MIN_FACTOR_WINDOW = 10
VERDICT_RESERVE = 45
MIN_RETRY_SECONDS = 20  # a repair retry needs this long (or the call's own limit, if shorter) to be worth starting
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
facts, at most 1 decimal place. If a change matters, say in which week it started.
Use a position label like WR1 or TE1 only with the player's own position from the facts."""

COMPARE_FACTOR_PROMPT = """\
You compare two players on one factor, for a fantasy football manager choosing which
one to start, from facts computed from nflverse data. Reply with only this JSON:
{"favours": "<the full name of the player this factor favours, or even>",
 "support": "strong" | "moderate" | "weak" | "not supported",
 "summary": "<one sentence with both players' numbers from the facts>"}
support: how decisively this factor favours that player ("not supported" when even).
Use only numbers in the facts, at most 1 decimal place, and write percentages with %.
Use a position label like WR1 or TE1 only with the player's own position from the facts."""

VERDICT_PROMPT = """\
You write the verdict for a fantasy football manager from factors already rated
against nflverse data. Reply with only this JSON:
{"verdict": "<short action phrase, e.g. Pick up Deebo Samuel / Start Christian Watson / Hold Mike Evans>",
 "why": "<2-3 complete sentences>"}
verdict starts with one of: Pick up, Add, Start, Sit, Bench, Hold, Drop, Stash.
Never pick up or start the player the question says is out or missing time.
For a compare question (two players, start which one?), verdict is "Start <A> over <B>",
naming exactly one of the two to start, and "why" quotes the deciding numbers for both
players; follow the head-to-head factors, or say why not.
For a replacement question (who takes over if a player is out), verdict names the
fantasy pick, backed by target share; the answer then opens with who is next on the
depth chart, written by the system ("Deebo Samuel is next at WR on the depth chart, but
the target share points to George Kittle (24.9%), so for fantasy: pick up George
Kittle"), so do not repeat the depth chart in "why".
In "why", lead with the most supported factors and their numbers; use only numbers
given, at most 1 decimal place. If a premise check is given, answer the corrected
question. If a user context is given, quote points in its scoring and never recommend
picking up a player already on its roster. Never recommend a player the facts have no
data for. Never start a player on bye that week; if the game was already played, say so.
Use a position label like WR1 or TE1 only with the player's own position. Do not add a
disclaimer."""
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


class NeedsClarification(AnalystError):
    """The question names a player by a last name that matches nobody, or several players
    equally: the reply asks which player is meant instead of guessing."""

    def __init__(self, message: str, options: list[factor_queries.Player] | None = None) -> None:
        super().__init__(message)
        self.options = options or []


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
    favours: str | None = None  # compare questions: the player this factor favours, or "even"


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
    players: list[factor_queries.Player] = field(default_factory=list)  # both players of a compare question
    name_note: str | None = None  # last names resolved from the rosters: "Bowers = Brock Bowers, LV TE."

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
    players: list[factor_queries.Player] = field(default_factory=list)  # compare: both players, question order
    bye_claims: list[str] = field(default_factory=list)  # "Jalen Hurts is not on bye in week 7: PHI plays DAL."
    last_names: list[factor_queries.LastName] = field(default_factory=list)  # resolved from a last name only

    def name_note(self) -> str | None:
        """ "Bowers = Brock Bowers, LV TE." for each player the question named by last name."""
        notes = [n.note() for n in self.last_names if n.player]
        return " ".join(notes) or None

    def corrected_question(self, question: str) -> str:
        if not (self.player and self.wrong_teams) or len(self.players) > 1:
            return question  # with two players the wrong team cannot be pinned on one of them
        return factor_queries.corrected_question(question, self.wrong_teams, self.player.team,
                                                 tuple(p.name for p in (self.player, *self.players)))

    def premise_note(self) -> str | None:
        note = self._team_note()
        return " ".join(n for n in (note, *self.bye_claims) if n) or None

    def _team_note(self) -> str | None:
        if not (self.player and self.wrong_teams):
            return None
        if len(self.players) > 1:
            on = " and ".join(f"{p.name} is on {p.team}" for p in self.players)
            return f"{on} in the data (rosters, week {self.player.roster_week}), not {' or '.join(self.wrong_teams)}."
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
    # Without league memory, the question's own scoring ("Bijan or Lamb half ppr") still counts.
    stated = None if memory else scoring_in(question)
    scoring = factor_queries.SCORINGS[memory.scoring if memory else stated or "ppr"]
    plan = _run_plan(run_id, factor_queries.with_nicknames(question), player_name, question_type, season, week,
                     scoring, memory, player_names=route.player_names)

    if free_sql:
        return _sql_loop(run_id, question, context, plan)
    topic = factor_queries.unsupported_topic(question) if plan.question_type == "unsupported" else None
    if plan.player is None and topic:
        trace(run_id, AGENT_NAME, "answer", "unsupported", topic=topic)
        raise AnalystError(factor_queries.unsupported_message(topic) + (
            "" if topic == "kickers or defenses" else " Name the players to get their week-by-week numbers."))
    if plan.player is None:
        trace(run_id, AGENT_NAME, "answer", "error", reason="no player found")
        suggestion = _closest_name(run_id, question, season) if season else None
        if suggestion:  # a misspelt name ("Justin Jeffersen")
            raise AnalystError("Could not find the NFL player this question is about in this season's rosters. "
                               f"Did you mean {suggestion}? Name the player in full.")
        other = _other_position(run_id, question, season) if season else None
        if other:  # QA: "Should I start Harrison Butker?" got "I answer questions about specific players"
            article = "an" if other[1][:1] in "AEFHILMNORSX" else "a"  # "an OL", "an LB", "a K"
            raise AnalystError(f"{other[0]} is {article} {other[1]} ({other[2]}). I cover QBs, RBs, WRs and TEs only, "
                               "so I can't rate kickers, defenders or linemen.")
        raise AnalystError(NO_PLAYER_MESSAGE)

    window = _factor_window(started + TOTAL_BUDGET - time.perf_counter())
    # The agents get the question with its wrong premise already corrected from the data.
    asked = plan.corrected_question(question)
    factors = _rate_factors(run_id, asked, plan, window=window)
    deadline = max(started + TOTAL_BUDGET, time.perf_counter() + VERDICT_RESERVE)
    out = factor_queries.says_out(question, plan.player.name)
    facts = _verdict_facts(asked, context, plan.premise_note(), plan.queries, factors, memory, plan.name_note(),
                           question_type=plan.question_type, player=plan.player, players=plan.players, out=out)
    verdict = _verdict(run_id, plan.question_type, plan.player, facts, plan.queries, factors, deadline=deadline,
                       memory=memory, out=out, players=plan.players, name_note=plan.name_note(), question=question)
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
    players = [factor_queries.Player(**p) for p in data.get("players") or []]
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
        "players": players,
    })


def _factor_window(left: float) -> float:
    """The factor agents' shared window, given the seconds left of TOTAL_BUDGET once the queries are done."""
    return max(MIN_FACTOR_WINDOW, min(FACTOR_WINDOW, left - VERDICT_RESERVE))


def revise_verdict(
    result: AnalystResult, issues: list[str], deadline: float, round: int, rule_based: str | None = None
) -> None:
    """Rerun only the verdict step after critic round `round`; updates result.

    The prompt is the verdict's facts plus the critic's issues as rules to follow
    (critic.as_rule), without the previous answer: shown its previous answer and asked to
    fix it, Nemotron reasons for 6,000-8,000 tokens even with thinking off (2026-10-25).
    The factor agents are not rerun. If the call fails, the rule-based verdict is used;
    with rule_based (the reason, e.g. "the model recommended a rostered player twice")
    the model is not called at all.
    """
    if result.player is None:  # free-SQL answers have no planned facts to re-verdict from
        trace(result.run_id, AGENT_NAME, "revise", "skipped", target_agent="critic", round=round,
              reason="no planned factor queries")
        return
    out = factor_queries.says_out(result.question, result.player.name)
    facts = _verdict_facts(
        result.asked or result.question, result.season_context, result.premise_correction,
        result.queries, result.factors, result.user_context, result.name_note,
        question_type=result.question_type, player=result.player, players=result.players, out=out,
    )
    answer, by = _verdict(
        result.run_id, result.question_type, result.player, facts, result.queries, result.factors,
        deadline=deadline, revision=issues, memory=result.user_context, out=out, players=result.players,
        name_note=result.name_note, round=round, rule_based=rule_based, question=result.question,
    )
    result.answer, result.verdict_by = answer, by
    trace(result.run_id, AGENT_NAME, "revise", "ok" if by == "model" else "fallback", target_agent="critic",
          round=round, verdict_by=by, issues=len(issues), **({"reason": rule_based} if rule_based else {}))


def _player_line(plan: Plan) -> str:
    line = _lookup_summary(plan.queries)
    if plan.name_note():
        line += f" Named by last name: {plan.name_note()}"
    note = plan.premise_note()
    return f"{line} Premise check: {note} Answer for the team in the data." if note else line


# A question that names no player ("Who should I pick up at RB?", "Best waiver add this week?").
NO_PLAYER_MESSAGE = (
    "I answer questions about specific players. Try: 'Should I start Jared Goff?', 'Pickens or Olave?', "
    "'Who replaces McCaffrey if he's out?', 'Is Kyle Monangai playing?'"
)


def _closest_name(run_id: str, question: str, season: int) -> str | None:
    """A "did you mean" for a misspelled name (QA run: "Justin Jeffersen" got no suggestion)."""
    record = QueryRecord(1, "skill-player names this season, for a suggestion", factor_queries.names_sql(season))
    _run_query(run_id, record, action="name_suggestion")
    if record.error:
        return None
    return factor_queries.closest_name(question, [str(r[0]) for r in record.rows])


def _other_position(run_id: str, question: str, season: int) -> tuple[str, str, str] | None:
    """(name, position, team) of a non-skill player the question names in full, if any."""
    names = ", ".join(factor_queries._quote(c) for c in dict.fromkeys(
        factor_queries.name_key(c) for c in factor_queries.name_candidates(question)) if c)
    if not names:
        return None
    positions = ", ".join(factor_queries._quote(p) for p in factor_queries.SKILL_POSITIONS)
    sql = ("SELECT full_name, position, team FROM NFLVERSE.rosters "
           f"WHERE season = {season} AND {factor_queries.SQL_NAME.format(col='full_name')} IN ({names}) "
           f"AND position NOT IN ({positions}) ORDER BY week DESC LIMIT 1")
    record = QueryRecord(1, "non-skill players the question names", sql)
    _run_query(run_id, record, action="name_suggestion")
    return tuple(str(x) for x in record.rows[0][:3]) if not record.error and record.rows else None


def _lookup_summary(queries: list[QueryRecord]) -> str:
    """The players found by full name; when none were, the last-name matches."""
    lookups = [q for q in queries if q.factor in ("Player lookup", "Last-name lookup") and not q.error and q.rows]
    return _summary(lookups[0]) if lookups else _summary(queries[0])


def _summary(record: QueryRecord) -> str:
    if record.error:
        return "Query failed; no data."
    return " ".join(factor_queries.summarize(record.factor or "", record.headers, record.rows))


def _evidence(record: QueryRecord) -> list[Evidence]:
    return [] if record.error else [Evidence(record.query_id, record.sql, record.headers, record.rows)]


def _rate_factors(run_id: str, question: str, plan: Plan, window: float) -> list[Factor]:
    """One factor agent (model call) per factor, all in parallel, sharing one time window.

    Each agent gets the factor's directions, computed in code (directions.py: who leads,
    what rose or fell, which matchup is easier). A factor whose agent fails after its
    retry, or has no reply when the window closes, is rated with the fixed rules in
    factor_queries.rule_rating; so is one whose summary contradicts those directions,
    which then shows the code summary, so a reversed factor is never shown.
    Returns the factors ranked from most to least supported.
    """
    rated = [q for q in plan.queries if q.factor in factor_queries.RATED_FACTORS]
    player_line = _player_line(plan)
    positions = factor_queries.known_positions([(q.headers, q.rows) for q in plan.queries if not q.error])
    head_to_head = len(plan.players) >= 2
    results = {q.factor: (q.headers, q.rows) for q in plan.queries if not q.error}
    subject = plan.player.name if plan.player else None
    found = {q.factor: directions.directions(q.factor, results, subject) for q in rated if not q.error}
    # Numbers a factor summary may quote: the question, the rows and the facts computed from them.
    allowed = directions.numbers_in([question, player_line, *(v for q in plan.queries for row in q.rows for v in row
                                                             if v is not None),
                                     *(line for q in plan.queries if not q.error
                                       for line in factor_queries.summarize(q.factor or "", q.headers, q.rows)),
                                     *(line for d in found.values() for line in d.lines)])
    replies: dict[int, dict[str, Any] | Exception] = {}
    deadline = time.perf_counter() + window

    def work(record: QueryRecord) -> None:
        try:
            replies[record.query_id] = _factor_agent(run_id, question, player_line, record, deadline, plan.players,
                                                     positions, found[record.factor].lines)
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

    factors = []
    for q in rated:
        agent = f"factor_agent:{q.factor}"
        reply = replies.get(q.query_id)
        wrong = []
        if isinstance(reply, dict):
            summary = round_numbers(reply["summary"])
            wrong = directions.contradictions(summary, found[q.factor], reply.get("favours"))
            # "4.4 more half-PPR points per game (17.1 vs 13.1)": a number not in its rows (smoke run).
            wrong += [f"{value} is not in the rows" for _, value in directions.unknown_numbers(summary, allowed)]
            if not wrong:
                factor = Factor(q.factor, reply["support"], summary, _evidence(q), favours=reply.get("favours"))
                trace(run_id, agent, "rate_factor", "ok", rated_by="model", support=factor.support,
                      favours=factor.favours, query_id=q.query_id)
                factors.append(factor)
                continue
        if wrong:
            reason = "the model summary contradicts the numbers: " + "; ".join(wrong)
        else:
            reason = "query failed" if q.error else (str(reply) if reply else f"no reply within {window:.0f}s")
        favours = None
        if head_to_head and q.factor in factor_queries.COMPARE_FACTORS:
            favours, support, rule = factor_queries.compare_rating(q.factor, results)
        else:
            own = plan.player.name if plan.player and plan.question_type in ("start_sit", "waiver") else None
            support, rule = factor_queries.rule_rating(q.factor, results, own)
        if wrong:
            rule += f"; model summary replaced: {'; '.join(wrong)}"
        factor = Factor(q.factor, support, _summary(q), _evidence(q), rated_by="rule-based", rule=rule,
                        favours=favours)
        trace(run_id, agent, "rate_factor", "replaced" if wrong else "fallback", rated_by="rule-based",
              support=support, favours=favours, rule=rule, query_id=q.query_id, reason=reason[:300],
              **({"model_summary": reply["summary"][:300]} if wrong else {}))
        factors.append(factor)
    return sorted(factors, key=lambda f: SUPPORT_LEVELS.index(f.support))


def _factor_agent(
    run_id: str, question: str, player_line: str, record: QueryRecord, deadline: float,
    players: list[factor_queries.Player] | None = None, positions: dict[str, str] | None = None,
    direction_lines: list[str] | None = None,
) -> dict[str, Any]:
    """Rate one factor; for a compare question, head-to-head: which of the two players it favours."""
    facts = "\n".join(f"- {line}" for line in factor_queries.summarize(record.factor or "", record.headers, record.rows))
    if direction_lines:
        facts += "\nDirections (computed in code; your summary and rating must agree with them):\n" + "\n".join(
            f"- {line}" for line in direction_lines)
    head_to_head = record.factor in factor_queries.COMPARE_FACTORS and players and len(players) >= 2
    label = "Players" if head_to_head else "Player"
    messages = [
        {"role": "system", "content": COMPARE_FACTOR_PROMPT if head_to_head else FACTOR_PROMPT},
        {"role": "user", "content": f"Question: {question}\n{label}: {player_line}\nFactor: {record.factor}\nFacts:\n{facts}"},
    ]
    check = _check_head_to_head([p.name for p in players]) if head_to_head else _check_rating
    check = _with_position_check(check, positions or {})
    return _ask_json(
        run_id, "factor", messages, FACTOR_MAX_TOKENS, check,
        agent_name=f"factor_agent:{record.factor}", timeout=FACTOR_TIMEOUT, deadline=deadline,
    )


def _check_head_to_head(names: list[str]):
    """A rating check that also needs "favours": one of the two players' names, or "even"."""
    def check(reply: dict[str, Any]) -> None:
        _check_rating(reply)
        favours = str(reply.get("favours", "")).strip()
        if favours.lower() == factor_queries.EVEN:
            reply["favours"] = factor_queries.EVEN
            return
        match = next((n for n in names if factor_queries.same_player(n, favours)), None)
        if match is None:
            raise ValueError(f"'favours' must be one of: {', '.join(names)}, or even")
        reply["favours"] = match
    return check


def _with_position_check(check, positions: dict[str, str]):
    """A rating check that also rejects a "WR1"-style label on a player of another position."""
    def checked(reply: dict[str, Any]) -> None:
        check(reply)
        for _, label, name, pos in factor_queries.position_label_problems(str(reply.get("summary", "")), positions):
            raise ValueError(f"'{label}' is wrong for {name}, who is a {pos}; use {pos} labels for him")
    return checked


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
    revision: list[str] | None = None, memory: UserContext | None = None, out: bool = False,
    players: list[factor_queries.Player] | None = None, name_note: str | None = None, round: int | None = None,
    rule_based: str | None = None, question: str = "",
) -> tuple[str, str]:
    """(answer, verdict_by): the model's verdict, or the code rules' if that call fails.

    revision is the critic's issues as rules when critic round `round` sent the answer back.
    rule_based (a reason) skips the model: the code rules give the verdict.
    The rule-based stand-in skips players already on the user's roster (memory), and
    never names the player when the question says he is out (out).
    """
    note = ""
    results = {q.factor: (q.headers, q.rows) for q in queries if not q.error}
    reply, failed = None, None
    if question_type == "unsupported":  # the model would answer the trade anyway: the code says what it can
        rule_based = "this question type is not supported, so only the week's numbers are given"
    if question_type == "status":  # a lookup in the injury report, not a judgement
        rule_based = "a status question is answered from the injury report"
    if not meterless.configured():
        rule_based = "no model configured (sample mode)"
    if not rule_based:
        try:
            reply = _model_verdict(run_id, facts, deadline, revision)
        except AnalystError as error:
            failed = str(error)
    if reply is not None:
        verdict, why, by = reply["verdict"], reply["why"], "model"
    else:
        ranked = [(f.factor, f.support, f.summary) for f in factors]
        roster = memory.roster_names if memory else ()
        verdict, why = factor_queries.rule_verdict(question_type, player, results, ranked, roster, out=out,
                                                   players=players, question=question,
                                                   favours={f.factor: f.favours for f in factors})
        if rule_based == "no model configured (sample mode)":
            note = "(Rule-based: no model configured (sample mode).)"
        else:
            note = f"(Rule-based verdict: {rule_based or 'the verdict model call failed'}, so fixed thresholds were applied.)"
        by = "rule-based"
        trace(run_id, AGENT_NAME, "verdict", "fallback", rated_by=by, verdict=verdict,
              step="revise" if revision else "verdict", reason=(rule_based or failed or "")[:300],
              **({"round": round} if revision else {}))
    lead = factor_queries.replacement_lead(player, results, verdict, question) if question_type == "replacement" else None
    answer = _with_name_note(_compose(question_type, verdict, why, note, lead), name_note)
    return round_numbers(_with_variant_note(answer, question)), by


# Scoring rules the queries do not model (QA run): said, not silently ignored.
SCORING_VARIANTS = (
    (re.compile(r"\bte[- ]?prem(?:ium)?\b|\btep\b", re.I), "TE premium"),
    (re.compile(r"\b6[- ]?(?:pt|point)s?\b.{0,20}\b(?:pass(?:ing)?|qb)\b|\b6[- ]?(?:pt|point)\s+pass", re.I),
     "6-point passing touchdowns"),
    (re.compile(r"\bsuper[- ]?flex\b|\bsflex\b", re.I), "superflex"),
)


def _with_variant_note(answer: str, question: str) -> str:
    found = [name for pattern, name in SCORING_VARIANTS if pattern.search(question or "")]
    if not found:
        return answer
    note = f"Note: {' and '.join(found)} {'is' if len(found) == 1 else 'are'} not modelled; this answer uses standard scoring rules for {'it' if len(found) == 1 else 'them'}."
    body, sep, tail = answer.partition("\n\n" + DISCLAIMER)
    return f"{body} {note}{sep}{tail}"


def _with_name_note(answer: str, note: str | None) -> str:
    """Say which player a last name resolved to, right after the first sentence:
    "Start Trey McBride over Brock Bowers. Bowers = Brock Bowers, LV TE. ..."."""
    if not note or note in answer:
        return answer
    first = (factor_queries.sentences(answer) or [answer])[0]
    at = answer.find(first) + len(first)
    rest = answer[at:].strip()
    return f"{answer[:at]} {note}" + (f" {rest}" if rest else "")


def _compose(question_type: str, verdict: str, why: str, note: str = "", lead: str | None = None) -> str:
    """Join verdict and why with sentence case and one period each.

    A "why" question gets the explanation first and the action last
    ("He ... Verdict: hold Christian Watson."); a replacement question opens with lead
    (the depth chart's answer, then "so for fantasy: <verdict>"); every other type leads
    with the action.
    """
    verdict, why = verdict.strip().rstrip(".").strip(), why.strip()
    why = why[:1].upper() + why[1:]
    if why and not why.endswith((".", "!", "?")):
        why += "."
    if question_type == "why" and why:
        text = f"{why} Verdict: {verdict[:1].lower() + verdict[1:]}."
    elif lead:
        text = f"{lead} {why}" if why else lead
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
    memory: UserContext | None = None, name_note: str | None = None, question_type: str = "other",
    player: factor_queries.Player | None = None, players: list[factor_queries.Player] | None = None,
    out: bool = False,
) -> list[str]:
    """The verdict prompt's facts: the rated factors with their directions, then hard
    rules computed in code (who is out or rostered, the compare leaders, positions)."""
    results = {q.factor: (q.headers, q.rows) for q in queries if not q.error}
    lines = [context]
    if memory and memory.prompt_block():
        lines.append(memory.prompt_block())
    lines.append(f"Question: {question}")
    if name_note:
        lines.append(f"Named by last name (from the rosters): {name_note}")
    if premise_note:
        lines.append(f"Premise check: {premise_note}")
    lines.append(f"Player: {_lookup_summary(queries)}")
    status = next((q for q in queries if q.factor == "Status"), None)
    if status:
        lines.append(f"Injury status: {_summary(status)}")
    lines.append("Rated factors (most supported first):")
    for f in factors:
        rating = f.support if not f.favours else (
            "even" if f.favours == factor_queries.EVEN else f"favours {f.favours}, {f.support}")
        lines.append(f"- {f.factor} [{rating}]: {f.summary}")
        if f.favours:  # head-to-head: the verdict needs both players' numbers, not only the agent's sentence
            lines += [f"    {line}" for line in factor_queries.summarize(f.factor, *_rows_of(queries, f.factor))]
        if f.factor in results:
            lines += [f"    {line}" for line in directions.directions(f.factor, results, player and player.name).lines]
    rules = _hard_rules(question_type, player, players or [], results, memory, out, "\n".join(lines), question)
    if rules:
        lines.append("Hard rules (computed in code; follow every one):")
        lines += [f"- {rule}" for rule in rules]
    return lines


def _hard_rules(
    question_type: str, player: factor_queries.Player | None, players: list[factor_queries.Player],
    results: dict[str, tuple[list[str], list[list]]], memory: UserContext | None, out: bool, facts: str,
    question: str = "",
) -> list[str]:
    rules = []
    if player and (out or question_type == "replacement"):
        rules.append(f"Never recommend {player.name}: the question says he is out.")
    roster = list(memory.roster_names) if memory else []
    if roster:
        rules.append(f"Never recommend picking up {', '.join(roster)}: already on the user's roster.")
    if question_type == "replacement":
        rules.append('The verdict is "Pick up <one player>": who to add for fantasy, not a start/sit choice.')
    # Every compared player the question says is out, not only the first-named one (QA).
    away = factor_queries.unavailable(results, question if question_type == "compare" else "")
    for name, why in away.items():
        if question_type == "compare" and len(players) >= 2:
            others = [p.name for p in players if not any(factor_queries.same_player(p.name, n) for n in away)]
            if others:
                rules.append(f"{name} {why}: never start him; start one of {', '.join(others)}.")
            else:
                rules.append(f"{name} {why}: none of the players can play, so the verdict is \"Sit\" for all of them.")
        elif question_type == "start_sit":
            rules.append(f"He {why}: Sit {name}.")
    if player and (question_type == "replacement" or (out and question_type in ("start_sit", "waiver"))):
        rules += _backed_pick(player, results, tuple(roster), question)
    elif player and question_type != "compare":
        rules.append(f'The verdict names its player ("Hold {player.name}", "Start {player.name}"), never a bare '
                     '"Hold" or "Start".')
    if question_type == "compare" and len(players) >= 2:
        rules += _compare_leaders([p.name for p in players], results)
    positions = factor_queries.known_positions(list(results.values()))
    if player and player.position:
        positions.setdefault(player.name, player.position)
    for p in players:
        if p.position:
            positions.setdefault(p.name, p.position)
    named = [f"{n} {pos}" for n, pos in positions.items()
             if (last := factor_queries.name_key(n).split()[-1:]) and re.search(rf"\b{re.escape(last[0])}\b", facts, re.I)]
    if named:
        rules.append("Positions (from the rosters): " + "; ".join(named[:12])
                     + ". Use a label like WR1 or TE1 only with the player's own position.")
    return rules


def _backed_pick(
    player: factor_queries.Player, results: dict[str, tuple[list[str], list[list]]], roster: tuple[str, ...],
    question: str = "",
) -> list[str]:
    """The stand-in the code rules pick (factor_queries._next_up), as critic check (a) tests it:
    "The usage numbers back Christian McCaffrey (22.8%) among players not on the roster: recommend him."."""
    name, reason = factor_queries._next_up(player, results, roster, question)
    if not name:
        return []
    backs = f"The numbers back {name}: {factor_queries._first_sentence(reason)}"
    return [f'{backs}. Recommend him ("Pick up {name}"), a {player.position} like {player.name}. '
            "The answer may still say who is next on the depth chart."]


def _compare_leaders(names: list[str], results: dict[str, tuple[list[str], list[list]]]) -> list[str]:
    """Who leads on points per game and in the later weeks, as critic check (g) compare tests them."""
    usage, trend = results.get("Team usage share", ([], [])), results.get("Recent trend", ([], []))
    label = factor_queries.scoring_of(usage[0]).label
    get = lambda values, n: values.get(factor_queries._row_name(n, values))
    out = []
    ppg = factor_queries._per_game_by_player(usage) if usage[1] else {}
    late = factor_queries.h2h_values("Recent trend", *trend) if trend[1] else {}
    if len(names) > 2:  # rank them all, then the top two as for a pair
        ranked = sorted(names, key=lambda n: -(get(ppg, n) if get(ppg, n) is not None else -1))
        listing = ", ".join(f"{n} {factor_queries._fmt(get(ppg, n))}" for n in ranked)
        return [f"{label[:1].upper() + label[1:]} points per game: {listing}.", *_compare_leaders(ranked[:2], results)]
    a, b = names
    leaders = []
    for values, what in ((ppg, f"{label} points per game"), (late, f"{label} points per game in the later weeks")):
        va, vb = get(values, a), get(values, b)
        if va is None or vb is None:
            continue
        lead = a if va - vb >= factor_queries.PPG_MARGIN else b if vb - va >= factor_queries.PPG_MARGIN else None
        leaders.append(lead)
        out.append(f"{what[:1].upper() + what[1:]}: {a} {factor_queries._fmt(va)} vs {b} {factor_queries._fmt(vb)}: "
                   + (f"{lead} leads." if lead else "level."))
    if len(leaders) == 2 and leaders[0] and leaders[0] == leaders[1]:
        out.append(f"{leaders[0]} leads on both, so start {leaders[0]}.")
    elif out:
        out.append("If one player leads on both, start him; otherwise start the points-per-game leader, or say "
                   "why the later weeks or the matchup decide it.")
    return out


def _rows_of(queries: list[QueryRecord], factor: str) -> tuple[list[str], list[list[Any]]]:
    q = next((q for q in queries if q.factor == factor and not q.error), None)
    return (q.headers, q.rows) if q else ([], [])


def _model_verdict(run_id: str, facts: list[str], deadline: float, revision: list[str] | None = None) -> dict[str, Any]:
    content = "\n".join(facts)
    if revision:
        content += "\n\nRules from a check against the data (follow every one):\n" + "\n".join(
            f"- {rule}" for rule in revision)
    messages = [
        {"role": "system", "content": VERDICT_PROMPT},
        {"role": "user", "content": content},
    ]
    return _ask_json(
        run_id, "revise" if revision else "verdict", messages,
        REVISE_MAX_TOKENS if revision else VERDICT_MAX_TOKENS, _check_verdict,
        timeout=REVISE_TIMEOUT if revision else CALL_TIMEOUT, deadline=deadline,
    )


def _assemble(
    run_id: str, question: str, asked: str, context: str, plan: Plan,
    factors: list[Factor], verdict: tuple[str, str], started: float,
) -> AnalystResult:
    """Claims are the code-computed facts of each query that bears on the answer."""
    claims = [
        Claim(_summary(q), _evidence(q))
        for q in plan.queries
        if q.factor in ("Player lookup", "Last-name lookup", "Status") and not q.error and q.rows
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
        players=plan.players,
        name_note=plan.name_note(),
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
    fresh_repair: bool = False,
) -> dict[str, Any]:
    """One model call that must return a JSON object passing check(); one repair retry.

    Each attempt gets at most `timeout` seconds and must end by `deadline`
    (a time.perf_counter() value); a repair is only tried with MIN_RETRY_SECONDS left
    (or `timeout`, if shorter). (Within an attempt, the adapter also retries once on a
    5xx or an empty reply.) The repair normally shows the model its invalid reply;
    fresh_repair sends the original messages again with a short "JSON only" reminder
    instead, because a model shown its own reply can repeat it word for word (the
    critic's review in runs 4e765f424e23 and e7adc890c23c).
    """
    original = list(messages)
    messages = list(messages)
    retry_seconds = MIN_RETRY_SECONDS if timeout is None else min(MIN_RETRY_SECONDS, timeout)
    for repairs in range(MAX_REPAIRS + 1):
        limit = timeout
        if deadline is not None:
            left = deadline - time.perf_counter()
            if left <= 0 or (repairs and left < retry_seconds):
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
            trace(run_id, agent_name, "parse_reply", status, retry_count=repairs + 1, step=step, error=str(error),
                  reply_head=reply[:200])
            if status == "error":
                raise AnalystError(f"Model reply ({step}) was not valid: {error}") from error
            if fresh_repair:
                last = original[-1]
                messages = original[:-1] + [dict(last, content=last["content"] + "\n\nReply with only the JSON object.")]
            else:
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
    memory: UserContext | None = None, player_names: tuple[str, ...] = (),
) -> Plan:
    """Look the player up (the model's name first, then names in the question) and run their factor queries.

    Without a name from the model, a player the question names who is not on the user's
    roster comes first ("my TE is George Kittle. Who replaces Mike Evans?" is about Evans).
    A compare question needs two players (the model's two names, else the first two the
    question names, roster or not); with fewer it is answered as start/sit.
    """
    plan = Plan(question_type=question_type)
    candidates = factor_queries.name_candidates(question)
    named_first = [n.lower() for n in (*player_names, player_name) if n]
    if named_first:
        candidates = [*dict.fromkeys(named_first), *[c for c in candidates if c not in named_first]]
    if season is None or week is None or not candidates:
        return plan

    lookup = QueryRecord(1, "team, position and roster status", factor_queries.lookup_sql(candidates, season))
    lookup.factor = "Player lookup"
    _run_query(run_id, lookup, action="player_lookup")
    if lookup.error:
        return plan
    try:
        players = factor_queries.parse_players(lookup.rows, question)
    except (IndexError, TypeError, ValueError) as error:
        trace(run_id, AGENT_NAME, "player_lookup", "error", error=f"bad lookup rows: {error}")
        return plan
    plan.queries.append(lookup)

    # A choice ("Trey Mcbride or Bowers") may name a player by last name only; a player
    # named as context ("Josh Allen on bye, Goff or Bryce Young?") is not one of the options.
    choice = factor_queries.CHOICE_CUE.search(question) is not None and question_type in (
        "compare", "start_sit", "waiver", "other", "unsupported")
    context = [p for p in players if factor_queries.CONTEXT_AFTER.match(
        question.lower().replace("’", "'"), (factor_queries.name_span(p, question) or (0, -1))[1])]
    if (choice and len(players) - len(context) < 2) or not players:
        players = _last_names(run_id, question, plan, players, season, scoring, choice)
    if not players:
        plan.queries.clear()
        return plan
    all_players = list(players)
    # "Josh Allen on bye, Goff or Bryce Young?": Allen is context, not an option.
    context = factor_queries.context_players(question, players) if question_type not in ("why", "replacement")         and factor_queries.is_choice(question, players) else []
    if context:
        trace(run_id, AGENT_NAME, "compare", "context", players=[p.name for p in context])
        players = [p for p in players if p not in context]
    # Two or more players and a choice cue is a compare, whatever the capitals ("bucky irving
    # or Jonathan Taylor", "Gibbs, Achane"; QA run). An unsupported question compares them too.
    choice = question_type in ("compare", "start_sit", "waiver", "other", "unsupported") and \
        factor_queries.is_choice(question, players)
    if choice and question_type not in ("compare", "unsupported") and len(players) >= 2:
        trace(run_id, AGENT_NAME, "compare", "ok", reason="a choice between players",
              players=[p.name for p in players], from_type=question_type)
        question_type = plan.question_type = "compare"
    week_named = factor_queries.question_week(question)

    if question_type in ("compare", "unsupported"):
        # Every player the question names, not the first two (QA: "James Cook, Bijan Robinson
        # or CeeDee Lamb?" dropped Lamb, the leader).
        pair = [p for n in player_names for p in players if factor_queries.same_player(p.name, n)]
        pair = _unique([*pair, *players])
        if len(pair) < 2 and question_type == "compare":
            trace(run_id, AGENT_NAME, "compare", "fallback", reason="fewer than two players found",
                  question_type="start_sit")
            question_type = plan.question_type = "start_sit"
        elif len(pair) >= 2:
            plan.players = pair
            plan.player = plan.players[0]
            # A team the question names that is no player's is a wrong premise.
            names = tuple(p.name for p in all_players)
            wrong = [factor_queries.wrong_teams(question, p, names) for p in plan.players]
            plan.wrong_teams = [t for t in wrong[0] if all(t in w for w in wrong[1:])]
            for planned in factor_queries.compare_bundle(plan.players, season, week, scoring, week_named):
                record = QueryRecord(len(plan.queries) + 1, planned.purpose, planned.sql, factor=planned.factor)
                _run_query(run_id, record, action="factor_query")
                plan.queries.append(record)
            _check_opponents_and_byes(run_id, question, plan, all_players, season, week, scoring, week_named)
            return plan

    # "Jalen Hurts is on bye, should I start Jared Goff?" is about Goff (QA run answered Hurts).
    on_bye = _claimed_on_bye(question, players)
    players = [p for p in players if p not in on_bye] or players
    named = [p for p in players if player_name and p.name.lower() == player_name.lower()]
    not_owned = [p for p in players if not (memory and memory.owns(p.name))]
    # "I have Josh Allen and Christian Watson. Should I start Christian Watson?" is about
    # Watson, rostered or not: the player the last sentence names (QA run answered Allen).
    asked = [p for p in factor_queries.order_in_question(players, question)
             if question_type in ("start_sit", "waiver", "unsupported", "status") and factor_queries.name_span(
                 p, factor_queries.sentences(question)[-1] if factor_queries.sentences(question) else question)]
    # "I dropped Deebo Samuel. Who becomes the 49ers' WR1 if Mike Evans is out?" is about Evans:
    # the player the question says is out, or the one after "replaces" (QA, 26 October 2026).
    gone = [p for p in factor_queries.order_in_question(players, question) if question_type == "replacement" and (
        factor_queries.says_out(question, p.name) or factor_queries.replaced_in(question, p))]
    plan.player = (gone or named or asked or not_owned or players)[0]
    plan.wrong_teams = factor_queries.wrong_teams(question, plan.player, tuple(p.name for p in all_players))
    planned_type = "start_sit" if question_type in ("unsupported", "status") else question_type
    for planned in factor_queries.plan(planned_type, plan.player, season, week, scoring, week_named):
        record = QueryRecord(len(plan.queries) + 1, planned.purpose, planned.sql, factor=planned.factor)
        _run_query(run_id, record, action="factor_query")
        plan.queries.append(record)
    _check_opponents_and_byes(run_id, question, plan, all_players, season, week, scoring, week_named)
    return plan


BYE_CLAIM = re.compile(r"\s*(?:'s\s+|\s+is\s+|\s+)?on (?:a |his )?bye\b", re.I)


def _claimed_on_bye(question: str, players: list[factor_queries.Player]) -> list[factor_queries.Player]:
    """The players the question says are on bye ("Hurts on bye", "Jalen Hurts is on bye")."""
    low = question.lower().replace("\u2019", "'")
    return [p for p in players if (s := factor_queries.name_span(p, question)) and BYE_CLAIM.match(low, s[1])]


def _check_opponents_and_byes(
    run_id: str, question: str, plan: Plan, players: list[factor_queries.Player], season: int, week: int,
    scoring: factor_queries.Scoring, week_named: int | None,
) -> None:
    """Drop a "wrong team" that is the player's opponent that week ("Lamb at the Eagles"),
    and correct a false "X is on bye" ("Hurts on bye": PHI plays DAL in week 7). QA run."""
    results = {q.factor: (q.headers, q.rows) for q in plan.queries if not q.error and q.factor}
    t = factor_queries._Rows(*results.get("Next matchup", ([], [])))
    opponents = set(t.text("opponent"))
    # "the Packers' Jahmyr Gibbs" still pins GB on Gibbs when GB is his opponent (QA, 26 Oct 2026).
    plan.wrong_teams = [w for w in plan.wrong_teams if w not in opponents or factor_queries.possessive_team(question, w)]
    claimed = _claimed_on_bye(question, players)
    if not claimed:
        return
    record = QueryRecord(len(plan.queries) + 1, "", factor_queries.matchup_query(
        claimed, season, week, scoring, week_named).sql, factor="Bye check")
    record.purpose = f"{', '.join(p.name for p in claimed)}: is he on bye that week?"
    _run_query(run_id, record, action="factor_query")
    if record.error:
        return
    plan.queries.append(record)
    rows = factor_queries._Rows(record.headers, record.rows)
    for name, team, wk, opp in zip(rows.text("player"), rows.text("team"), rows.text("game_week"), rows.text("opponent")):
        if opp:
            plan.bye_claims.append(f"{name} is not on bye in week {wk}: {team} plays {opp}.")


def _last_names(
    run_id: str, question: str, plan: Plan, players: list[factor_queries.Player], season: int,
    scoring: factor_queries.Scoring, choice: bool,
) -> list[factor_queries.Player]:
    """Look up single words that may be last names ("Bowers") and add the players they
    resolve to, in question order. Raises NeedsClarification when the question still names
    too few players and a last name matched nobody, or several players equally."""
    words = factor_queries.last_name_words(question, players)
    if not words:
        return players
    record = QueryRecord(len(plan.queries) + 1, f"skill players with the last name {', '.join(words)}",
                         factor_queries.last_name_lookup_sql(words, season, scoring), factor="Last-name lookup")
    _run_query(run_id, record, action="player_lookup")
    if record.error:
        return players
    plan.queries.append(record)
    names = factor_queries.resolve_last_names(words, record.headers, record.rows, players)
    plan.last_names = [n for n in names if n.player]
    found = _unique([*players, *(n.player for n in plan.last_names)])
    trace(run_id, AGENT_NAME, "last_names", "ok",
          resolved={n.word: n.player.name for n in plan.last_names},
          rules={n.word: n.rule for n in plan.last_names},
          unresolved={n.word: [p.name for p, _ in n.options] for n in names if not n.player})
    unresolved = [n for n in names if not n.player]
    if unresolved and ((choice and len(found) < 2) or not found):
        message = factor_queries.clarify_message(unresolved)
        trace(run_id, AGENT_NAME, "clarify", "ok", message=message)
        raise NeedsClarification(message, [p for n in unresolved for p, _ in n.options])
    return factor_queries.order_in_question(found, question)


def _unique(players: list[factor_queries.Player]) -> list[factor_queries.Player]:
    seen, out = set(), []
    for p in players:
        if p.player_id not in seen:
            seen.add(p.player_id)
            out.append(p)
    return out


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
