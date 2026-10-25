"""Critic agent: checks the Analyst's answer against the numbers before it is shown.

Code checks, each giving an issue with its reason and numbers:
  verdict_support  the recommended player is the one the usage numbers back; a Start /
                   Pick up for a player under half the top teammate's target share
                   always blocks, even if the answer names that teammate
  numbers          every number in the answer is in the query rows or in facts code computed from them
  artifacts        no leaked prompt labels ("[strong]"), "0.0 games" counts or missing values
  question_fit     the answer fits the question type (a "why" answer explains first),
                   its verdict names a player ("Verdict: start." blocks), and it never
                   picks up or starts the player the question says is out
  timing           "after X got hurt" / "since week N" changes really start that week
  user_context     with league memory: no pickup of a player already on the user's
                   roster, and points quoted in the league's scoring (not "PPR" in a
                   half-PPR or standard league)
Then one optional model review call (model_review), which falls back to the code
checks alone if it fails, times out or has no time left. Its issues block only in
round 1, so they drive at most one revision; later rounds record them.

Issues in the final answer block approval and send the verdict back for revision.
Issues in factor summaries the model wrote are recorded but never block: the
revision reruns only the verdict step, so it could not fix them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents import analyst, factor_queries
from app.agents.analyst import AnalystError, AnalystResult
from app.agents.factor_queries import name_key, same_player, sentences
from app.trace import trace

AGENT_NAME = "critic"
REVIEW_MAX_TOKENS = 8192
REVIEW_TIMEOUT = 90  # the run budget (pipeline.RUN_BUDGET) still caps it
MAX_MODEL_ISSUES = 3
# Model-review issues may send the answer back only this many times (the reviewer can be
# wrong, run ddb115ab07ae); the code checks block in every round.
MODEL_BLOCKING_ROUNDS = 1

REVIEW_PROMPT = """\
You check a fantasy football answer against facts computed from nflverse data.
Reply with only this JSON:
{"issues": [{"claim": "<exact words copied from the answer>",
             "reason": "<what the facts show instead, with their numbers>"}]}
