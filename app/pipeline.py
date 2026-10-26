"""One question end to end: the Analyst answers, the Critic checks, the verdict is revised.

    [memory.remember ->] planner.plan -> analyst.analyze -> critic.critique -> (needs_revision) analyst.revise_verdict -> critique ...

With a user_id, league memory (app.agents.memory, on the H-MEM engine) first stores
what the question says about the user's league and roster, then retrieves what is
remembered, so the answer uses their scoring and is written for their roster.

At most MAX_ROUNDS critiques, so at most MAX_ROUNDS - 1 revisions; only the verdict
step is rerun, never the factor agents. If the model's revision still breaks a
code-checked hard rule (critic.HARD_RULES) before the last round, the last revision
does not call the model: it is the rule-based verdict, labelled with the reason, and
the Critic checks it like any other. The whole run fits in RUN_BUDGET seconds:
the Analyst keeps its own budget and the critic loop gets whatever is left.
If issues remain after the last round, the answer says so in a closing critic note.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from app.agents import analyst, critic, memory, planner
from app.agents.analyst import AnalystResult
from app.agents.critic import Critique
from app.trace import new_run_id, trace

RUN_BUDGET = 360  # the Analyst can now run past its 150s when live queries are slow
MAX_ROUNDS = 3
REVISE_RESERVE = 45  # kept back from a review that may be followed by a revision


@dataclass
class PipelineResult:
    result: AnalystResult  # the final, critic-checked answer is result.answer
    first_answer: str  # the Analyst's answer before the critic saw it
    critiques: list[Critique]
    approved: bool
    seconds: float


def answer(
    question: str, run_id: str | None = None, model_review: bool | None = None,
    user_id: str | None = None, session_id: str | None = None,
) -> PipelineResult:
    """Raises analyst.AnalystError if the Analyst cannot answer at all.

    model_review (default: CRITIC_MODEL_REVIEW env, on) adds the Critic's model call
    to its code checks. user_id turns on league memory; session_id (default: the
    run_id) scopes what this session writes.
    """
    run_id = run_id or new_run_id()
    started = time.perf_counter()
    context = memory.remember(user_id, question, run_id, session_id) if user_id else None
    route = planner.plan(run_id, question)
    result = analyst.analyze(question, run_id=run_id, memory=context, route=route)
    return review(result, started, model_review)


def review(result: AnalystResult, started: float | None = None, model_review: bool | None = None) -> PipelineResult:
    """The critique -> revise loop on an Analyst answer; updates result in place.

    started (a time.perf_counter() value) is when the run began, for the RUN_BUDGET.
    """
    started = time.perf_counter() if started is None else started
    deadline = started + RUN_BUDGET
    if model_review is None:
        model_review = os.environ.get("CRITIC_MODEL_REVIEW", "true").strip().lower() not in ("0", "false", "no")
    run_id = result.run_id
    first_answer = result.answer
    critiques: list[Critique] = []
    for round in range(1, MAX_ROUNDS + 1):
        last = round == MAX_ROUNDS
        found = critic.critique(result, round, deadline if last else deadline - REVISE_RESERVE, model_review)
        critiques.append(found)
        if not found.blocking or last:
            break
        rule_based = critic.fallback_reason(critiques) if round >= 2 and round == MAX_ROUNDS - 1 else None
        analyst.revise_verdict(result, [critic.as_rule(i) for i in found.blocking], deadline, round,
                               rule_based=rule_based)

    approved = not critiques[-1].blocking
    if not approved:
        result.answer += " Critic note: " + " ".join(i.reason for i in critiques[-1].blocking)
    seconds = time.perf_counter() - started
    trace(run_id, critic.AGENT_NAME, "final", "approved" if approved else "unresolved",
          rounds=len(critiques), revisions=len(critiques) - 1, duration_ms=round_ms(seconds))
    return PipelineResult(result, first_answer, critiques, approved, seconds)


def round_ms(seconds: float) -> int:
    return round(seconds * 1000)
