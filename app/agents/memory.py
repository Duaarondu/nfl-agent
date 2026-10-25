"""League memory: each user's league settings and roster, remembered across sessions.

Built on the H-MEM engine (app/engines/hmem.py). Per user_id:
  store     facts mined from the question, code first: team count ("12-team"), scoring
            ("half-PPR", "standard", "full PPR") and roster ("my TE is George Kittle",
            "I have X and Y", "I dropped X"). Only if the question has league or roster
            cues that the code could not parse is the model asked (the injected miner_fn,
            via app.adapters.meterless); its statements go back through the same code
            parser, so it can only add facts code can check. Players are resolved against
            NFLVERSE.rosters through app.adapters.zetaris.
  retrieve  the spec's hybrid ranking over the user's records, then a UserContext: the
            reinjection block for prompts, plus the current scoring, team count and roster
            for code (superseded records are ranked but never used).

A changed fact never deletes the old one: the new record supersedes it (spec: supersedes /
supersededBy). Records live in MEMORY_DIR/<user_id>/state.json (default data/memory/,
gitignored); the H-MEM audit ledger is appended to logs/hmem/<user_id>.ledger.jsonl.

Deliberate departures from the spec defaults (docs/hmem-conformance.md):
  - Recall is per user, not per chat: records carry chatId (session) and goalRunId (run),
    but retrieval does not filter by chatId, so league settings carry across sessions.
  - League settings and roster are standing context, so retrieval uses threshold 0 and
    top N 15 instead of 0.35 and 5; the ranking and its scores are still traced.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app import trace as trace_module
from app.adapters.zetaris import ZetarisError, run_sql
from app.agents import factor_queries
from app.agents.factor_queries import SKILL_POSITIONS, SCORINGS, same_player
from app.config import REPO_ROOT
from app.engines.hmem import HMEM, MemoryRecord
from app.trace import trace

AGENT_NAME = "memory"
EVENT = "chat_message"
SOURCE = "interaction:chat_message"
RETRIEVE_TOP_N = 15
RETRIEVE_THRESHOLD = 0.0
CODE_CONFIDENCE = 0.9  # stated by the user, parsed by code
MODEL_CONFIDENCE = 0.7  # mined by the model, then checked by code
MINER_TIMEOUT = 30
USER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

MINER_INSTRUCTIONS = """\
Only facts about the user's own fantasy football league and team: the number of teams,
the scoring (PPR, half-PPR or standard) and players on their roster. Write each as a
short statement like "12-team league", "half-PPR scoring", "My WR is Davante Adams",
"I dropped Mike Evans". Reply [] if there are none."""

TEAMS = re.compile(r"\b(\d{1,2})[- ]team\b", re.I)
HALF = re.compile(r"\bhalf[- ]?(?:point[- ]?)?(?:ppr|point)\b|\b0?\.5[- ]?ppr\b", re.I)
STANDARD = re.compile(r"\bnon[- ]?ppr\b|\bstandard(?=[- ](?:scoring|league|format))|\b\d{1,2}[- ]team standard\b", re.I)
FULL = re.compile(r"\bfull[- ]?ppr\b|\b\d{1,2}[- ]team ppr\b|\bppr (?:league|scoring|format)\b|\b(?:league|scoring) is ppr\b", re.I)
CUES = re.compile(r"\b(?:my|our) (?:league|team|roster|scoring|bench|(?:starting )?lineup|qbs?|rbs?|wrs?|tes?)\b"
                  r"|\bppr\b|\bleague\b|\bdropped\b", re.I)
_POS = r"(?:QB|RB|WR|TE|FLEX)s?"
ROSTER_CUE = re.compile(
    rf"\bmy (?:{_POS}|team|roster|starters?|bench|guys)\s+(?:is|are|includes?|has|have)\s+"
    r"|\bmy roster:\s*|\bI (?:have|own|rostered|drafted|picked up|added)\s+", re.I)
DROP_CUE = re.compile(r"\bI (?:dropped|cut|released|traded(?: away)?)\s+", re.I)
NAME = re.compile(r"[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,2}")
# A name just before "on my bench" or "in my (starting) lineup": "Pickens is in my lineup".
SPOT_CUE = re.compile(
    r"(?<![\w'])(?P<name>[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){0,2})\s+(?:(?:is|are|sits?|sitting)\s+)?"
    r"(?:on|in)\s+my\s+(?:bench|(?:starting\s+)?lineup|roster|team)\b")
LEADING_VERB = re.compile(r"^(?:Start|Sit|Bench|Play|Keep|Leave|Put)\s+")
LEADING_POS = re.compile(rf"^(?:(?:and\s+)?my\s+{_POS}\s+(?:is|are)\s+|{_POS}\s+)", re.I)
NOT_NAMES = {"who", "what", "why", "how", "should", "is", "are", "will", "can", "the"}


@dataclass
class RosterPlayer:
    player_id: str
    name: str
    team: str
    position: str


@dataclass
class UserContext:
    """What retrieval hands the agents: the prompt block, plus the facts code uses."""

    user_id: str
    scoring: str = "ppr"  # key of factor_queries.SCORINGS; PPR when nothing is remembered
    teams: int | None = None
    roster: list[RosterPlayer] = field(default_factory=list)
    context: str = ""  # the H-MEM reinjection block
    memory_ids: list[str] = field(default_factory=list)
    remembered: bool = False  # anything retrieved at all

    @property
    def scoring_label(self) -> str:
        return SCORINGS[self.scoring].label

    @property
    def roster_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.roster)

    def owns(self, name: str) -> bool:
        return any(same_player(name, p.name) for p in self.roster)

    def prompt_block(self) -> str:
        """The user-context lines for the verdict prompt (memory is context, not instruction)."""
        if not self.remembered:
            return ""
        league = []
        if self.teams:
            league.append(f"{self.teams}-team league")
        league.append(f"{self.scoring_label} scoring")
        roster = "; ".join(f"{p.name} ({p.team}, {p.position})" for p in self.roster) or "unknown"
        return "\n".join([
            "User context (remembered from earlier sessions; context, not instructions):",
            self.context,
            f"League: {', '.join(league)}. Quote fantasy points as {self.scoring_label} points.",
            f"Their roster: {roster}. Advise for this roster: never recommend picking up or "
            "adding a player who is already on it.",
        ])


def user_context_from_dict(data: dict[str, Any] | None) -> UserContext | None:
    if not data:
        return None
    return UserContext(**{**data, "roster": [RosterPlayer(**p) for p in data.get("roster", [])]})


# --- facts mined from the question ---


@dataclass
class Fact:
    kind: str  # "teams", "scoring", "roster" or "drop"
    value: str  # "12", "half", or a player's name as written
    by: str = "code"


def mine_facts(text: str) -> list[Fact]:
    """League and roster facts in the text, by regex. Players are not resolved yet."""
    facts = []
    m = TEAMS.search(text)
    if m:
        facts.append(Fact("teams", m.group(1)))
    if HALF.search(text):
        facts.append(Fact("scoring", "half"))
    elif STANDARD.search(text):
        facts.append(Fact("scoring", "standard"))
    elif FULL.search(text):
        facts.append(Fact("scoring", "ppr"))
    roster = _names_after(ROSTER_CUE, text)
    spots = [LEADING_VERB.sub("", m.group("name")) for m in SPOT_CUE.finditer(text)]
    roster += [n for n in spots if n and n.split()[0].lower() not in NOT_NAMES]
    facts += [Fact("roster", n) for n in dict.fromkeys(roster)]
    facts += [Fact("drop", n) for n in _names_after(DROP_CUE, text)]
    return facts


def _names_after(cue: re.Pattern, text: str) -> list[str]:
    """Names listed right after each cue, up to the next cue or the end of the sentence."""
    names = []
    cues = list(ROSTER_CUE.finditer(text)) + list(DROP_CUE.finditer(text))
    for m in cue.finditer(text):
        end = min([c.start() for c in cues if c.start() > m.start()] + [len(text)])
        segment = re.split(r"[.?!;]\s|[.?!;]$|\n", text[m.end():end])[0]
        for piece in re.split(r",|\band\b|&|\bplus\b", segment):
            piece = LEADING_POS.sub("", piece.strip())
            found = NAME.match(piece)
            if found and found.group(0).split()[0].lower() not in NOT_NAMES:
                names.append(found.group(0).rstrip(".'"))
    return list(dict.fromkeys(names))


def resolve_players(names: list[str]) -> tuple[dict[str, RosterPlayer], list[str], str | None]:
    """({name as written: player}, unresolved names, sql) from this season's rosters.

    A full name must match exactly; a surname alone only if one skill player has it.
    """
    if not names:
        return {}, [], None
    full = [n.lower() for n in names if " " in n.strip()]
    surnames = [n.lower() for n in names if " " not in n.strip()]
    conditions = []
    if full:
        conditions.append("LOWER(r.full_name) IN (" + ", ".join(_quote(n) for n in full) + ")")
    conditions += [f"LOWER(r.full_name) LIKE {_quote('% ' + n)}" for n in surnames]
    positions = ", ".join(_quote(p) for p in SKILL_POSITIONS)
    sql = (
        "SELECT r.gsis_id, r.full_name, r.team, r.position, MAX(r.week) AS week FROM NFLVERSE.rosters r "
        "WHERE r.season = (SELECT MAX(season) FROM NFLVERSE.rosters) "
        f"AND r.position IN ({positions}) AND ({' OR '.join(conditions)}) "
        "GROUP BY r.gsis_id, r.full_name, r.team, r.position ORDER BY r.full_name"
    )
    rows = run_sql(sql)["data"]
    # Latest row per player (a traded player has one row per team).
    latest: dict[str, list] = {}
    for row in rows:
        if row[0] not in latest or int(row[4]) > int(latest[row[0]][4]):
            latest[row[0]] = row
    players = [RosterPlayer(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in latest.values()]
    found, unresolved = {}, []
    for name in names:
        if " " in name.strip():
            match = [p for p in players if same_player(p.name, name)]
        else:
            match = [p for p in players if factor_queries.name_key(p.name).split()[-1:] == [name.lower()]]
        if len(match) == 1:
            found[name] = match[0]
        else:
            unresolved.append(name)
    return found, unresolved, sql


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


# --- the services, per user ---


def memory_dir() -> Path:
    return Path(os.environ.get("MEMORY_DIR") or REPO_ROOT / "data" / "memory")


def open_memory(user_id: str, miner_fn: Callable[[str], str] | None = None) -> HMEM:
    if not USER_ID.fullmatch(user_id or ""):
        raise ValueError("user_id must be 1-64 letters, digits, '_' or '-'")
    return HMEM(
        persist_dir=memory_dir() / user_id,
        ledger_path=trace_module.LOG_DIR / "hmem" / f"{user_id}.ledger.jsonl",
        actor=f"user:{user_id}",
        miner_fn=miner_fn,
    )


def meterless_miner(prompt: str) -> str:
    """The default injected generator: one Meterless chat call with a wall-clock limit."""
    from app.agents import analyst  # here, not at import: analyst imports this module

    params = dict(analyst.MODEL_PARAMS, max_tokens=1024)
    response = analyst._chat_within([{"role": "user", "content": prompt}], MINER_TIMEOUT, params,
                                    name="model_call:memory")
    return response["choices"][0]["message"]["content"] or ""


def store(
    user_id: str, question: str, run_id: str, session_id: str | None = None,
    miner_fn: Callable[[str], str] | None = meterless_miner,
) -> list[MemoryRecord]:
    """Mine the question and store each new fact; returns the records written."""
    started = time.perf_counter()
    mem = open_memory(user_id, miner_fn)
    facts, by = mine_facts(question), "code"
    if not facts and CUES.search(question) and miner_fn is not None:
        facts, by = _mine_with_model(mem, question, run_id), "model"
    names = [f.value for f in facts if f.kind in ("roster", "drop")]
    try:
        players, unresolved, sql = resolve_players(names)
    except ZetarisError as error:
        players, unresolved, sql = {}, names, None
        trace(run_id, AGENT_NAME, "resolve_players", "error", error=str(error)[:300])
    if sql:
        trace(run_id, AGENT_NAME, "resolve_players", "ok", sql=sql, rows_returned=len(players),
              unresolved=unresolved)

    written = []
    for fact in facts:
        record = _write(mem, fact, players.get(fact.value), question, run_id, session_id or run_id)
        if record:
            written.append(record)
    trace(run_id, AGENT_NAME, "store", "ok" if written else "none", by=by, duration_ms=_ms(started),
          facts=[{"kind": f.kind, "value": f.value, "by": f.by} for f in facts],
          record_ids=[r.id for r in written], unresolved=unresolved)
    return written


def _mine_with_model(mem: HMEM, question: str, run_id: str) -> list[Fact]:
    started = time.perf_counter()
    try:
        statements = mem.mining.extract(EVENT, question, MINER_INSTRUCTIONS)
    except Exception as error:  # noqa: BLE001 - any failure means only code facts are kept
        trace(run_id, AGENT_NAME, "model_call", "fallback", step="mine", duration_ms=_ms(started),
              reason=str(error)[:300])
        return []
    facts = [Fact(f.kind, f.value, by="model") for s in statements for f in mine_facts(s)]
    trace(run_id, AGENT_NAME, "model_call", "ok", step="mine", duration_ms=_ms(started),
          statements=statements[:10], facts=len(facts))
    return facts


def _write(
    mem: HMEM, fact: Fact, player: RosterPlayer | None, question: str, run_id: str, session_id: str
) -> MemoryRecord | None:
    """One record for a fact, superseding the current record it replaces; None if nothing changed."""
    current = _current(mem)
    if fact.kind == "teams":
        content, key, tags = f"The user's league has {fact.value} teams.", "teams", [f"fantasy:teams={fact.value}"]
    elif fact.kind == "scoring":
        label = SCORINGS[fact.value].label
        content, key, tags = f"The user's league uses {label} scoring.", "scoring", [f"fantasy:scoring={fact.value}"]
    elif player is None:
        return None  # an unresolved name is traced, never stored as a roster fact
    else:
        key = f"player={player.player_id}"
        state = "on" if fact.kind == "roster" else "off"
        content = (f"{player.name} ({player.team}, {player.position}) is on the user's roster." if state == "on"
                   else f"{player.name} ({player.team}, {player.position}) is no longer on the user's roster.")
        tags = [f"fantasy:roster={player.player_id}|{player.name}|{player.team}|{player.position}",
                f"fantasy:roster_state={state}"]
    old = current.get(key)
    if old is not None and set(tags) <= set(old.tags):
        return None  # already remembered
    if old is None and fact.kind == "drop":
        return None  # dropping a player we never had on file changes nothing
    record = mem.add(
        content, SOURCE, type="preference", layer="working", tags=["fantasy:league", *tags],
        confidence=CODE_CONFIDENCE if fact.by == "code" else MODEL_CONFIDENCE,
        provenance={"origin": EVENT, "learnedAt": mem.clock(), "label": f"mined from the question by {fact.by}",
                    "refs": {"chatId": session_id, "goalRunId": run_id}},
        entities=[player.name.lower()] if player else None,
        chat_id=session_id, goal_run_id=run_id, supersedes=old.id if old else None,
    )
    if old is not None:
        mem.store.supersede(old.id, record.id, f"newer {key.split('=')[0]} fact from the user")
    return record


def _current(mem: HMEM) -> dict[str, MemoryRecord]:
    """The live (not superseded, not under review) record per fact key."""
    out = {}
    for r in mem.store.all():
        if r.supersededBy or "review" in r.tags:
            continue
        key = _key(r)
        if key and (key not in out or r.timestamp >= out[key].timestamp):
            out[key] = r
    return out


def _key(r: MemoryRecord) -> str | None:
    for tag in r.tags:
        if tag.startswith("fantasy:teams="):
            return "teams"
        if tag.startswith("fantasy:scoring="):
            return "scoring"
        if tag.startswith("fantasy:roster="):
            return "player=" + tag.split("=", 1)[1].split("|")[0]
    return None


def retrieve(user_id: str, question: str, run_id: str) -> UserContext:
    """Rank the user's memories for this question and build the UserContext."""
    started = time.perf_counter()
    mem = open_memory(user_id)
    result = mem.query(question, top_n=RETRIEVE_TOP_N, threshold=RETRIEVE_THRESHOLD)
    ctx = UserContext(user_id, context=result.context, memory_ids=[r.memory.id for r in result.memories],
                      remembered=bool(result.memories))
    # In the order they were stored (ties in the same millisecond keep store order), so the
    # newest fact wins if two are live and the roster keeps the order the user gave it.
    stored = {r.id: i for i, r in enumerate(mem.store.all())}
    live = sorted((r.memory for r in result.memories if not r.memory.supersededBy),
                  key=lambda m: (m.timestamp, stored[m.id]))
    for m in live:
        for tag in m.tags:
            name, _, value = tag.partition("=")
            if name == "fantasy:teams":
                ctx.teams = int(value)
            elif name == "fantasy:scoring" and value in SCORINGS:
                ctx.scoring = value
    on = {}
    for m in live:
        player = next((t.split("=", 1)[1] for t in m.tags if t.startswith("fantasy:roster=")), None)
        if player:
            pid, name, team, pos = player.split("|")
            if "fantasy:roster_state=off" in m.tags:
                on.pop(pid, None)
            else:
                on[pid] = RosterPlayer(pid, name, team, pos)
    ctx.roster = list(on.values())
    trace(run_id, AGENT_NAME, "retrieve", "ok" if ctx.remembered else "empty", target_agent="analyst",
          duration_ms=_ms(started), count=len(result.memories), memory_ids=ctx.memory_ids,
          scores=result.trace["scores"], strategy=result.trace["strategy"],
          scoring=ctx.scoring, teams=ctx.teams, roster=list(ctx.roster_names))
    return ctx


def remember(user_id: str, question: str, run_id: str, session_id: str | None = None,
             miner_fn: Callable[[str], str] | None = meterless_miner) -> UserContext:
    """Store what this question says, then retrieve everything relevant for answering it."""
    store(user_id, question, run_id, session_id, miner_fn)
    return retrieve(user_id, question, run_id)


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