Report only claims that the facts contradict or do not support, including claims about
when a change started. Do not report style or wording, or problems listed as already
found. Reply {"issues": []} if the answer holds up."""

ACTIONS = ("hold off on", "pick up", "add", "start", "sit", "bench", "hold", "drop", "stash")
# Actions that commit a lineup spot or a roster move; these must follow the usage numbers.
CONFIDENT_ACTIONS = ("start", "pick up", "add")
QUESTION_ACTIONS = {
    "start_sit": ("start", "sit", "bench"),
    "waiver": ("pick up", "add", "hold off on", "stash", "drop"),
}
# A number on its own: not part of a word like "49ers" or "WR1".
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")
ARTIFACTS = (
    (re.compile(r"\[(?:strong|moderate|weak|not supported)\]", re.I), "a support label copied from the prompt"),
    (re.compile(r"\b\d+\.0\s+(?:games?|targets?|touchdowns?|TDs?|carries|receptions|catches|plays|weeks?|snaps)\b", re.I),
     "a count written with a decimal"),
    (re.compile(r"\b(?:nan|NaN|null|n/a)\b|\bNone\b(?!\s+of)"), "a missing value leaked from the data"),
)
TEAMMATE_EVENT = re.compile(
    r"\b(?:after|since|once|when)\s+(?P<who>[A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+)*)\s+"
    r"(?:got hurt|got injured|was injured|went out|went down|was ruled out|was out|missed time|left)"
)
WEEK_EVENT = re.compile(r"\b(?P<word>since|after|from|starting in|beginning in)\s+week\s+(?P<week>\d+)", re.I)
RISE = re.compile(r"\b(?:rose|risen|rises?|rising|grew|grown|grows?|growing|increas(?:e[sd]?|ing)|jump(?:s|ed|ing)"
                  r"|climb(?:s|ed|ing)|spik(?:es|ed|ing)|surg(?:es|ed|ing)|expand(?:s|ed|ing)|boost(?:s|ed|ing)?"
                  r"|higher|more)\b", re.I)
FALL = re.compile(r"\b(?:fell|fallen|falls?|falling|drop(?:s|ped|ping)|declin(?:e[sd]?|ing)|decreas(?:e[sd]?|ing)"
                  r"|shr(?:ank|inks?|inking)|lower|fewer)\b", re.I)
# Clauses checked on their own: "snap share fell ... starting in week 4; ... yards per target rising".
CLAUSE_BREAK = re.compile(r";\s*")
# (words in the sentence, factor whose weekly rows hold it, column, label); first match wins.
METRICS = (
    (r"yards per target", "Big plays", "yards_per_target", "yards per target"),
    (r"air yards", "Big plays", "air_yards_share_pct", "air yards share"),
    (r"target share", "Opportunity", "target_share_pct", "target share"),
    (r"snap", "Opportunity", "snap_pct", "snap share"),
    (r"\btargets\b", "Opportunity", "targets", "targets"),
    (r"", "Opportunity", "{points}", "fantasy points"),  # the scoring's points column
)
PICKUP_ACTIONS = ("pick up", "add")
# A replacement answer: "<depth chart pick> is next at WR on the depth chart, but ... so for fantasy: pick up X."
FOR_FANTASY = "for fantasy:"
# "PPR" not part of "half-PPR", "half PPR", "0.5 PPR" or "non-PPR".
FULL_PPR = re.compile(r"(?<!half-)(?<!half )(?<!0\.5 )(?<!\.5 )(?<!non-)(?<!non )\bPPR\b", re.I)
ANY_PPR = re.compile(r"(?<!non-)(?<!non )\bPPR\b", re.I)


@dataclass
class Issue:
    check: str  # verdict_support, numbers, artifacts, question_fit, timing or model_review
    where: str  # "answer" or "factor:<name>"
    claim: str  # the words being questioned
    reason: str
    blocking: bool = True


@dataclass
class Critique:
    round: int
    answer: str
    issues: list[Issue]
    reviewed_by: str  # "model" or "rule-based" (review off, skipped or failed: code checks only)
    status: str = "approved"  # or "needs_revision"

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]


def critique(
    result: AnalystResult, round: int, deadline: float, model_review: bool = True
) -> Critique:
    """Run the code checks, then (optionally) one model review; trace the outcome."""
    issues = check_answer(result)
    reviewed_by = "rule-based"
    if model_review:
        try:
            found_by_model = _model_review(result, issues, deadline)
            if round > MODEL_BLOCKING_ROUNDS:
                for issue in found_by_model:
                    issue.blocking = False  # recorded, but only the code checks block after round 1
            issues += found_by_model
            reviewed_by = "model"
        except AnalystError as error:
            trace(result.run_id, AGENT_NAME, "review", "fallback", round=round, reviewed_by="rule-based",
                  reason=str(error)[:300])
    found = Critique(round, result.answer, issues, reviewed_by)
    found.status = "needs_revision" if found.blocking else "approved"
    trace(
        result.run_id, AGENT_NAME, "critique", found.status,
        target_agent="analyst" if found.blocking else None, round=round, reviewed_by=reviewed_by,
        blocking=len(found.blocking),
        issues=[{"check": i.check, "where": i.where, "blocking": i.blocking, "reason": i.reason[:300]} for i in issues],
    )
    return found


def check_answer(result: AnalystResult) -> list[Issue]:
    return [
        *check_verdict_support(result),
        *check_numbers(result),
        *check_artifacts(result),
        *check_question_fit(result),
        *check_timing(result),
        *check_user_context(result),
    ]


# --- a) the recommended player is the one the numbers back ---


def check_verdict_support(result: AnalystResult) -> list[Issue]:
    verdict = verdict_sentence(result.answer)
    name = recommended_name(verdict) if verdict else None
    subject = result.player.name if result.player else ""
    if not name or (same_player(name, subject) and result.question_type != "replacement"):
        return []  # e.g. "Start Christian Watson" about Watson himself: nothing to compare
    if _owned(result, name):
        return []  # already on the user's roster: check (f) user_context covers it
    issues = []

    usage = _table(result, "Team usage")
    if usage:
        names, positions, recent = usage.text("player_display_name"), usage.text("position"), usage.col("recent_target_share_pct")
        # Players already on the user's roster are not options, so they are not compared.
        rows = [(n, p, s) for n, p, s in zip(names, positions, recent)
                if not same_player(n, subject) and not _owned(result, n)]
        mine = next(((n, s) for n, _, s in rows if same_player(n, name)), None)
        if mine is None or mine[1] is None:
            issues.append(Issue("verdict_support", "answer", verdict,
                                f"{name} has no recent target share in the {_team(result)} usage rows."))
        else:
            ahead = sorted(((n, p, s) for n, p, s in rows if s is not None and s > mine[1]), key=lambda r: -r[2])
            trailing = " and ".join(f"{n} ({p}) {_fmt(s)}%" for n, p, s in ahead)
            action = _action(verdict) or ""
            # A confident action for a player far behind on usage is blocked even if the
            # answer names the teammates ahead of him: mentioning them is not following them.
            if action in CONFIDENT_ACTIONS and ahead and mine[1] < ahead[0][2] / 2:
                top_name, top_pos, top_share = ahead[0]
                issues.append(Issue(
                    "verdict_support", "answer", verdict,
                    f"{mine[0]}'s recent target share ({_fmt(mine[1])}%) trails {trailing}, and is less than "
                    f"half of {top_name}'s. A '{action.capitalize()}' must follow the usage numbers: recommend "
                    "the player they back. The answer may still say who is next on the depth chart.",
                ))
            elif any(not mentioned(n, result.answer) for n, _, _ in ahead):
                issues.append(Issue(
                    "verdict_support", "answer", verdict,
                    f"{mine[0]}'s recent target share ({_fmt(mine[1])}%) trails {trailing}. "
                    "The answer must explain why it backs him over them, or recommend the player the numbers back.",
                ))

    without = _table(result, "Games without the player")
    if without:
        missed = [i for i, s in enumerate(without.text("player_status"))
                  if s == "missed" and not _owned(result, without.text("player_display_name")[i])]
        if missed:
            share = without.col("avg_target_share_pct")
            best = max(missed, key=lambda i: share[i] or 0)
            top = without.text("player_display_name")[best]
            if not same_player(top, name) and not mentioned(top, result.answer):
                issues.append(Issue(
                    "verdict_support", "answer", verdict,
                    f"In the games {subject} missed, {top} had the top target share ({_fmt(share[best])}%), not {name}.",
                ))
    return issues


# --- b) every number comes from the rows or the facts code computed from them ---


def check_numbers(result: AnalystResult) -> list[Issue]:
    allowed = allowed_numbers(result)
    issues = [
        Issue("numbers", "answer", sentence, f"{value} is not in the cited rows or the facts computed from them.")
        for sentence, value in unknown_numbers(result.answer, allowed)
    ]
    for f in result.factors:
        if f.rated_by == "model":
            issues += [
                Issue("numbers", f"factor:{f.factor}", sentence,
                      f"{value} is not in the cited rows or the facts computed from them.", blocking=False)
                for sentence, value in unknown_numbers(f.summary, allowed)
            ]
    return issues


def allowed_numbers(result: AnalystResult) -> list[float]:
    texts = [result.season_context, result.question, result.premise_correction or ""]
    for q in result.queries:
        texts += [str(v) for row in q.rows for v in row if v is not None]
        if not q.error:
            texts += factor_queries.summarize(q.factor or "", q.headers, q.rows)
    texts += [f.rule or "" for f in result.factors]
    texts += [str(factor_queries.START_PPR), str(factor_queries.PICKUP_SHARE)]  # quoted by rule-based verdicts
    return sorted({float(m) for text in texts for m in NUMBER.findall(text)})


def unknown_numbers(text: str, allowed: list[float]) -> list[tuple[str, str]]:
    """(sentence, number) for each number in text that no allowed value matches to 1 decimal place."""
    out = []
    for sentence in sentences(text):
        for value in NUMBER.findall(sentence):
            if not any(abs(float(value) - a) < 0.051 for a in allowed):
                out.append((sentence, value))
    return out


# --- c) leftovers from prompts and data ---


def check_artifacts(result: AnalystResult) -> list[Issue]:
    issues = [Issue("artifacts", "answer", m, f"'{m}' is {what}.") for m, what in _artifacts(result.answer)]
    for f in result.factors:
        if f.rated_by == "model":
            issues += [Issue("artifacts", f"factor:{f.factor}", m, f"'{m}' is {what}.", blocking=False)
                       for m, what in _artifacts(f.summary)]
    return issues


def _artifacts(text: str) -> list[tuple[str, str]]:
    return [(m.group(0), what) for pattern, what in ARTIFACTS for m in pattern.finditer(text)]


# --- d) the answer fits the question type ---


def check_question_fit(result: AnalystResult) -> list[Issue]:
    parts = sentences(result.answer)
    first = parts[0] if parts else ""
    qt = result.question_type
    verdict = verdict_sentence(result.answer)
    subject = result.player.name if result.player else ""
    name = recommended_name(verdict) if verdict else None
    out = qt == "replacement" or bool(subject and factor_queries.says_out(result.question, subject))
    if out and name and same_player(name, subject) and _action(verdict) in CONFIDENT_ACTIONS:
        return [Issue("question_fit", "answer", verdict,
                      f"The verdict says to {_action(verdict)} {subject}, the player who is out; "
                      "recommend who replaces him.")]
    if verdict is not None and qt != "replacement":  # replacement has its own stand-in check below
        action = _action(verdict)
        if action and not recommended_name(verdict):
            return [Issue("question_fit", "answer", verdict,
                          f"The verdict '{verdict.rstrip('.')}' names no player; say who to {action}.")]
    if qt == "why":
        if _action(first):
            return [Issue("question_fit", "answer", first,
                          f"A why question needs the explanation first; the answer opens with the action '{first}'.")]
        if not NUMBER.search(first):
            return [Issue("question_fit", "answer", first,
                          "A why answer should open with the explanation and its numbers.")]
    elif qt == "replacement":
        verdict = verdict_sentence(result.answer)
        name = recommended_name(verdict) if verdict else None
        subject = result.player.name if result.player else ""
        if not name:
            return [Issue("question_fit", "answer", verdict or first,
                          "A replacement question needs a named stand-in; the verdict names no player.")]
        if same_player(name, subject):
            return [Issue("question_fit", "answer", verdict,
                          f"The verdict recommends {subject}, the player who is out.")]
    elif qt in QUESTION_ACTIONS:
        if _action(first) not in QUESTION_ACTIONS[qt]:
            allowed = ", ".join(a.capitalize() for a in QUESTION_ACTIONS[qt])
            return [Issue("question_fit", "answer", first,
                          f"A {qt.replace('_', '/')} answer should open with one of: {allowed}.")]
    return []


# --- e) timing: a change claimed to follow an event must start that week ---


def check_timing(result: AnalystResult) -> list[Issue]:
    issues = _timing(result, result.answer, "answer", blocking=True)
    for f in result.factors:
        if f.rated_by == "model":
            issues += _timing(result, f.summary, f"factor:{f.factor}", blocking=False)
    return issues


def _timing(result: AnalystResult, text: str, where: str, blocking: bool) -> list[Issue]:
    """Each clause that ties a change to an event is tested on its own, so a direction
    word in one clause ("yards per target rising") is never read against another
    clause's event ("... starting in week 4")."""
    issues = []
    for sentence in sentences(text):
        for clause in CLAUSE_BREAK.split(sentence):
            event = _event(result, clause)
            if event is None:
                continue
            start, label = event
            if start is None:
                issues.append(Issue("timing", where, sentence, label, blocking))
                continue
            rises, falls = RISE.search(clause), FALL.search(clause)
            if bool(rises) == bool(falls):
                continue  # no single direction claimed
            problem = _timing_problem(result, clause, start, label, rises is not None, (rises or falls).start())
            if problem:
                issues.append(Issue("timing", where, sentence, problem, blocking))
    return issues


