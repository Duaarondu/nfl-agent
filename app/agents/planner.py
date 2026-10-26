"""Planner agent: reads the question and routes it to the Analyst.

One small model call (via app.adapters.meterless) classifies the question as
{player_name, player_names, question_type}; if that call fails, keyword rules
(factor_queries.guess_question_type) pick the type and the Analyst finds the players
from the names in the question. A "compare" question (start A or B?) names two players. The Planner then hands off to the Analyst, which
looks the player up, checks the premise and runs the factor queries for that type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents import factor_queries
from app.trace import trace

AGENT_NAME = "planner"
PROMPT = """\
Read one fantasy football question. Reply with only this JSON:
{"player_name": "<full name of the NFL player it is about, or null>",
 "player_names": ["<for compare: both players' full names>"],
 "question_type": "why" | "replacement" | "start_sit" | "waiver" | "compare" | "other"}
why: explain a player's production. replacement: who takes over if a player is out,
including who to pick up or start because a player is out or misses time ("Should I pick
up a 49ers receiver if Evans misses time?" is replacement, about Evans).
start_sit: start or bench one player. waiver: pick up, add or drop.
compare: choose between two players ("X or Y?", "X vs Y", "I have X on my bench and Y in
my lineup, who should I start?"); player_names lists both, player_name is the first.
For a replacement question, player_name is the player who is out."""
MAX_TOKENS = 4096  # Lightning thinks before replying; 1024 ran out (HTTP 502 empty_response)
TIMEOUT = 30


@dataclass
class Route:
    player_name: str | None
    question_type: str
    by: str  # "model" or "keyword" (the model call failed)
    player_names: tuple[str, ...] = ()  # both players of a "compare" question, when the model named them


def plan(run_id: str, question: str) -> Route:
    """Classify the question, then trace the handoff to the Analyst."""
    from app.agents import analyst  # its model-call helpers; analyst imports this module

    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": question}]
    try:
        reply = analyst._ask_json(run_id, "classify", messages, MAX_TOKENS, _check, agent_name=AGENT_NAME,
                                  timeout=TIMEOUT)
        name = reply.get("player_name")
        name = name.strip() if isinstance(name, str) and name.strip() else None
        names = tuple(n.strip() for n in reply.get("player_names") or [] if isinstance(n, str) and n.strip())
        # A name whose last name is not in the question is the model's guess, not the user's:
        # "Johnson or McBride?" came back as Brock Bowers and Trey McBride (smoke run).
        dropped = [n for n in dict.fromkeys((name, *names)) if n and not named_in(n, question)]
        names = tuple(n for n in names if n not in dropped)
        name = None if name in dropped else name
        question_type = reply["question_type"]
        if question_type == "replacement" and factor_queries.is_pickup_question(question):
            question_type = "waiver"  # "Should I pick up Deebo Samuel?" is not about who replaces him
        question_type = corrected_type(question, question_type)
        route = Route(name or (names[0] if names else None), question_type, "model",
                      names if question_type == "compare" else ())
        if dropped or question_type != reply["question_type"]:
            trace(run_id, AGENT_NAME, "classify", "corrected", dropped_names=dropped,
                  question_type=question_type, model_question_type=reply["question_type"])
    except analyst.AnalystError as error:
        route = Route(None, factor_queries.guess_question_type(question), "keyword")
        trace(run_id, AGENT_NAME, "classify", "fallback", error=str(error), question_type=route.question_type)
    trace(run_id, AGENT_NAME, "handoff", "ok", target_agent="analyst", player_name=route.player_name,
          player_names=list(route.player_names), question_type=route.question_type, classified_by=route.by)
    return route


def corrected_type(question: str, question_type: str) -> str:
    """The code's cues win over the model's type where they are certain (QA run): a trade,
    FAAB or streaming question is unsupported; "is X startable" is start/sit, not other;
    "Should I drop X?" is a keep/drop (waiver) question."""
    if factor_queries.unsupported_topic(question):
        return "unsupported"
    if question_type == "other":
        guess = factor_queries.guess_question_type(question)
        return guess if guess in ("start_sit", "waiver") else question_type
    if question_type == "start_sit" and factor_queries.DROP_CUE.search(question):
        return "waiver"
    return question_type


def named_in(name: str, question: str) -> bool:
    """Whether the question names this player's last name (suffixes and case ignored)."""
    last = factor_queries.name_key(name).split()[-1:]
    return bool(last) and re.search(rf"\b{re.escape(last[0])}\b", factor_queries.name_key(question)) is not None


def _check(reply: dict[str, Any]) -> None:
    if reply.get("question_type") not in factor_queries.QUESTION_TYPES:
        raise ValueError(f"question_type must be one of {', '.join(factor_queries.QUESTION_TYPES)}")
