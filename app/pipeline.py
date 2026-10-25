"""One question end to end: the Analyst answers, the Critic checks, the verdict is revised.

    analyst.analyze -> critic.critique -> (needs_revision) analyst.revise_verdict -> critique ...

At most MAX_ROUNDS critiques, so at most MAX_ROUNDS - 1 revisions; only the verdict
step is rerun, never the factor agents. The whole run fits in RUN_BUDGET seconds:
the Analyst keeps its own budget and the critic loop gets whatever is left.
If issues remain after the last round, the answer says so in a closing critic note.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from app.agents import analyst, critic
from app.agents.analyst import AnalystResult
from app.agents.critic import Critique
from app.trace import new_run_id, trace

RUN_BUDGET = 300
MAX_ROUNDS = 3
REVISE_RESERVE = 45  # kept back from a review that may be followed by a revision


@dataclass
class PipelineResult:
    result: AnalystResult  # the final, critic-checked answer is result.answer
    first_answer: str  # the Analyst's answer before the critic saw it
    critiques: list[Critique]
    approved: bool
    seconds: float


def answer(question: str, run_id: str | None = None, model_review: bool | None = None) -> PipelineResult:
    """Raises analyst.AnalystError if the Analyst cannot answer at all.

    model_review (default: CRITIC_MODEL_REVIEW env, on) adds the Critic's model call
    to its code checks.
    """
    run_id = run_id or new_run_id()
    started = time.perf_counter()
    result = analyst.analyze(question, run_id=run_id)
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
        analyst.revise_verdict(result, [_for_prompt(i) for i in found.blocking], deadline, round)

    approved = not critiques[-1].blocking
    if not approved:
        result.answer += " Critic note: " + " ".join(i.reason for i in critiques[-1].blocking)
    seconds = time.perf_counter() - started
    trace(run_id, critic.AGENT_NAME, "final", "approved" if approved else "unresolved",
          rounds=len(critiques), revisions=len(critiques) - 1, duration_ms=round_ms(seconds))
    return PipelineResult(result, first_answer, critiques, approved, seconds)


def _for_prompt(issue: critic.Issue) -> str:
    claim = issue.claim if len(issue.claim) <= 200 else issue.claim[:200] + "..."
    return f'{issue.check}: "{claim}" -> {issue.reason}'


def round_ms(seconds: float) -> int:
    return round(seconds * 1000)