def _event(result: AnalystResult, sentence: str) -> tuple[int | None, str] | None:
    """(first week after the event, label), (None, why not found) or None if no event is claimed."""
    m = TEAMMATE_EVENT.search(sentence)
    if m:
        who = m.group("who")
        absences = _table(result, "Teammate absences")
        weeks = [int(w) for w, n in zip(absences.text("week"), absences.text("full_name")) if _named(n, who)] if absences else []
        if not weeks:
            return None, f"The injury reports in the data have no Out or Doubtful entry for {who}."
        return min(weeks), f"{who} was first out in week {min(weeks)}"
    m = WEEK_EVENT.search(sentence)
    if m:
        week = int(m.group("week"))
        return (week + 1 if m.group("word").lower() == "after" else week), f"week {week}"
    return None


def _timing_problem(
    result: AnalystResult, sentence: str, start: int, label: str, rises: bool, at: int = 0
) -> str | None:
    _, factor, column, metric = _metric(sentence, at)
    table = _table(result, factor)
    if not table:
        return None  # no weekly rows for this question type; nothing to test against
    if column == "{points}":
        column, metric = table.points, f"{table.scoring.label} points"
    by_week = {int(w): v for w, v in zip(table.text("week"), table.col(column)) if w and v is not None}
    before = [v for w, v in sorted(by_week.items()) if w < start]
    after = [v for w, v in by_week.items() if w >= start]
    if not before or not after:
        return None
    b, a = _avg(before), _avg(after)
    direction = "rise" if rises else "fall"
    if (rises and a <= b) or (not rises and a >= b):
        return (f"His {metric} averaged {_fmt(b)} before week {start} and {_fmt(a)} from week {start} on, "
                f"so it did not {direction} after {label}.")
    last_week = max(w for w in by_week if w < start)
    if (rises and before[-1] >= a) or (not rises and before[-1] <= a):
        return (f"The {direction} in his {metric} started before {label}: week {last_week} already had "
                f"{_fmt(before[-1])}, vs {_fmt(a)} on average from week {start} on.")
    return None


def _metric(sentence: str, at: int) -> tuple[str, str, str, str]:
    """The METRICS entry the direction word at position `at` is about: the last metric
    named before it ("target share fell"), else the first named after it, else points."""
    lower = sentence.lower()
    named = [(m.start(), entry) for entry in METRICS[:-1] for m in re.finditer(entry[0], lower)]
    before = [n for n in named if n[0] < at]
    if before:
        return max(before, key=lambda n: n[0])[1]
    return min(named, key=lambda n: n[0])[1] if named else METRICS[-1]


# --- f) league memory: the user's roster and scoring ---


def check_user_context(result: AnalystResult) -> list[Issue]:
    ctx = result.user_context
    if not ctx or not ctx.remembered:
        return []
    issues = []
    verdict = verdict_sentence(result.answer)
    name = recommended_name(verdict) if verdict else None
    if name and _action(verdict) in PICKUP_ACTIONS and ctx.owns(name):
        issues.append(Issue("user_context", "answer", verdict,
                            f"{name} is already on the user's roster; recommend a player who is not."))
    if ctx.scoring != "ppr":
        wrong = FULL_PPR if ctx.scoring == "half" else ANY_PPR
        for sentence in sentences(result.answer):
            if wrong.search(sentence):
                issues.append(Issue("user_context", "answer", sentence,
                                    f"The user's league uses {ctx.scoring_label} scoring; quote "
                                    f"{ctx.scoring_label} points, not PPR."))
    return issues


# --- the optional model review ---


def _model_review(result: AnalystResult, found: list[Issue], deadline: float) -> list[Issue]:
    facts = []
    for q in result.queries:
        if not q.error:
            facts += [f"- {q.factor or 'Query'}: {line}" for line in factor_queries.summarize(q.factor or "", q.headers, q.rows)]
    ctx = result.user_context.prompt_block() if result.user_context else ""
    lines = [
        result.season_context,
        *([ctx] if ctx else []),
        f"Question: {result.asked or result.question}",
        *( [f"Premise check: {result.premise_correction}"] if result.premise_correction else [] ),
        "Facts:", *facts,
        f"Answer to check:\n{result.answer}",
    ]
    if found:
        lines += ["Already found:", *(f"- {i.reason}" for i in found)]
    messages = [
        {"role": "system", "content": REVIEW_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]
    reply = analyst._ask_json(
        result.run_id, "review", messages, REVIEW_MAX_TOKENS, _check_review,
        agent_name=AGENT_NAME, timeout=REVIEW_TIMEOUT, deadline=deadline,
    )
    issues = []
    answer = _squash(result.answer)
    for item in reply["issues"][:MAX_MODEL_ISSUES]:
        claim, reason = item["claim"].strip(), analyst.round_numbers(item["reason"].strip())
        # Only a claim quoted from the answer can block: an unquotable one may be the reviewer's own slip.
        issues.append(Issue("model_review", "answer", claim, reason, blocking=bool(claim) and _squash(claim) in answer))
    return issues


def _check_review(reply: dict[str, Any]) -> None:
    items = reply.get("issues")
    if not isinstance(items, list):
        raise ValueError("needs an 'issues' list")
    for item in items:
        if not (isinstance(item, dict) and isinstance(item.get("claim"), str) and isinstance(item.get("reason"), str)):
            raise ValueError("each issue needs 'claim' and 'reason' strings")


# --- helpers ---


def verdict_sentence(answer: str) -> str | None:
    """The action: after "Verdict:" or "so for fantasy:" (a replacement answer's lead) if
    present, else the first sentence that starts with one."""
    parts = sentences(answer)
    for s in parts:
        if s.lower().startswith("verdict:"):
            return s[len("verdict:"):].strip()
    for s in parts:
        at = s.lower().find(FOR_FANTASY)
        if at >= 0:
            return s[at + len(FOR_FANTASY):].strip()
    return next((s for s in parts if _action(s)), None)


def recommended_name(verdict: str) -> str | None:
    action = _action(verdict)
    if not action:
        return None
    m = re.match(r"[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*", verdict[len(action):].strip())
    return m.group(0).rstrip(".") if m else None


def mentioned(name: str, text: str) -> bool:
    """Whether the answer names this player (by surname)."""
    key = name_key(name).split()
    text = re.sub(r"['’]s\b", "", text.lower()).replace("'", "")  # "Kittle's" names Kittle
    return bool(key) and re.search(rf"\b{re.escape(key[-1])}\b", text) is not None


def _named(full: str, given: str) -> bool:
    """'Jayden Reed' matches 'Jayden Reed' or just 'Reed'."""
    given_key = name_key(given)
    return same_player(full, given) or (" " not in given_key and name_key(full).split()[-1:] == [given_key])


def _action(sentence: str) -> str | None:
    lower = sentence.lower().strip()
    bare = lower.rstrip(".!").strip()  # "Start." on its own is an action with no player
    return next((a for a in ACTIONS if lower.startswith(a + " ") or bare == a), None)


def _table(result: AnalystResult, factor: str):
    q = next((q for q in result.queries if q.factor == factor and not q.error and q.rows), None)
    return factor_queries._Rows(q.headers, q.rows) if q else None


def _owned(result: AnalystResult, name: str) -> bool:
    return bool(result.user_context and result.user_context.owns(name))


def _team(result: AnalystResult) -> str:
    return result.player.team if result.player else "team"


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


_avg = factor_queries._avg
_fmt = factor_queries._fmt
