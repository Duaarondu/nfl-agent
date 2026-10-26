"""Queries the Analyst runs in code before the model's first turn.

The player named in the question is looked up in rosters, then a fixed bundle
of SQL runs for that player: one query per "why" factor for why-questions, one
query per head-to-head factor (rows for both players) for a two-player "compare"
question, or status, team usage and depth chart for everything else. All SQL is
plain standard SQL that runs on both Spark SQL (Zetaris) and DuckDB (sample mode).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
QUESTION_TYPES = ("why", "replacement", "start_sit", "waiver", "compare", "other", "unsupported", "status")
# "is Kyle Monangai playing sunday", "Is X out?": answered from the injury report (QA run).
STATUS_CUE = re.compile(r"^\s*(?:is|will)\b.+\b(?:playing|play|out|active|healthy|injured|available|suiting up)\b"
                        r"|\binjury (?:status|report)\b", re.I)
MAX_NAME_CANDIDATES = 60
WHY_FACTORS = (
    "Opportunity", "Teammate absences", "Team pass rate and game script",
    "Big plays", "Touchdowns and red zone", "Matchups",
)
# Head-to-head factors for "compare" (start A or B?): each query returns rows for both players.
COMPARE_FACTORS = ("Weekly opportunity", "Team usage share", "Recent trend", "Touchdown share", "Next matchup")
EVEN = "even"

# Team code -> lowercase names a question might use. Codes match nflverse.
TEAM_NAMES: dict[str, tuple[str, ...]] = {
    "ARI": ("cardinals", "arizona"),
    "ATL": ("falcons", "atlanta"),
    "BAL": ("ravens", "baltimore"),
    "BUF": ("bills", "buffalo"),
    "CAR": ("panthers", "carolina"),
    "CHI": ("bears", "chicago"),
    "CIN": ("bengals", "cincinnati"),
    "CLE": ("browns", "cleveland"),
    "DAL": ("cowboys", "dallas"),
    "DEN": ("broncos", "denver"),
    "DET": ("lions", "detroit"),
    "GB": ("packers", "green bay"),
    "HOU": ("texans", "houston"),
    "IND": ("colts", "indianapolis"),
    "JAX": ("jaguars", "jags", "jacksonville"),
    "KC": ("chiefs", "kansas city"),
    "LA": ("rams", "los angeles"),
    "LAC": ("chargers",),
    "LV": ("raiders", "las vegas"),
    "MIA": ("dolphins", "miami"),
    "MIN": ("vikings", "minnesota"),
    "NE": ("patriots", "pats", "new england"),
    "NO": ("saints", "new orleans"),
    "NYG": ("giants",),
    "NYJ": ("jets",),
    "PHI": ("eagles", "philadelphia"),
    "PIT": ("steelers", "pittsburgh"),
    "SEA": ("seahawks", "seattle"),
    "SF": ("49ers", "niners", "san francisco"),
    "TB": ("buccaneers", "bucs", "tampa bay", "tampa"),
    "TEN": ("titans", "tennessee"),
    "WAS": ("commanders", "washington"),
}


@dataclass
class Player:
    player_id: str
    name: str
    team: str
    position: str
    status: str | None
    roster_week: int


@dataclass(frozen=True)
class Scoring:
    """A league's fantasy scoring: how points are computed in SQL and what they are called."""

    name: str  # "ppr", "half" or "standard"
    key: str  # column-alias prefix: ppr_points, half_ppr_points, std_points
    label: str  # "PPR", "half-PPR", "standard"
    sql: str  # the points expression; {p} is the table prefix

    def expr(self, prefix: str = "") -> str:
        return self.sql.format(p=prefix)


SCORINGS = {
    "ppr": Scoring("ppr", "ppr", "PPR", "{p}fantasy_points_ppr"),
    # nflverse has standard and full PPR; half-PPR is their average (standard + 0.5 per catch).
    "half": Scoring("half", "half_ppr", "half-PPR", "({p}fantasy_points + {p}fantasy_points_ppr) / 2"),
    "standard": Scoring("standard", "std", "standard", "{p}fantasy_points"),
}
PPR = SCORINGS["ppr"]


def scoring_of(headers: list[str]) -> Scoring:
    """The scoring a query's points columns were computed with (PPR if none)."""
    for s in (SCORINGS["half"], SCORINGS["standard"]):
        if any(h.startswith(s.key + "_") or f"_{s.key}_" in h for h in headers):
            return s
    return PPR


@dataclass
class PlannedQuery:
    factor: str
    purpose: str
    sql: str


# "is out", "misses time", "ruled out": the question says a player will not play.
OUT_PHRASE = (r"(?:(?:is|are|goes|gets|got|went|was|being)\s+(?:out|ruled out|sidelined|hurt|injured|down)"
              r"|miss(?:es|ing|ed)?\s+(?:time|games?|weeks?)|ruled out|sidelined|(?:is|goes|went)\s+on\s+(?:the\s+)?ir)\b")


def says_out(question: str, name: str | None = None) -> bool:
    """Whether the question says a player (this one, by surname, if name is given) is out.

    "Should I pick up a 49ers receiver if Evans misses time?" says Evans is out.
    """
    if name is None:
        return re.search(rf"\b{OUT_PHRASE}", question, re.I) is not None
    key = name_key(name).split()
    return bool(key) and re.search(rf"\b{re.escape(key[-1])}(?:['’]s)?\s+{OUT_PHRASE}", question, re.I) is not None


# Words that ask who takes over: "Who becomes the Bucs' WR1?", "Who replaces Evans?"
REPLACEMENT_CUE = re.compile(r"\b(becomes?|replace|replaces|takes? over|next man up|wr1|rb1|te1)\b", re.I)
PICKUP_CUE = re.compile(r"\b(pick (?:him )?up|add|grab|claim|waiver)\b", re.I)


def is_pickup_question(question: str) -> bool:
    """"Should I pick up Deebo Samuel?": a waiver question, not a replacement one, unless
    the question says a player is out or asks who takes over (run eef583ef739b)."""
    return bool(PICKUP_CUE.search(question)) and not REPLACEMENT_CUE.search(question) and not says_out(question)


# Questions the app cannot answer: (pattern, what to say it cannot evaluate). QA run.
UNSUPPORTED = (
    (r"\b(?:kickers?|defen[cs]es?|d/st|dst)\b|\bstream(?:ing)?\s+(?:a\s+)?(?:k|def|dst)\b", "kickers or defenses"),
    (r"\btrad(?:e|es|ed|ing)\b|\bis this (?:deal )?fair\b", "trades"),
    (r"\bsell(?:ing)? high\b|\bbuy(?:ing)? low\b|\b(?:ros|rest[- ]of[- ](?:the[- ])?season)\b|\bdynasty\b"
     r"|\blegit or (?:a )?fluke\b|\bfluke\b", "rest-of-season value"),
    (r"\bfaab\b|\bhow much (?:should i )?(?:bid|spend)\b", "FAAB bids"),
    (r"\bhandcuffs?\b", "handcuffs"),
    (r"\bstream(?:ing|er|ers)?\b", "streaming"),
)


def unsupported_topic(question: str) -> str | None:
    """"trades", "FAAB bids" ...: what the question asks that the app cannot evaluate, or None."""
    return next((what for pattern, what in UNSUPPORTED if re.search(pattern, question, re.I)), None)


def unsupported_message(topic: str) -> str:
    if topic == "kickers or defenses":
        return "I cover QB, RB, WR and TE only, not kickers or defenses."
    return f"I can't evaluate {topic} yet."


# "is X startable", "X @ DAL too tempting?", "is PHI a good matchup for X", "X worth a flex" (QA run).
START_CUE = re.compile(r"\b(?:start|sit|bench|flex|startable|too tempting|good matchup|bad matchup|play him|should i play)\b"
                       r"|\s@\s*[A-Z]|\bworth a (?:flex|start)\b", re.I)
DROP_CUE = re.compile(r"\b(?:drop|cut|release)\b|\bshould i (?:hold|keep)\b", re.I)
WAIVER_CUE = re.compile(r"\b(?:pick (?:him )?up|waivers?|add|adding|worth a pickup|must[- ]add|stash)\b", re.I)


def guess_question_type(question: str) -> str:
    """Keyword fallback for when the model cannot classify the question."""
    text = question.lower()
    if unsupported_topic(question):
        return "unsupported"
    if STATUS_CUE.search(question) and not START_CUE.search(question.replace("play", "")):
        return "status"
    if is_why_question(text):
        return "why"
    if is_compare_question(question):
        return "compare"
    # "Should I pick up a 49ers receiver if Evans misses time?" asks who replaces him.
    if REPLACEMENT_CUE.search(text) or says_out(text):
        return "replacement"
    if WAIVER_CUE.search(text) or DROP_CUE.search(text):
        return "waiver"
    if START_CUE.search(question):
        return "start_sit"
    return "other"


# "Pickens or Williams", "between X and Y", "who should I start": a choice between players.
COMPARE_CUE = re.compile(
    r"\b(?:or|vs\.?|versus|over)\b|\bbetween\b.+\band\b|\bwho should I (?:start|pick|play|choose)\b"
    r"|\bwhich (?:one|player|of them)\b", re.I)
FULL_NAME = re.compile(r"\b[A-Z][a-z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+)+")
# Any choice between players, with or without capitals: COMPARE_CUE, "need one", "pick 2",
# "sit Lamb for Nacua", "A instead of B" (QA run). A comma or slash list is checked on the
# players' positions in the question (listed_together).
CHOICE_CUE = re.compile(
    COMPARE_CUE.pattern + r"|\bneed (?:one|a|an|\d)\b|\bpick (?:one|two|\d)\b|\bsit\b.+\bfor\b|\binstead of\b", re.I)


def name_span(player: "Player", text: str) -> tuple[int, int] | None:
    """Where the question names this player: full name, else last name (lowercased text)."""
    low = text.lower().replace("’", "'")
    i = low.find(player.name.lower())
    if i >= 0:
        return i, i + len(player.name)
    last = name_key(player.name).split()[-1:]
    m = re.search(rf"\b{re.escape(last[0])}\b", low) if last else None
    return (m.start(), m.end()) if m else None


def listed_together(question: str, players: list["Player"]) -> bool:
    """Two of the players are named next to each other with only a comma or slash between
    ("Gibbs, Achane", "Hubbard/Henry")."""
    spans = sorted(s for s in (name_span(p, question) for p in players) if s)
    return any(re.fullmatch(r"\s*[,/]\s*", question[a[1]:b[0]]) for a, b in zip(spans, spans[1:]))


def is_choice(question: str, players: list["Player"]) -> bool:
    return CHOICE_CUE.search(question) is not None or listed_together(question, players)


# "Josh Allen on bye, Goff or Bryce Young?": a player named as context, not an option.
CONTEXT_AFTER = re.compile(r"\s*(?:'s\s+|\s+is\s+|\s+)?(?:on (?:a |his )?bye|(?:is )?out|ruled out|injured|hurt)\b", re.I)


def context_players(question: str, players: list["Player"]) -> list["Player"]:
    """Players the question says are on bye or out, when at least two others remain."""
    low = question.lower().replace("’", "'")
    ctx = [p for p in players if (s := name_span(p, question)) and CONTEXT_AFTER.match(low, s[1])]
    return ctx if len(players) - len(ctx) >= 2 else []


def is_compare_question(question: str, last_names: tuple[str, ...] | list[str] = ()) -> bool:
    """A choice cue and at least two players: full names ("Jameson Williams ... George
    Pickens"), plus any single words in last_names, the last names that resolved to a
    player ("Trey McBride or Bowers")."""
    if COMPARE_CUE.search(question) is None:
        return False
    full = set(FULL_NAME.findall(question))
    covered = {w.lower() for f in full for w in f.split()}
    single = {w.lower() for w in last_names} - covered
    return len(full) + len(single) >= 2


def is_why_question(question: str) -> bool:
    return re.search(r"\b(why|explain|what explains|how come)\b", question, re.I) is not None


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


# Nicknames and first names fans use alone (QA run: "CMC", "JSN", "Puka" were "could not find").
# Acronyms match in capitals only; a first name counts only when the last name does not follow.
NICKNAMES = {
    "CMC": "Christian McCaffrey", "JSN": "Jaxon Smith-Njigba", "ARSB": "Amon-Ra St. Brown",
    "Sun God": "Amon-Ra St. Brown", "MHJ": "Marvin Harrison Jr.", "BTJ": "Brian Thomas Jr.",
    "AJB": "A.J. Brown", "T-Mac": "Terry McLaurin", "Puka": "Puka Nacua", "Saquon": "Saquon Barkley",
    "Bijan": "Bijan Robinson", "Lamar": "Lamar Jackson", "Ja'Marr": "Ja'Marr Chase", "Jahmyr": "Jahmyr Gibbs",
    "Deebo": "Deebo Samuel", "JJ": "Justin Jefferson", "Kelce": "Travis Kelce",
}


def with_nicknames(question: str) -> str:
    """The question with each nickname replaced by the player's full name."""
    for alias, full in NICKNAMES.items():
        rest = full[len(alias):].strip() if full.lower().startswith(alias.lower()) else ""
        before = r"(?<!\w)(?<!Travis )" if alias == "Kelce" else r"(?<!\w)"
        after = rf"(?!\w)(?!\s+{re.escape(rest)})" if rest else r"(?!\w)"
        flags = 0 if alias.isupper() else re.I
        question = re.sub(before + re.escape(alias) + after, full, question, flags=flags)
    return question


def names_sql(season: int) -> str:
    """Every skill player's name this season, for a closest-name suggestion."""
    positions = ", ".join(_quote(p) for p in SKILL_POSITIONS)
    return (f"SELECT DISTINCT full_name FROM NFLVERSE.rosters WHERE season = {season} "
            f"AND position IN ({positions})")


def closest_name(question: str, names: list[str]) -> str | None:
    """The roster name closest to a 2-3 word run in the question ("Justin Jeffersen")."""
    by_key = {without_suffix(n).lower(): n for n in names}
    best, score = None, 0.0
    for candidate in name_candidates(question):
        for match in difflib.get_close_matches(candidate, by_key, n=1, cutoff=0.8):
            ratio = difflib.SequenceMatcher(None, candidate, match).ratio()
            if ratio > score:
                best, score = by_key[match], ratio
    return best


def name_candidates(question: str) -> list[str]:
    """Every run of 2-3 words in the question, lowercased: possible full names."""
    words = re.findall(r"[A-Za-z][A-Za-z.'\-]*", question.replace("’", "'"))
    words = [_strip_word(w) for w in words]
    seen: list[str] = []
    for size in (2, 3):
        for i in range(len(words) - size + 1):
            candidate = " ".join(words[i : i + size]).lower()
            if candidate not in seen:
                seen.append(candidate)
    return seen[:MAX_NAME_CANDIDATES]


# "A.J.", "C.J." and "St." keep their periods: the rosters spell them "A.J. Brown",
# "Amon-Ra St. Brown" (QA run: all three were "could not find").
INITIALS = re.compile(r"(?:[A-Za-z]\.){1,3}|St\.", re.I)


def _strip_word(w: str) -> str:
    w = w if INITIALS.fullmatch(w) else w.rstrip(".")
    return w.removesuffix("'s").removesuffix("'")


# A generational suffix at the end of a name: "Deebo Samuel Sr." is "Deebo Samuel".
NAME_SUFFIX = re.compile(r"\s+(?:jr|sr|ii|iii|iv)\.?$", re.I)
SQL_NAME = "REGEXP_REPLACE(LOWER({col}), ' (jr|sr|ii|iii|iv)[.]?$', '')"  # the same, in SQL


def without_suffix(name: str) -> str:
    return NAME_SUFFIX.sub("", name.strip())


def lookup_sql(candidates: list[str], season: int) -> str:
    """Latest roster row this season for each skill player whose full name is a candidate.

    Names match without a Jr./Sr./II/III/IV suffix on either side, so "Deebo Samuel"
    finds "Deebo Samuel Sr." (smoke run eef583ef739b found nobody).
    """
    names = ", ".join(_quote(c) for c in dict.fromkeys(without_suffix(c).lower() for c in candidates))
    positions = ", ".join(_quote(p) for p in SKILL_POSITIONS)
    return (
        "SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week "
        "FROM NFLVERSE.rosters r "
        "JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters "
        f"WHERE season = {season} AND {SQL_NAME.format(col='full_name')} IN ({names}) GROUP BY gsis_id) latest "
        "ON r.gsis_id = latest.gsis_id AND r.week = latest.week "
        f"WHERE r.season = {season} AND r.position IN ({positions}) "
        "ORDER BY r.full_name"
    )


def parse_players(rows: list[list], question: str) -> list[Player]:
    """Players from lookup rows, in the order the question names them."""
    players = [
        Player(str(r[0]), str(r[1]), str(r[2]), str(r[3]), r[4], int(float(r[5]))) for r in rows
    ]
    return order_in_question(players, question)


def order_in_question(players: list[Player], question: str) -> list[Player]:
    """Players in the order the question names them, by full name or else by last name."""
    text = question.lower().replace("’", "'")

    def at(p: Player) -> int:
        i = text.find(p.name.lower())
        if i >= 0:
            return i
        last = name_key(p.name).split()[-1:]
        m = re.search(rf"\b{re.escape(last[0])}\b", text) if last else None
        return m.start() if m else len(text)

    return sorted(players, key=at)


# Capitalised words in questions that are not players' last names.
NOT_LAST_NAMES = {
    "who", "what", "why", "how", "which", "should", "would", "could", "will", "can", "do", "does", "did",
    "is", "are", "was", "start", "starting", "sit", "bench", "play", "pick", "flex", "add", "drop", "stash",
    "trade", "keep", "week", "weeks", "this", "next", "the", "and", "or", "vs", "versus", "over", "between",
    "one", "player", "players", "his", "him", "her", "my", "me", "mine", "you", "your", "for", "with", "from",
    "ppr", "half", "standard", "league", "team", "roster", "lineup", "waiver", "waivers", "fantasy", "points",
    "game", "games", "season", "today", "tonight", "sunday", "monday", "thursday", "saturday", "qb", "rb", "wr",
    "te", "dst", "def", "kicker", "out", "injured", "hurt", "if", "please", "thanks", "hey", "help",
    "i", "i'm", "im", "i've", "i'd", "hold", "sell", "buy", "cut", "release", "need", "bye",
}
CHOICE_WORDS = {"or", "vs", "vs.", "versus", "over"}


def last_name_words(question: str, found: list[Player]) -> list[str]:
    """Single words that may be a player's last name, as written: capitalised, or next to
    "or" / "vs" / "over"; not a common word, team or position, and not part of a player
    already found ("Trey Mcbride or Bowers" -> ["bowers"] once McBride is found)."""
    covered = {t for p in found for t in name_key(p.name).split()}
    teams = {w for names in TEAM_NAMES.values() for n in names for w in n.split()}
    text = question.replace("’", "'")
    found_tokens = list(re.finditer(r"[A-Za-z][A-Za-z.'\-]*", text))
    tokens = [m.group(0) for m in found_tokens]
    clean = [t.rstrip(".").removesuffix("'s").removesuffix("'") for t in tokens]

    def name_like(j: int) -> bool:  # a capitalised word that is not a common word
        return 0 <= j < len(clean) and clean[j][:1].isupper() and clean[j].lower() not in NOT_LAST_NAMES

    def joined(i: int, j: int) -> bool:  # only spaces between tokens i and j: "Gibbs, Achane" are two words
        a, b = sorted((i, j))
        return 0 <= a and b < len(tokens) and text[found_tokens[a].end():found_tokens[b].start()].isspace()

    words = []
    for i, raw in enumerate(tokens):
        word = clean[i]
        low = word.lower()
        if len(low) < 3 or low in NOT_LAST_NAMES or low in covered or low in teams or POSITION_LABEL.fullmatch(word):
            continue
        if (name_like(i - 1) and joined(i - 1, i)) or (name_like(i + 1) and joined(i, i + 1)):
            continue  # part of a full name ("Nobody Atall"): the full-name lookup's job
        prev = tokens[i - 1].lower() if i else ""
        nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        if (word[:1].isupper() or prev in CHOICE_WORDS or nxt in CHOICE_WORDS) and low not in {
                w.lower() for w in words}:
            words.append(word)
    return words


def last_name_lookup_sql(words: list[str], season: int, s: Scoring = PPR) -> str:
    """Skill players on this season's rosters whose last name is one of words, with their
    fantasy points this season (to pick between players who share a last name)."""
    like = " OR ".join(
        f"LOWER(full_name) LIKE {_quote('% ' + w.lower())} OR LOWER(full_name) LIKE {_quote('% ' + w.lower() + ' %')}"
        for w in words
    )
    positions = ", ".join(_quote(p) for p in SKILL_POSITIONS)
    return (
        "WITH latest AS (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters "
        f"WHERE season = {season} AND position IN ({positions}) AND ({like}) GROUP BY gsis_id), "
        f"pts AS (SELECT player_id, ROUND(SUM({s.expr()}), 1) AS season_points FROM NFLVERSE.player_stats "
        f"WHERE season = {season} GROUP BY player_id) "
        "SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week, "
        f"p.season_points AS season_{s.key}_points "
        "FROM NFLVERSE.rosters r JOIN latest l ON r.gsis_id = l.gsis_id AND r.week = l.week "
        "LEFT JOIN pts p ON p.player_id = r.gsis_id "
        f"WHERE r.season = {season} AND r.position IN ({positions}) ORDER BY r.full_name"
    )


@dataclass
class LastName:
    """One last name from the question and what it resolved to."""
    word: str  # as written in the question
    player: Player | None  # None: nobody, or several equally likely players (options)
    options: list[tuple[Player, float | None]]  # the matches, most fantasy points first
    rule: str = ""  # how the player was chosen

    def note(self) -> str:
        p = self.player
        return f"{self.word} = {p.name}, {p.team} {p.position}." if p else ""


def resolve_last_names(
    words: list[str], headers: list[str], rows: list[list], others: list[Player]
) -> list[LastName]:
    """Resolve each last name: one match; else the same position as the other players
    named; then the most fantasy points. Two or more left with the same points (or none)
    is ambiguous: no player, only options."""
    t = _Rows(headers, rows)
    points_col = next((h for h in headers if h.startswith("season_") and h.endswith("_points")), "")
    seen, candidates = set(), []
    for row, pts in zip(rows, t.col(points_col) if points_col else [None] * len(rows)):
        player = Player(str(row[0]), str(row[1]), str(row[2]), str(row[3]), row[4], int(float(row[5])))
        if player.player_id not in seen:
            seen.add(player.player_id)
            candidates.append((player, pts))
    positions = {p.position for p in others}
    out = []
    for word in words:
        matches = [(p, pts) for p, pts in candidates if name_key(p.name).split()[-1:] == [word.lower()]]
        matches.sort(key=lambda m: -1 if m[1] is None else m[1], reverse=True)
        if not matches:
            out.append(LastName(word, None, []))
            continue
        if len(matches) == 1:
            out.append(LastName(word, matches[0][0], matches, "the only skill player with this last name"))
            continue
        same = [m for m in matches if m[0].position in positions]
        pool = same or matches
        why = f"same position as {', '.join(p.name for p in others)}" if same else ""
        if len(pool) == 1:
            out.append(LastName(word, pool[0][0], matches, why))
            continue
        (top, top_pts), (_, next_pts) = pool[0], pool[1]
        if top_pts and top_pts > (next_pts or 0):
            rule = f"most {scoring_of(headers).label} points this season ({_fmt(top_pts)})"
            out.append(LastName(word, top, matches, f"{why}; {rule}" if why else rule))
        else:
            out.append(LastName(word, None, matches))
    return out


def clarify_message(unresolved: list[LastName]) -> str:
    """Ask which player the question means, for each last name that did not resolve."""
    parts = []
    for n in unresolved:
        name = n.word
        if not n.options:
            parts.append(f'I couldn\'t find a skill player called "{name}" on this season\'s rosters.')
        else:
            listed = "; ".join(f"{p.name} ({p.team}, {p.position})" for p, _ in n.options[:6])
            more = f", and {len(n.options) - 6} more" if len(n.options) > 6 else ""
            parts.append(f'"{name}" could be {len(n.options)} players: {listed}{more}.')
    return " ".join(parts) + " Which player do you mean? Please give their full name."


WEEK_IN_QUESTION = re.compile(r"\bweek\s+(\d{1,2})\b", re.I)


def question_week(question: str) -> int | None:
    """The week the question names ("for week 7"), if any."""
    m = WEEK_IN_QUESTION.search(question)
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 22 else None


def teams_mentioned(question: str) -> list[str]:
    """Team codes the question refers to by name or nickname, in order of appearance."""
    text = question.lower()
    found = []
    for code, names in TEAM_NAMES.items():
        positions = [m.start() for n in names for m in re.finditer(rf"\b{re.escape(n)}\b", text)]
        positions += [m.start() for m in re.finditer(rf"\b{code}\b", question)]  # "KC", "TB": capitals only
        if positions:
            found.append((min(positions), code, names))
    return [code for _, code, _ in sorted(found)]


def wrong_teams(question: str, player: Player) -> list[str]:
    """Teams the question pins on the player that the data contradicts ([] if none).

    Mentions as an opponent ("vs the Bucs", "against Tampa") are not a premise, and
    nothing is flagged when the question also names the player's actual team.
    """
    text = question.lower()
    owned = []
    for code in teams_mentioned(question):
        matches = [*(m for name in TEAM_NAMES[code] for m in re.finditer(rf"\b{re.escape(name)}\b", text)),
                   *re.finditer(rf"\b{code}\b", question)]
        for match in matches:
            before = text[max(0, match.start() - 20) : match.start()]
            after = text[match.end() : match.end() + 30]
            # An opponent is not a premise: "vs the Bucs", "at the Eagles", "Taylor @ Minnesota",
            # "is Philadelphia a good matchup for Lamb" (QA run).
            if not re.search(r"(?:\b(?:vs\.?|versus|against|facing|plays|play|at)|@)\s*(?:the\s+)?$", before) \
                    and not re.match(r"\s+(?:a\s+)?(?:good\s+|bad\s+|tough\s+|easy\s+)?(?:matchup|defen[cs]e)\b", after):
                owned.append(code)
    owned = list(dict.fromkeys(owned))
    return [] if player.team in owned else owned


def corrected_question(question: str, wrong: list[str], team: str) -> str:
    """The question with each wrong team's names replaced by the player's actual team."""
    nickname = TEAM_NAMES[team][0]
    nickname = nickname if nickname[0].isdigit() else nickname.title()
    for code in wrong:
        # Longest names first, so "tampa bay" is replaced before "tampa".
        for name in sorted(TEAM_NAMES[code], key=len, reverse=True):
            question = re.sub(rf"(?i)\b{re.escape(name)}\b", nickname, question)
    return question


def status_query(p: Player, season: int) -> PlannedQuery:
    return PlannedQuery(
        "Status",
        f"{p.name}: injury report entries this season",
        "SELECT week, report_status, report_primary_injury, practice_status "
        "FROM NFLVERSE.injuries "
        f"WHERE season = {season} AND gsis_id = {_quote(p.player_id)} ORDER BY week",
    )


def why_bundle(p: Player, season: int, s: Scoring = PPR) -> list[PlannedQuery]:
    """One query per factor in the Analyst prompt's "why" list, plus injury status."""
    pid, team = _quote(p.player_id), _quote(p.team)
    pos = p.position if p.position in SKILL_POSITIONS else "WR"
    return [
        status_query(p, season),
        PlannedQuery(
            "Opportunity",
            f"{p.name}: snap %, targets, target share and {s.label} points by week",
            "SELECT ps.week, ps.opponent_team, sc.offense_snaps, "
            "ROUND(100 * sc.offense_pct, 1) AS snap_pct, ps.targets, "
            "ROUND(100 * ps.target_share, 1) AS target_share_pct, ps.receptions, ps.carries, "
            f"ROUND({s.expr('ps.')}, 1) AS {s.key}_points "
            "FROM NFLVERSE.player_stats ps "
            "LEFT JOIN NFLVERSE.snap_counts sc ON sc.game_id = ps.game_id "
            "AND sc.player = ps.player_display_name AND sc.team = ps.team "
            f"WHERE ps.season = {season} AND ps.player_id = {pid} ORDER BY ps.week",
        ),
        PlannedQuery(
            "Teammate absences",
            f"{p.team} skill players listed Out or Doubtful, by week",
            "SELECT week, full_name, position, report_status, report_primary_injury "
            "FROM NFLVERSE.injuries "
            f"WHERE season = {season} AND team = {team} AND gsis_id <> {pid} "
            "AND position IN ('QB', 'RB', 'WR', 'TE') AND report_status IN ('Out', 'Doubtful') "
            "ORDER BY week, position, full_name LIMIT 50",
        ),
        PlannedQuery(
            "Team pass rate and game script",
            f"{p.team} pass rate and final score margin by week",
            "SELECT p.week, MAX(p.defteam) AS opponent, SUM(p.pass) AS pass_plays, "
            "SUM(p.rush) AS rush_plays, "
            "ROUND(100 * SUM(p.pass) / NULLIF(SUM(p.pass) + SUM(p.rush), 0), 1) AS pass_rate_pct, "
            f"MAX(CASE WHEN s.home_team = {team} THEN s.home_score - s.away_score "
            "ELSE s.away_score - s.home_score END) AS final_margin "
            "FROM NFLVERSE.pbp p JOIN NFLVERSE.schedules s ON s.game_id = p.game_id "
            f"WHERE p.season = {season} AND p.posteam = {team} "
            "GROUP BY p.week ORDER BY p.week",
        ),
        PlannedQuery(
            "Big plays",
            f"{p.name}: air yards, yards per target and 20+ yard plays by week",
            "SELECT ps.week, ps.targets, ps.receiving_yards, "
            "ROUND(ps.receiving_air_yards, 1) AS air_yards, "
            "ROUND(100 * ps.air_yards_share, 1) AS air_yards_share_pct, "
            "ROUND(ps.receiving_yards / NULLIF(ps.targets, 0), 1) AS yards_per_target, "
            "COALESCE(b.plays_20_plus, 0) AS plays_20_plus, b.longest_play "
            "FROM NFLVERSE.player_stats ps LEFT JOIN ("
            "SELECT game_id, SUM(CASE WHEN yards_gained >= 20 THEN 1 ELSE 0 END) AS plays_20_plus, "
            "MAX(yards_gained) AS longest_play FROM NFLVERSE.pbp "
            f"WHERE season = {season} AND play_type IN ('pass', 'run') "
            f"AND (receiver_player_id = {pid} OR rusher_player_id = {pid}) GROUP BY game_id"
            ") b ON b.game_id = ps.game_id "
            f"WHERE ps.season = {season} AND ps.player_id = {pid} ORDER BY ps.week",
        ),
        PlannedQuery(
            "Touchdowns and red zone",
            f"{p.name}: touchdowns, TD points vs {s.label} points, red-zone targets and carries by week",
            "SELECT ps.week, ps.receiving_tds, ps.rushing_tds, ps.passing_tds, "
            "6 * (ps.receiving_tds + ps.rushing_tds) + 4 * ps.passing_tds AS td_points, "
            f"ROUND({s.expr('ps.')}, 1) AS {s.key}_points, "
            "COALESCE(rz.rz_targets, 0) AS rz_targets, COALESCE(rz.team_rz_targets, 0) AS team_rz_targets, "
            "COALESCE(rz.rz_carries, 0) AS rz_carries "
            "FROM NFLVERSE.player_stats ps LEFT JOIN ("
            f"SELECT game_id, posteam, SUM(CASE WHEN receiver_player_id = {pid} THEN 1 ELSE 0 END) AS rz_targets, "
            "SUM(CASE WHEN receiver_player_id IS NOT NULL THEN 1 ELSE 0 END) AS team_rz_targets, "
            f"SUM(CASE WHEN rusher_player_id = {pid} AND rush = 1 THEN 1 ELSE 0 END) AS rz_carries "
            f"FROM NFLVERSE.pbp WHERE season = {season} AND yardline_100 <= 20 "
            "AND play_type IN ('pass', 'run') GROUP BY game_id, posteam"
            ") rz ON rz.game_id = ps.game_id AND rz.posteam = ps.team "
            f"WHERE ps.season = {season} AND ps.player_id = {pid} ORDER BY ps.week",
        ),
        PlannedQuery(
            "Matchups",
            f"{p.name}: {s.label} points by opponent, and each opponent's average {s.label} points allowed to {pos}s "
            "(rank 1 = most allowed)",
            f"WITH allowed AS (SELECT opponent_team, week, SUM({s.expr()}) AS pts "
            f"FROM NFLVERSE.player_stats WHERE season = {season} AND position = {_quote(pos)} "
            "GROUP BY opponent_team, week), "
            f"avg_allowed AS (SELECT opponent_team, ROUND(AVG(pts), 1) AS avg_{s.key}_allowed "
            "FROM allowed GROUP BY opponent_team), "
            f"ranked AS (SELECT opponent_team, avg_{s.key}_allowed, "
            f"RANK() OVER (ORDER BY avg_{s.key}_allowed DESC) AS allowed_rank FROM avg_allowed) "
            f"SELECT ps.week, ps.opponent_team, ROUND({s.expr('ps.')}, 1) AS {s.key}_points, "
            f"r.avg_{s.key}_allowed AS opp_avg_{s.key}_allowed_to_{pos.lower()}, r.allowed_rank "
            "FROM NFLVERSE.player_stats ps LEFT JOIN ranked r ON r.opponent_team = ps.opponent_team "
            f"WHERE ps.season = {season} AND ps.player_id = {pid} ORDER BY ps.week",
        ),
    ]


def team_bundle(p: Player, season: int, latest_week: int, s: Scoring = PPR) -> list[PlannedQuery]:
    """Status, team usage and depth chart: for waiver, start/sit and replacement questions.

    A QB gets no team usage query: target share measures receivers, and the factor agent
    turned a TE's 18.9% into "the highest target share among BUF QBs" (smoke run, Josh Allen).
    """
    team = _quote(p.team)
    pos = p.position if p.position in SKILL_POSITIONS else "WR"
    recent = max(1, latest_week - 1)
    bundle = [
        status_query(p, season),
        PlannedQuery(
            "Team usage",
            f"{p.team} RB/WR/TE usage this season and in weeks {recent}-{latest_week}",
            "SELECT player_display_name, position, COUNT(*) AS games, SUM(targets) AS targets, "
            "ROUND(100 * AVG(target_share), 1) AS avg_target_share_pct, "
            f"ROUND(100 * AVG(CASE WHEN week >= {recent} THEN target_share END), 1) AS recent_target_share_pct, "
            f"SUM(carries) AS carries, ROUND(AVG({s.expr()}), 1) AS {s.key}_per_game "
            f"FROM NFLVERSE.player_stats WHERE season = {season} AND team = {team} "
            "AND position IN ('RB', 'WR', 'TE') "
            "GROUP BY player_display_name, position ORDER BY targets DESC LIMIT 12",
        ),
        PlannedQuery(
            "Depth chart",
            f"{p.team} current {pos} depth chart (pos_rank 1 = top), with roster status and the week "
            f"{latest_week + 1} injury report",
            "SELECT DISTINCT d.pos_abb, d.pos_rank, d.player_name, r.status AS roster_status, "
            "i.report_status FROM NFLVERSE.depth_charts d "
            "LEFT JOIN (SELECT gsis_id, MAX(status) AS status FROM NFLVERSE.rosters "
            f"WHERE season = {season} AND week = (SELECT MAX(week) FROM NFLVERSE.rosters WHERE season = {season}) "
            "GROUP BY gsis_id) r ON r.gsis_id = d.gsis_id "
            "LEFT JOIN (SELECT gsis_id, MAX(report_status) AS report_status FROM NFLVERSE.injuries "
            f"WHERE season = {season} AND week = {latest_week + 1} GROUP BY gsis_id) i ON i.gsis_id = d.gsis_id "
            f"WHERE d.team = {team} AND d.pos_abb = {_quote(pos)} "
            f"AND d.dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = {team}) "
            "ORDER BY d.pos_rank LIMIT 25",
        ),
    ]
    if p.position == "QB":  # his own points per game is the start/sit basis (QA run: "averages n/a")
        bundle[1] = PlannedQuery(
            "Points per game",
            f"{p.name}: games, passing and rushing touchdowns and {s.label} points per game this season",
            "SELECT player_display_name, position, COUNT(*) AS games, SUM(passing_yards) AS passing_yards, "
            "SUM(passing_tds) AS passing_tds, SUM(rushing_tds) AS rushing_tds, "
            f"ROUND(AVG({s.expr()}), 1) AS {s.key}_per_game "
            f"FROM NFLVERSE.player_stats WHERE season = {season} AND player_id = {_quote(p.player_id)} "
            "GROUP BY player_display_name, position",
        )
    return bundle


def games_without_query(p: Player, season: int, s: Scoring = PPR) -> PlannedQuery:
    """Teammates' targets in the team's games the player missed vs the games he played."""
    pid, team = _quote(p.player_id), _quote(p.team)
    split = "CASE WHEN m.game_id IS NULL THEN 'played' ELSE 'missed' END"
    return PlannedQuery(
        "Games without the player",
        f"{p.team} RB/WR/TE targets in games {p.name} missed vs games he played this season",
        "WITH team_games AS (SELECT game_id FROM NFLVERSE.schedules "
        f"WHERE season = {season} AND (home_team = {team} OR away_team = {team}) AND home_score IS NOT NULL), "
        "played AS (SELECT DISTINCT game_id FROM NFLVERSE.player_stats "
        f"WHERE season = {season} AND player_id = {pid}), "
        "missed AS (SELECT g.game_id FROM team_games g LEFT JOIN played p ON p.game_id = g.game_id "
        "WHERE p.game_id IS NULL) "
        f"SELECT {split} AS player_status, ps.player_display_name, ps.position, COUNT(*) AS games, "
        "SUM(ps.targets) AS targets, ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, "
        f"ROUND(AVG({s.expr('ps.')}), 1) AS {s.key}_per_game "
        "FROM NFLVERSE.player_stats ps JOIN team_games g ON g.game_id = ps.game_id "
        "LEFT JOIN missed m ON m.game_id = ps.game_id "
        f"WHERE ps.season = {season} AND ps.team = {team} AND ps.player_id <> {pid} "
        "AND ps.position IN ('RB', 'WR', 'TE') "
        f"GROUP BY {split}, ps.player_display_name, ps.position "
        "ORDER BY player_status, targets DESC LIMIT 30",
    )


def compare_bundle(
    players: list[Player], season: int, latest_week: int, s: Scoring = PPR, week: int | None = None
) -> list[PlannedQuery]:
    """One query per head-to-head factor, each with a row (or rows) per player.
    week: the week the question names, for the matchup (default: the next game)."""
    ids = ", ".join(_quote(p.player_id) for p in players)
    names = " vs ".join(p.name for p in players)
    pts = s.expr("ps.")
    mid = max(1, latest_week // 2)  # weeks 1-3 vs 4-6 after week 6
    roster = " UNION ALL ".join(
        f"SELECT {_quote(p.player_id)} AS player_id, {_quote(p.name)} AS player, {_quote(p.team)} AS team, "
        f"{_quote(p.position if p.position in SKILL_POSITIONS else 'WR')} AS position"
        for p in players
    )
    return [
        PlannedQuery(
            "Weekly opportunity",
            f"{names}: snap %, targets, target share and {s.label} points by week",
            "SELECT ps.player_display_name AS player, ps.week, ps.opponent_team, "
            "ROUND(100 * sc.offense_pct, 1) AS snap_pct, ps.targets, "
            "ROUND(100 * ps.target_share, 1) AS target_share_pct, ps.receptions, ps.carries, "
            f"ROUND({pts}, 1) AS {s.key}_points "
            "FROM NFLVERSE.player_stats ps "
            "LEFT JOIN NFLVERSE.snap_counts sc ON sc.game_id = ps.game_id "
            "AND sc.player = ps.player_display_name AND sc.team = ps.team "
            f"WHERE ps.season = {season} AND ps.player_id IN ({ids}) ORDER BY ps.player_display_name, ps.week",
        ),
        PlannedQuery(
            "Team usage share",
            f"{names}: share of their team's targets and air yards, and {s.label} points per game",
            "SELECT ps.player_display_name AS player, ps.team, COUNT(*) AS games, SUM(ps.targets) AS targets, "
            "ROUND(100 * AVG(ps.target_share), 1) AS avg_target_share_pct, "
            "ROUND(100 * AVG(ps.air_yards_share), 1) AS avg_air_yards_share_pct, SUM(ps.carries) AS carries, "
            f"ROUND(AVG({pts}), 1) AS {s.key}_per_game "
            f"FROM NFLVERSE.player_stats ps WHERE ps.season = {season} AND ps.player_id IN ({ids}) "
            "GROUP BY ps.player_display_name, ps.team ORDER BY ps.player_display_name",
        ),
        PlannedQuery(
            "Recent trend",
            f"{names}: {s.label} points per game and target share in weeks 1-{mid} vs {mid + 1}-{latest_week}",
            f"SELECT ps.player_display_name AS player, {mid} AS split_week, "
            f"SUM(CASE WHEN ps.week <= {mid} THEN 1 ELSE 0 END) AS early_games, "
            f"SUM(CASE WHEN ps.week > {mid} THEN 1 ELSE 0 END) AS late_games, "
            f"ROUND(AVG(CASE WHEN ps.week <= {mid} THEN {pts} END), 1) AS early_{s.key}_per_game, "
            f"ROUND(AVG(CASE WHEN ps.week > {mid} THEN {pts} END), 1) AS late_{s.key}_per_game, "
            f"ROUND(100 * AVG(CASE WHEN ps.week <= {mid} THEN ps.target_share END), 1) AS early_target_share_pct, "
            f"ROUND(100 * AVG(CASE WHEN ps.week > {mid} THEN ps.target_share END), 1) AS late_target_share_pct "
            f"FROM NFLVERSE.player_stats ps WHERE ps.season = {season} AND ps.player_id IN ({ids}) "
            "GROUP BY ps.player_display_name ORDER BY ps.player_display_name",
        ),
        PlannedQuery(
            "Touchdown share",
            f"{names}: touchdowns and the share of {s.label} points that came from them",
            "SELECT ps.player_display_name AS player, "
            "SUM(ps.receiving_tds + ps.rushing_tds + ps.passing_tds) AS touchdowns, "
            "SUM(6 * (ps.receiving_tds + ps.rushing_tds) + 4 * ps.passing_tds) AS td_points, "
            f"ROUND(SUM({pts}), 1) AS {s.key}_points, "
            "ROUND(100 * SUM(6 * (ps.receiving_tds + ps.rushing_tds) + 4 * ps.passing_tds) "
            f"/ NULLIF(SUM({pts}), 0), 1) AS td_share_pct "
            f"FROM NFLVERSE.player_stats ps WHERE ps.season = {season} AND ps.player_id IN ({ids}) "
            "GROUP BY ps.player_display_name ORDER BY ps.player_display_name",
        ),
        matchup_query(players, season, latest_week, s, week),
    ]


def matchup_query(
    players: list[Player], season: int, latest_week: int, s: Scoring = PPR, week: int | None = None
) -> PlannedQuery:
    """Each player's opponent and that defense's average points allowed per game to the
    player's position, ranked (1 = most allowed), in the league's scoring.

    week: the week the question names; else the week after the latest stats week
    (latest_week + 1), not each team's next game, so a team with no game that week is on
    bye: Josh Allen's "this week" was week 7, a BUF bye, not BAL in week 8 (smoke run).
    A team with no game that week gets a row with no opponent (on bye); played = 1 when
    the game already has a score. opp_games is how many games the average is over.
    """
    names = " vs ".join(p.name for p in players)
    roster = " UNION ALL ".join(
        f"SELECT {_quote(p.player_id)} AS player_id, {_quote(p.name)} AS player, {_quote(p.team)} AS team, "
        f"{_quote(p.position if p.position in SKILL_POSITIONS else 'WR')} AS position, "
        f"{_quote(str(p.status or ''))} AS roster_status"
        for p in players
    )
    games = ("games AS (SELECT home_team AS team, away_team AS opponent, week, home_score FROM NFLVERSE.schedules "
             f"WHERE season = {season} "
             "UNION ALL SELECT away_team AS team, home_team AS opponent, week, home_score FROM NFLVERSE.schedules "
             f"WHERE season = {season})")
    week = latest_week + 1 if week is None else int(week)
    target = f"target AS (SELECT DISTINCT team, {week} AS week FROM players)"
    which = f"week {week} opponent"
    return PlannedQuery(
        "Next matchup",
        f"{names}: {which} and its average {s.label} points allowed per game to the position "
        "(rank 1 = most allowed)",
        f"WITH players AS ({roster}), {games}, {target}, "
        f"allowed AS (SELECT opponent_team, position, week, SUM({s.expr()}) AS pts "
        f"FROM NFLVERSE.player_stats WHERE season = {season} GROUP BY opponent_team, position, week), "
        f"avg_allowed AS (SELECT opponent_team, position, ROUND(AVG(pts), 1) AS avg_{s.key}_allowed, "
        "COUNT(*) AS opp_games FROM allowed GROUP BY opponent_team, position), "
        f"ranked AS (SELECT opponent_team, position, avg_{s.key}_allowed, opp_games, "
        f"RANK() OVER (PARTITION BY position ORDER BY avg_{s.key}_allowed DESC) AS allowed_rank, "
        "COUNT(*) OVER (PARTITION BY position) AS teams_ranked FROM avg_allowed) "
        "SELECT p.player, p.team, p.position, t.week AS game_week, g.opponent, "
        "CASE WHEN g.home_score IS NULL THEN 0 ELSE 1 END AS played, "
        f"r.avg_{s.key}_allowed AS opp_avg_{s.key}_allowed, r.allowed_rank, r.teams_ranked, r.opp_games, "
        "p.roster_status, i.report_status, i.report_primary_injury "
        "FROM players p LEFT JOIN target t ON t.team = p.team "
        "LEFT JOIN (SELECT gsis_id, week, MAX(report_status) AS report_status, "
        "MAX(report_primary_injury) AS report_primary_injury FROM NFLVERSE.injuries "
        f"WHERE season = {season} GROUP BY gsis_id, week) i ON i.gsis_id = p.player_id AND i.week = t.week "
        "LEFT JOIN games g ON g.team = p.team AND g.week = t.week "
        "LEFT JOIN ranked r ON r.opponent_team = g.opponent AND r.position = p.position "
        "ORDER BY p.player",
    )


def plan(
    question_type: str, player: Player, season: int, latest_week: int, scoring: Scoring = PPR,
    week: int | None = None,
) -> list[PlannedQuery]:
    """week: the week the question names, for the start/sit and waiver matchup."""
    if question_type == "why":
        return why_bundle(player, season, scoring)
    bundle = team_bundle(player, season, latest_week, scoring)
    if question_type == "replacement":
        bundle.append(games_without_query(player, season, scoring))
    if question_type in ("start_sit", "waiver"):
        bundle.append(matchup_query([player], season, latest_week, scoring, week))
    return bundle


# --- Summaries: the arithmetic is done in code, so the model only interprets ---


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(x: float | None) -> str:
    if x is None:
        return "n/a"
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def _avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _total(values) -> float:
    return round(sum(v for v in values if v is not None), 1)


def _pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole else None


class _Rows:
    def __init__(self, headers: list[str], rows: list[list]) -> None:
        self.headers, self.rows = headers, rows
        self.scoring = scoring_of(headers)
        self.points = f"{self.scoring.key}_points"  # the weekly points column

    def col(self, name: str) -> list[float | None]:
        if name not in self.headers:
            return [None] * len(self.rows)
        i = self.headers.index(name)
        return [_num(r[i]) for r in self.rows]

    def text(self, name: str) -> list[str]:
        if name not in self.headers:
            return [""] * len(self.rows)
        i = self.headers.index(name)
        return ["" if r[i] is None else str(r[i]) for r in self.rows]

    def early_late(self, name: str, label: str, unit: str = "") -> str | None:
        """Average of a column over the earlier vs the later half of the weeks played."""
        half = len(self.rows) // 2
        if half == 0:
            return None
        weeks, values = self.text("week"), self.col(name)
        early, late = range(half), range(half, len(self.rows))
        span = lambda idx: f"weeks {weeks[idx[0]]}-{weeks[idx[-1]]}" if len(idx) > 1 else f"week {weeks[idx[0]]}"
        a, b = _avg(values[i] for i in early), _avg(values[i] for i in late)
        return f"{label}: {_fmt(a)}{unit} in {span(early)} vs {_fmt(b)}{unit} in {span(late)}."


def summarize(factor: str, headers: list[str], rows: list[list]) -> list[str]:
    """Short factual lines computed from one planned query's rows."""
    if not rows:
        return ["No injury report entries this season." if factor == "Status" else "No rows."]
    fn = _SUMMARIES.get(factor)
    lines = fn(_Rows(headers, rows)) if fn else []
    return [line for line in lines if line]


def _lookup(t: _Rows) -> list[str]:
    return [
        f"{name}: {team}, {pos}, roster status {status} (week {week})."
        for name, team, pos, status, week in zip(
            t.text("full_name"), t.text("team"), t.text("position"), t.text("status"), t.text("week")
        )
    ]


def _status(t: _Rows) -> list[str]:
    week, status = t.text("week")[-1], t.text("report_status")[-1] or "no game status"
    injury = t.text("report_primary_injury")[-1]
    practice = t.text("practice_status")[-1] or "no practice entry"
    return [f"Latest injury report: week {week}, {status}{f' ({injury})' if injury else ''}; {practice}."]


def _opportunity(t: _Rows) -> list[str]:
    share, weeks = t.col("target_share_pct"), t.text("week")
    best = max(range(len(share)), key=lambda i: -1 if share[i] is None else share[i])
    carries = _total(t.col("carries"))
    runs = (f", {_fmt(carries)} carries ({_fmt(carries / len(t.rows))} per game)"
            if carries and carries / len(t.rows) >= MIN_CARRIES else "")
    return [
        f"{len(t.rows)} games, {_fmt(_total(t.col('targets')))} targets{runs}, average snap share "
        f"{_fmt(_avg(t.col('snap_pct')))}%, average target share {_fmt(_avg(share))}%, "
        f"{_fmt(_avg(t.col(t.points)))} {t.scoring.label} points per game.",
        f"Highest target share: week {weeks[best]} ({_fmt(share[best])}%).",
        t.early_late("snap_pct", "Snap share", "%"),
        t.early_late("target_share_pct", "Target share", "%"),
        t.early_late(t.points, f"{t.scoring.label} points per game"),
    ]


def _absences(t: _Rows) -> list[str]:
    by_week: dict[str, list[str]] = {}
    for week, name, pos, status in zip(t.text("week"), t.text("full_name"), t.text("position"), t.text("report_status")):
        by_week.setdefault(week, []).append(f"{name} ({pos}, {status})")
    return [f"Week {week}: {', '.join(names)}." for week, names in by_week.items()]


def _pass_rate(t: _Rows) -> list[str]:
    rate, margin = t.col("pass_rate_pct"), t.col("final_margin")
    losses = [r for r, m in zip(rate, margin) if m is not None and m < 0]
    others = [r for r, m in zip(rate, margin) if m is not None and m >= 0]
    return [
        f"Average pass rate {_fmt(_avg(rate))}%; {len(losses)} losses, {len(others)} wins or ties.",
        f"Pass rate {_fmt(_avg(losses))}% in losses vs {_fmt(_avg(others))}% in wins or ties."
        if losses and others else None,
        t.early_late("pass_rate_pct", "Pass rate", "%"),
    ]


def _big_plays(t: _Rows) -> list[str]:
    targets, yards = _total(t.col("targets")), _total(t.col("receiving_yards"))
    longest = max((x for x in t.col("longest_play") if x is not None), default=None)
    return [
        f"{_fmt(yards)} receiving yards on {_fmt(targets)} targets "
        f"({_fmt(round(yards / targets, 1) if targets else None)} yards per target); "
        f"{_fmt(_total(t.col('plays_20_plus')))} plays of 20+ yards; longest {_fmt(longest)}.",
        f"Average air yards share {_fmt(_avg(t.col('air_yards_share_pct')))}%.",
        t.early_late("yards_per_target", "Yards per target"),
    ]


def _touchdowns(t: _Rows) -> list[str]:
    rec, rush = t.col("receiving_tds"), t.col("rushing_tds")
    passing = t.col("passing_tds") if "passing_tds" in t.headers else [0] * len(rec)
    td_points, ppr = _total(t.col("td_points")), _total(t.col(t.points))
    rz, team_rz = _total(t.col("rz_targets")), _total(t.col("team_rz_targets"))
    weeks = [w for w, a, b, c in zip(t.text("week"), rec, rush, passing) if (a or 0) + (b or 0) + (c or 0) > 0]
    return [
        f"{_fmt(_total(rec) + _total(rush) + _total(passing))} touchdowns = {_fmt(td_points)} of {_fmt(ppr)} {t.scoring.label} points "
        f"({_fmt(_pct(td_points, ppr))}%). Scored in weeks: {', '.join(weeks) or 'none'}.",
        f"{_fmt(rz)} of the team's {_fmt(team_rz)} red-zone targets ({_fmt(_pct(rz, team_rz))}%); "
        f"{_fmt(_total(t.col('rz_carries')))} red-zone carries.",
    ]


def _matchups(t: _Rows) -> list[str]:
    ranks, ppr, label = t.col("allowed_rank"), t.col(t.points), t.scoring.label
    soft = [p for r, p in zip(ranks, ppr) if r is not None and r <= 10]
    rest = [p for r, p in zip(ranks, ppr) if r is not None and r > 10]
    return [
        f"Average opponent rank in {label} points allowed to the position: {_fmt(_avg(ranks))} of 32 (1 = most allowed).",
        f"{_fmt(_avg(soft))} {label} per game vs top-10 soft defenses ({len(soft)} games), "
        f"{_fmt(_avg(rest))} vs the rest ({len(rest)} games).",
    ]


def _team_usage(t: _Rows) -> list[str]:
    recent, names, pos = t.col("recent_target_share_pct"), t.text("player_display_name"), t.text("position")
    top = sorted(range(len(t.rows)), key=lambda i: -(recent[i] or 0))[:4]
    lines = ["Highest recent target share: " + "; ".join(f"{names[i]} ({pos[i]}) {_fmt(recent[i])}%" for i in top) + "."]
    carries, games = t.col("carries"), t.col("games")
    rbs = [i for i in range(len(t.rows)) if pos[i] == "RB" and carries[i] and games[i]]
    if rbs:
        lines.append("RB carries: " + "; ".join(
            f"{names[i]} {_fmt(carries[i])} in {_fmt(games[i])} games ({_fmt(round(carries[i] / games[i], 1))} per game)"
            for i in sorted(rbs, key=lambda i: -carries[i])[:3]) + ".")
    return lines


def _without(t: _Rows) -> list[str]:
    status, games = t.text("player_status"), t.col("games")
    missed = [i for i, s in enumerate(status) if s == "missed"]
    if not missed:
        return ["He played every team game this season; there are no games without him to compare."]
    played = {(t.text("player_display_name")[i]): i for i, s in enumerate(status) if s == "played"}
    names, pos, share = t.text("player_display_name"), t.text("position"), t.col("avg_target_share_pct")
    n_missed = int(max(games[i] or 0 for i in missed))
    top = sorted(missed, key=lambda i: -(share[i] or 0))[:4]

    def with_him(i: int) -> str:
        j = played.get(names[i])
        return f" (vs {_fmt(share[j])}% with him)" if j is not None else ""

    return [
        f"He missed {n_missed} team game{'s' if n_missed != 1 else ''} this season.",
        "Target share in the games he missed: "
        + "; ".join(f"{names[i]} ({pos[i]}) {_fmt(share[i])}%{with_him(i)}" for i in top) + ".",
    ]


def _by_player(t: _Rows) -> dict[str, list[int]]:
    """Row indexes per player, in the rows' order."""
    out: dict[str, list[int]] = {}
    for i, name in enumerate(t.text("player")):
        out.setdefault(name, []).append(i)
    return out


def _h2h_opportunity(t: _Rows) -> list[str]:
    lines = []
    for name, idx in _by_player(t).items():
        snap, share = t.col("snap_pct"), t.col("target_share_pct")
        targets, pts, carries = t.col("targets"), t.col(t.points), t.col("carries")
        runs = _avg(carries[i] for i in idx)
        rushing = (f", {_fmt(_total(carries[i] for i in idx))} carries ({_fmt(runs)} per game, "
                   f"{_fmt(_avg((targets[i] or 0) + (carries[i] or 0) for i in idx))} touches per game)"
                   if runs and runs >= MIN_CARRIES else "")
        lines.append(
            f"{name}: {len(idx)} games, {_fmt(_total(targets[i] for i in idx))} targets "
            f"({_fmt(_avg(targets[i] for i in idx))} per game){rushing}, average snap share {_fmt(_avg(snap[i] for i in idx))}%, "
            f"average target share {_fmt(_avg(share[i] for i in idx))}%, "
            f"{_fmt(_avg(pts[i] for i in idx))} {t.scoring.label} points per game."
        )
        weeks = t.text("week")
        lines.append(f"{name} {t.scoring.label} points by week: "
                     + ", ".join(f"week {weeks[i]} {_fmt(pts[i])}" for i in idx) + ".")
    return lines


def _h2h_usage(t: _Rows) -> list[str]:
    per_game = t.col(f"{t.scoring.key}_per_game")
    return [
        f"{name} ({team}): average target share {_fmt(share)}%, average air yards share {_fmt(air)}%, "
        f"{_fmt(targets)} targets and {_fmt(carries)} carries in {_fmt(games)} games, "
        f"{_fmt(ppg)} {t.scoring.label} points per game."
        for name, team, share, air, targets, carries, games, ppg in zip(
            t.text("player"), t.text("team"), t.col("avg_target_share_pct"), t.col("avg_air_yards_share_pct"),
            t.col("targets"), t.col("carries"), t.col("games"), per_game)
    ]


def _h2h_trend(t: _Rows) -> list[str]:
    key, label = t.scoring.key, t.scoring.label
    split = int(t.col("split_week")[0] or 0)
    lines = []
    for i, name in enumerate(t.text("player")):
        early, late = t.col(f"early_{key}_per_game")[i], t.col(f"late_{key}_per_game")[i]
        change = None if early is None or late is None else round(late - early, 1)
        sign = "" if change is None or change < 0 else "+"
        early_share, late_share = t.col("early_target_share_pct")[i], t.col("late_target_share_pct")[i]
        # A QB has no target share: "target share 0% vs 0%" means nothing (QA, 26 October 2026).
        shares = (f"; target share {_fmt(early_share)}% vs {_fmt(late_share)}%"
                  if early_share or late_share else "")
        lines.append(
            f"{name}: {_fmt(early)} {label} points per game in weeks 1-{split} vs {_fmt(late)} from week "
            f"{split + 1} on ({sign}{_fmt(change)}){shares}."
        )
    return lines


def _h2h_touchdowns(t: _Rows) -> list[str]:
    return [
        f"{name}: {_fmt(tds)} touchdown{'' if tds == 1 else 's'} = {_fmt(td)} of {_fmt(total)} {t.scoring.label} points ({_fmt(share)}% "
        "from touchdowns)."
        for name, tds, td, total, share in zip(t.text("player"), t.col("touchdowns"), t.col("td_points"),
                                               t.col(t.points), t.col("td_share_pct"))
    ]


def _h2h_matchup(t: _Rows) -> list[str]:
    allowed = next((h for h in t.headers if h.startswith("opp_avg_")), "")
    lines = []
    for i, (name, team, pos, week, opp) in enumerate(zip(
            t.text("player"), t.text("team"), t.text("position"), t.text("game_week"), t.text("opponent"))):
        if not week:
            lines.append(f"{name} ({team}) has no game left on the schedule.")
            continue
        if not opp:
            lines.append(f"{name} ({team}) is on bye in week {week}.")
            continue
        played = (t.col("played")[i] or 0) >= 1
        head = (f"{name} ({team}) already played {opp} in week {week} (that game is in the data)" if played
                else f"{name} ({team}) plays {opp} in week {week}")
        avg, rank = t.col(allowed)[i], t.col("allowed_rank")[i]
        if avg is None:
            lines.append(f"{head}; there is no {t.scoring.label} points-allowed data for {opp} yet.")
            continue
        teams, games = t.col("teams_ranked")[i], t.col("opp_games")[i]
        lines.append(
            f"{head}: {opp} allow {_fmt(avg)} {t.scoring.label} points per game to {pos}s "
            f"(rank {_fmt(rank)} of {_fmt(teams)}, 1 = most allowed; from {_fmt(games)} "
            f"game{'' if games == 1 else 's'} so far)."
        )
    return lines


def _depth(t: _Rows) -> list[str]:
    """ "TE depth chart: 1. Trey McBride (TE1), 2. ...": positions spelled out, so no one
    is called a WR1 by mistake."""
    pos = (t.text("pos_abb") or [""])[0]
    return [f"{pos} depth chart: " + ", ".join(
        f"{r}. {n} ({pos}{r})" for r, n in zip(t.text("pos_rank"), t.text("player_name"))) + "."]


def _last_names(t: _Rows) -> list[str]:
    points = next((h for h in t.headers if h.startswith("season_") and h.endswith("_points")), "")
    return [
        f"{name}: {team}, {pos}, {_fmt(pts)} {t.scoring.label} points this season."
        for name, team, pos, pts in zip(t.text("full_name"), t.text("team"), t.text("position"),
                                        t.col(points) if points else [None] * len(t.rows))
    ]


# "WR1", "TE2": a position label, which must match the player's roster position.
POSITION_LABEL = re.compile(r"\b(QB|RB|WR|TE)(\d{1,2})\b")
_NAME_COLUMNS = (("full_name", "position"), ("player_display_name", "position"), ("player", "position"),
                 ("player_name", "pos_abb"))


def known_positions(tables: list[tuple[list[str], list[list]]]) -> dict[str, str]:
    """{player name: position} from every table with a name and a position column."""
    out: dict[str, str] = {}
    for headers, rows in tables:
        for name_col, pos_col in _NAME_COLUMNS:
            if name_col in headers and pos_col in headers:
                i, j = headers.index(name_col), headers.index(pos_col)
                for row in rows:
                    if row[i] and row[j] and str(row[j]) in SKILL_POSITIONS:
                        out.setdefault(str(row[i]), str(row[j]))
                break
    return out


def position_label_problems(text: str, positions: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """(sentence, label, player, position) for each "WR1"-style label whose player plays
    another position. The player is the nearest one named before the label in the same
    sentence, else the first named after it."""
    problems = []
    for sentence in sentences(text):
        labels = list(POSITION_LABEL.finditer(sentence))
        if not labels:
            continue
        named = []
        for name in positions:
            last = name_key(name).split()[-1:]
            for m in re.finditer(rf"\b{re.escape(last[0])}\b", sentence, re.I) if last else ():
                named.append((m.start(), name))
        for label in labels:
            before = [n for n in named if n[0] < label.start()]
            after = [n for n in named if n[0] > label.start()]
            who = max(before)[1] if before else (min(after)[1] if after else None)
            if who and positions[who] != label.group(1):
                problems.append((sentence, label.group(0), who, positions[who]))
    return problems


_SUMMARIES = {
    "Player lookup": _lookup,
    "Status": _status,
    "Opportunity": _opportunity,
    "Teammate absences": _absences,
    "Team pass rate and game script": _pass_rate,
    "Big plays": _big_plays,
    "Touchdowns and red zone": _touchdowns,
    "Matchups": _matchups,
    "Team usage": _team_usage,
    "Points per game": lambda t: [
        f"{n} ({pos}): {_fmt(g)} games, {_fmt(pt)} passing and {_fmt(rt)} rushing touchdowns, "
        f"{_fmt(v)} {t.scoring.label} points per game." for n, pos, g, pt, rt, v in zip(
            t.text("player_display_name"), t.text("position"), t.col("games"), t.col("passing_tds"),
            t.col("rushing_tds"), t.col(f"{t.scoring.key}_per_game"))],
    "Depth chart": _depth,
    "Last-name lookup": _last_names,
    "Games without the player": _without,
    "Weekly opportunity": _h2h_opportunity,
    "Team usage share": _h2h_usage,
    "Recent trend": _h2h_trend,
    "Touchdown share": _h2h_touchdowns,
    "Next matchup": _h2h_matchup,
}


# --- Rule-based ratings: the fallback when a factor agent's model call fails ---

RATED_FACTORS = (*WHY_FACTORS, "Team usage", "Points per game", "Depth chart", "Games without the player",
                 *COMPARE_FACTORS)


def _grade(value: float | None, strong: float, moderate: float, weak: float) -> str:
    if value is None:
        return "not supported"
    if value >= strong:
        return "strong"
    if value >= moderate:
        return "moderate"
    return "weak" if value >= weak else "not supported"


def _ppr_by_week(results: dict[str, tuple[list[str], list[list]]]) -> dict[str, float]:
    headers, rows = results.get("Opportunity", ([], []))
    t = _Rows(headers, rows)
    return {w: p for w, p in zip(t.text("week"), t.col(t.points)) if p is not None}


def _scoring(results: dict[str, tuple[list[str], list[list]]]) -> Scoring:
    """The scoring the planned queries used (they all use the same one)."""
    for headers, _ in results.values():
        s = scoring_of(headers)
        if s is not PPR:
            return s
    return PPR


def _split_gain(ppr: dict[str, float], weeks: set[str]) -> float | None:
    """PPR per game in the given weeks minus PPR per game in the other weeks."""
    inside = [p for w, p in ppr.items() if w in weeks]
    outside = [p for w, p in ppr.items() if w not in weeks]
    if not inside or not outside:
        return None
    return round(_avg(inside) - _avg(outside), 1)


def rule_rating(
    factor: str, results: dict[str, tuple[list[str], list[list]]], player: str | None = None
) -> tuple[str, str]:
    """(support, rule) for one factor from fixed thresholds over the query results.

    results maps factor name -> (headers, rows) for every planned query, since some
    rules compare this factor's weeks with the player's weekly PPR points.
    """
    headers, rows = results.get(factor, ([], []))
    t = _Rows(headers, rows)
    ppr = _ppr_by_week(results)
    label = _scoring(results).label
    if not rows and factor != "Teammate absences":
        return "not supported", "no rows"

    if factor == "Opportunity":
        share, snap = _avg(t.col("target_share_pct")), _avg(t.col("snap_pct"))
        support = _grade(share, 22, 15, 10)
        if support == "strong" and (snap or 0) < 70:
            support = "moderate"
        rule = f"average target share {_fmt(share)}% (strong >= 22 with snap share >= 70%, moderate >= 15, weak >= 10)"
        carries = _avg(t.col("carries")) if "carries" in t.headers else None
        by_carries = _grade(carries, 15, PICKUP_CARRIES, MIN_CARRIES)
        if GRADES.index(by_carries) < GRADES.index(support):
            support = by_carries
            rule += f"; carries per game {_fmt(carries)} (strong >= 15, moderate >= {_fmt(PICKUP_CARRIES)}, weak >= {_fmt(MIN_CARRIES)})"
        return support, rule
    if factor == "Teammate absences":
        gain = _split_gain(ppr, set(t.text("week")))
        return _grade(gain, 5, 2, 0.1), f"{label} per game in weeks with a teammate out minus other weeks: {_fmt(gain)} (strong >= 5, moderate >= 2, weak > 0)"
    if factor == "Team pass rate and game script":
        rate = dict(zip(t.text("week"), t.col("pass_rate_pct")))
        mean = _avg(rate.values())
        gain = _split_gain(ppr, {w for w, r in rate.items() if r is not None and mean is not None and r > mean})
        return _grade(gain, 5, 2, 0.1), f"{label} per game in above-average pass-rate weeks minus the rest: {_fmt(gain)} (strong >= 5, moderate >= 2, weak > 0)"
    if factor == "Big plays":
        targets, yards = _total(t.col("targets")), _total(t.col("receiving_yards"))
        ypt = round(yards / targets, 1) if targets else None
        return _grade(ypt, 10, 8.5, 7), f"{_fmt(ypt)} yards per target (strong >= 10, moderate >= 8.5, weak >= 7)"
    if factor == "Touchdowns and red zone":
        share = _pct(_total(t.col("td_points")), _total(t.col(t.points)))
        return _grade(share, 35, 25, 15), f"touchdowns are {_fmt(share)}% of {label} points (strong >= 35, moderate >= 25, weak >= 15)"
    if factor == "Matchups":
        soft = {w for w, r in zip(t.text("week"), t.col("allowed_rank")) if r is not None and r <= 10}
        gain = _split_gain(ppr, soft)
        return _grade(gain, 5, 2, 0.1), f"{label} per game vs top-10 soft defenses minus the rest: {_fmt(gain)} (strong >= 5, moderate >= 2, weak > 0)"
    if factor == "Team usage" and player:  # start/sit or waiver: his own share, not the team leader's (QA run)
        own = _usage(player, results, "recent_target_share_pct")
        return _grade(own, 20, 15, 0.1), f"{player}'s recent target share {_fmt(own)}% (strong >= 20, moderate >= 15)"
    if factor == "Team usage":
        top = max((x for x in t.col("recent_target_share_pct") if x is not None), default=None)
        return _grade(top, 20, 15, 0.1), f"highest recent target share {_fmt(top)}% (strong >= 20, moderate >= 15)"
    if factor == "Points per game":
        ppg = (t.col(f"{t.scoring.key}_per_game") or [None])[0]
        return _grade(ppg, 18, START_PPR, 6), f"{_fmt(ppg)} {label} points per game (strong >= 18, moderate >= {_fmt(START_PPR)}, weak >= 6)"
    if factor == "Depth chart":
        return ("moderate" if len(rows) >= 2 else "weak"), f"{len(rows)} players listed on the depth chart"
    if factor == "Next matchup":
        week, opp = (t.text("game_week") or [""])[0], (t.text("opponent") or [""])[0]
        if not opp:
            return "not supported", f"on bye in week {week}" if week else "no game left on the schedule"
        rank, teams = (t.col("allowed_rank") or [None])[0], (t.col("teams_ranked") or [None])[0]
        support = _grade(None if rank is None else 33 - rank, 25, 17, 9)  # rank 1-8 strong, 9-16, 17-24
        return support, (f"{opp} rank {_fmt(rank)} of {_fmt(teams)} in {label} points allowed to the position "
                         "(strong 1-8, moderate 9-16, weak 17-24, else not supported)")
    if factor == "Games without the player":
        missed = [g for s, g in zip(t.text("player_status"), t.col("games")) if s == "missed"]
        n = int(max(missed)) if missed else 0
        return _grade(n, 3, 2, 1), f"{n} games without him (strong >= 3, moderate 2, weak 1)"
    return "not supported", "no rule for this factor"


# (column, higher is better, strong, moderate, weak margins, what it measures) per head-to-head factor.
_H2H_RULES = {
    "Weekly opportunity": ("targets", True, 2, 1, 0.3, "targets per game"),
    "Team usage share": ("avg_target_share_pct", True, 5, 2.5, 1, "average target share"),
    "Recent trend": ("late_{key}_per_game", True, 4, 2, 0.5, "{label} points per game in the later weeks"),
    "Touchdown share": ("td_share_pct", False, 15, 8, 3, "share of points from touchdowns, lower is steadier"),
    "Next matchup": ("opp_avg_{key}_allowed", True, 5, 2, 0.5, "next opponent's {label} points allowed per game"),
}


def _runners(t: _Rows) -> bool:
    """Any player in the rows averages MIN_CARRIES+ carries: opportunity counts touches."""
    if "carries" not in t.headers:
        return False
    carries = t.col("carries")
    return any((_avg(carries[i] for i in idx) or 0) >= MIN_CARRIES for idx in _by_player(t).values())


def h2h_values(factor: str, headers: list[str], rows: list[list]) -> dict[str, float | None]:
    """The deciding value of a head-to-head factor per player (targets per game for Weekly opportunity)."""
    t = _Rows(headers, rows)
    column = _H2H_RULES[factor][0].format(key=t.scoring.key)
    by_player = _by_player(t)
    values = t.col(column)
    if factor == "Weekly opportunity" and _runners(t):  # QA run: RBs were rated on targets alone
        carries = t.col("carries")
        return {name: _avg((values[i] or 0) + (carries[i] or 0) for i in idx) for name, idx in by_player.items()}
    if factor == "Weekly opportunity":
        return {name: _avg(values[i] for i in idx) for name, idx in by_player.items()}
    return {name: values[idx[0]] for name, idx in by_player.items()}


def compare_rating(factor: str, results: dict[str, tuple[list[str], list[list]]]) -> tuple[str, str, str]:
    """(favours: a player's name or EVEN, support, rule) for one head-to-head factor, from fixed margins."""
    headers, rows = results.get(factor, ([], []))
    values = h2h_values(factor, headers, rows) if rows else {}
    known = {n: v for n, v in values.items() if v is not None}
    column, higher, strong, moderate, weak, what = _H2H_RULES[factor]
    t = _Rows(headers, rows)
    if factor == "Weekly opportunity" and rows and _runners(t):
        strong, moderate, weak, what = 4, 2, 0.5, "touches (targets + carries) per game"
    if factor == "Next matchup" and len(set(t.text("position"))) > 1:
        # Different positions (QA run: RB vs WR points allowed): compare the ranks, lower is easier.
        by_player = _by_player(t)
        values = {n: t.col("allowed_rank")[idx[0]] for n, idx in by_player.items()}
        known = {n: v for n, v in values.items() if v is not None and t.text("opponent")[by_player[n][0]]}
        column, higher, strong, moderate, weak = "allowed_rank", False, 10, 5, 3
        what = "next opponent's rank against each player's position (1 = most points allowed, lower is easier)"
    label = scoring_of(headers).label
    what = what.format(label=label)
    if len(known) < 2:
        return EVEN, "not supported", f"{what}: not available for both players"
    (a, va), (b, vb) = sorted(known.items(), key=lambda kv: kv[1], reverse=higher)[:2]
    margin = round(abs(va - vb), 1)
    support = _grade(margin, strong, moderate, weak)
    u = "%" if column.endswith("_pct") else ""  # a share is always written with its % sign
    rule = (f"{what}: {a} {_fmt(va)}{u} vs {b} {_fmt(vb)}{u}; margin {_fmt(margin)}{u} "
            f"(strong >= {_fmt(strong)}{u}, moderate >= {_fmt(moderate)}{u}, weak >= {_fmt(weak)}{u}, else even)")
    return (EVEN if support == "not supported" else a), support, rule


# --- Rule-based verdict: the fallback when the verdict model call fails ---

START_PPR = 12.0  # points per game (in the league's scoring) at or above which a start/sit rule says start
PICKUP_SHARE = 15.0  # recent target share (%) at or above which a waiver rule says pick up
PICKUP_CARRIES = 10.0  # carries per game at or above which a waiver rule says pick up an RB (QA run)
MIN_CARRIES = 6.0  # carries per game below which carries are not quoted or rated
GRADES = ("strong", "moderate", "weak", "not supported")


def _carries_per_game(player: Player, results: dict[str, tuple[list[str], list[list]]]) -> float | None:
    """An RB's carries per game from the Team usage rows; None for other positions."""
    if player.position != "RB":
        return None
    carries, games = _usage(player, results, "carries"), _usage(player, results, "games")
    return round(carries / games, 1) if carries is not None and games else None
PPG_MARGIN = 0.5  # points per game closer than this are level (compare_verdict, critic check (g))


# A sentence ends at . ! or ? before a capital or "(", but not after "Sr." / "Jr." or a
# numbered-list marker (": 1." / ", 2." as in "Depth order: 1. Mike Evans, 2. ...").
SENTENCE_BREAK = re.compile(r"(?<!\bSr\.)(?<!\bJr\.)(?<!\bSt\.)(?<!\b[A-Z]\.)(?<!: \d\.)(?<!, \d\.)(?<!, \d\d\.)(?<=[.!?])\s+(?=[A-Z(])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_BREAK.split(text.strip()) if s.strip()]


def _first_sentence(text: str) -> str:
    parts = sentences(text)
    return parts[0].rstrip(".") if parts else ""


MIN_GAMES = 2  # a stand-in's usage needs at least this many games (QA run: picks rested on one game)


def depth_below(player: Player, results: dict[str, tuple[list[str], list[list]]]) -> list[str]:
    """The depth chart's names ranked below the player (all of them if he is not listed)."""
    names = _Rows(*results.get("Depth chart", ([], []))).text("player_name")
    at = next((i for i, n in enumerate(names) if same_player(n, player.name)), -1)
    return names[at + 1:]


def stand_in_pool(
    player: Player, results: dict[str, tuple[list[str], list[list]]], exclude: tuple[str, ...] = ()
) -> list[tuple[str, float | None, str]]:
    """(name, value, what) for each player who could take his place, best first: the same
    position (the depth chart is his position's), ranked below him, not Out or on reserve,
    not on the user's roster (exclude). RBs are ordered by carries, WRs and TEs by recent
    target share, QBs by the depth chart; usage from fewer than MIN_GAMES games does not
    count. QA run: McCaffrey out got Mike Evans, Godwin out got Egbuka (ranked above him)."""
    d = _Rows(*results.get("Depth chart", ([], [])))
    unavailable_names = {n for n, roster, report in zip(d.text("player_name"), d.text("roster_status"), d.text("report_status"))
                         if (report or "").lower() == "out" or roster in UNAVAILABLE_ROSTER}
    u = _Rows(*results.get("Team usage", ([], [])))
    # Without a depth chart (the query failed), his position's players in the usage rows.
    ranked = depth_below(player, results) if d.rows else [
        n for n, pos in zip(u.text("player_display_name"), u.text("position"))
        if pos == player.position and not same_player(n, player.name)]
    below = [n for n in ranked if n not in unavailable_names and not any(same_player(n, x) for x in exclude)]
    column, what = {"RB": ("carries", "carries"), "QB": (None, "")}.get(
        player.position, ("recent_target_share_pct", "recent target share"))
    values = {}
    if column and column in u.headers:
        for n, v, g in zip(u.text("player_display_name"), u.col(column), u.col("games")):
            if v is not None and (g or 0) >= MIN_GAMES:
                values[n] = v
    pool = [(n, next((v for x, v in values.items() if same_player(x, n)), None), what) for n in below]
    return sorted(pool, key=lambda r: -(r[1] if r[1] is not None else -1)) if column else pool


def _next_up(
    player: Player, results: dict[str, tuple[list[str], list[list]]], exclude: tuple[str, ...] = ()
) -> tuple[str | None, str]:
    """(stand-in, reason): the top of stand_in_pool. Players in exclude (already on the
    user's roster) are skipped."""
    pool = stand_in_pool(player, results, exclude)
    if not pool:
        return None, ""
    name, value, what = pool[0]
    pos = player.position
    below = depth_below(player, results)
    nxt = below[0] if below else None
    if value is None:
        return name, f"{name} is the next {pos} below {player.name} on the depth chart who can play."
    unit = "%" if "share" in what else f" {what}"
    among = f"{pos}s below {player.name} on the depth chart" + (" not already on your roster" if exclude else "")
    reason = f"{name} has the most {what} among the {among} ({_fmt(value)}{unit})."
    u = _Rows(*results.get("Team usage", ([], [])))
    row = next((i for i, n in enumerate(u.text("player_display_name")) if same_player(n, name)), None)
    if row is not None:
        reason += _per_game(u, row, "this season")
    if nxt and not same_player(nxt, name):
        reason += f" {nxt} is next on the depth chart."
    return name, reason


def _per_game(t: _Rows, i: int, when: str) -> str:
    """" He averages 15.6 half-PPR points per game this season." from a *_per_game column."""
    value = t.col(f"{t.scoring.key}_per_game")[i]
    return f" He averages {_fmt(value)} {t.scoring.label} points per game {when}." if value is not None else ""


def _usage(player: Player | str, results, column: str) -> float | None:
    """The player's value in the Team usage rows (a QB's in his Points per game row)."""
    wanted = player if isinstance(player, str) else player.name
    for factor in ("Team usage", "Points per game"):
        t = _Rows(*results.get(factor, ([], [])))
        if column not in t.headers:
            continue
        for name, value in zip(t.text("player_display_name"), t.col(column)):
            if same_player(name, wanted):
                return value
    return None


NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name: str) -> str:
    """'Deebo Samuel Sr.' and 'deebo samuel' -> 'deebo samuel' (sources disagree on suffixes)."""
    tokens = re.sub(r"[^a-z ]", " ", name.lower().replace("'", "")).split()
    return " ".join(t for t in tokens if t not in NAME_SUFFIXES)


def same_player(a: str, b: str) -> bool:
    return bool(name_key(a)) and name_key(a) == name_key(b)


def replacement_lead(player: Player, results: dict[str, tuple[list[str], list[list]]], verdict: str) -> str | None:
    """A replacement answer's first sentence: the literal question, then the fantasy advice.

    "Deebo Samuel is next at WR on the depth chart, but the target share points to
    George Kittle (24.9%), so for fantasy: pick up George Kittle if available."
    None without a depth chart row to answer from.
    """
    depth = depth_below(player, results)  # next = the first ranked below him, not the top of the chart
    if not depth:
        return None
    advice = verdict.strip().rstrip(".")
    advice = advice[:1].lower() + advice[1:]
    m = re.match(r"(?:pick up|add|start)\s+(.+?)(?:\s+if available)?$", advice, re.I)
    pick = m.group(1) if m else None
    pool = {n: (v, what) for n, v, what in stand_in_pool(player, results)}
    value, what = next(((v, w) for n, (v, w) in pool.items() if pick and same_player(n, pick)), (None, ""))
    shown = (f"{_fmt(value)}%" if "share" in what else f"{_fmt(value)} {what}") if value is not None else None
    lead = f"{depth[0]} is next at {player.position} on the depth chart"
    if pick and same_player(pick, depth[0]):
        lead += f" ({shown} {what})" if shown and "share" in what else f" ({shown})" if shown else ""
    elif pick and shown:
        lead += f", but the {what} points to {pick} ({shown})"
    return f"{lead}, so for fantasy: {advice}."


def compare_verdict(
    players: list[Player], results: dict[str, tuple[list[str], list[list]]], question: str = ""
) -> tuple[str, str]:
    """(verdict, why): start the player with more points per game in the league's scoring;
    within 0.5 points, the one scoring more in the later weeks (Recent trend). With three or
    more players, every one is ranked ("Start A over B and C"). A player on bye, Out, on
    reserve, or out as the question says cannot score; when none can play, the verdict says so."""
    usage = results.get("Team usage share", ([], []))
    label = _scoring(results).label
    ppg = _per_game_by_player(usage) if usage[1] else {}
    late = h2h_values("Recent trend", *results["Recent trend"]) if results.get("Recent trend", ([], []))[1] else {}
    names = [_row_name(p.name, ppg) for p in players]
    away = unavailable(results, question)
    off = {n: next(r for x, r in away.items() if same_player(n, x)) for n in names
           if any(same_player(n, x) for x in away)}
    able = [n for n in names if n not in off]
    if not able:
        reasons = "; ".join(f"{n} {r}" for n, r in off.items())
        return f"Sit {' and '.join(names)}: neither plays", f"Rule: {reasons}. Decided by availability."
    if off:
        why_off = "; ".join(f"{n} {r}" for n, r in off.items())
        if len(able) == 1:
            return (f"Start {able[0]} over {' and '.join(off)}", f"Rule: {why_off}. Decided by availability.")
        verdict, why = compare_verdict([p for p in players if _row_name(p.name, ppg) in able], results, question)
        return f"{verdict} and {' and '.join(off)}", f"Rule: {why_off}. {why}"
    if len(names) > 2:
        ranked = sorted(names, key=lambda n: -(ppg.get(n) if ppg.get(n) is not None else -1))
        top, second = ranked[0], ranked[1]
        if ppg.get(top) is not None and ppg.get(second) is not None and ppg[top] - ppg[second] < 0.5:
            lt, ls = late.get(_row_name(top, late)), late.get(_row_name(second, late))
            if (ls or 0) > (lt or 0):
                ranked[0], ranked[1] = second, top
        listing = ", ".join(f"{n} {_fmt(ppg.get(n))}" for n in ranked)
        return (f"Start {ranked[0]} over {' and '.join(ranked[1:])}",
                f"Rule: start the player with the most {label} points per game: {listing}. Decided by points per game.")
    (a, b) = names[:2]
    pa, pb = ppg.get(a), ppg.get(b)
    decided_by = "points per game"
    if pa is None or pb is None or abs(pa - pb) < 0.5:
        la, lb = late.get(_row_name(a, late)), late.get(_row_name(b, late))
        start, bench = (a, b) if (la or 0) >= (lb or 0) else (b, a)
        decided_by = "recent trend"
        why = (f"Rule: start the player with more {label} points per game ({a} {_fmt(pa)} vs {b} {_fmt(pb)}); "
               f"they are within 0.5, so the later weeks decide: {a} {_fmt(la)} vs {b} {_fmt(lb)} per game.")
    else:
        start, bench = (a, b) if pa > pb else (b, a)
        why = f"Rule: start the player with more {label} points per game: {a} {_fmt(pa)} vs {b} {_fmt(pb)}."
    return f"Start {start} over {bench}", f"{why} Decided by {decided_by}."


def matchup_label(rank: float | None, teams: float | None = 32) -> str | None:
    """favorable, neutral or tough, by the opponent's points-allowed rank (1 = allows the
    most): ranks 1-10 of 32 favorable, 11-22 neutral, 23-32 tough (scaled for other counts)."""
    if rank is None:
        return None
    r = rank * 32 / teams if teams else rank
    return "favorable" if r <= 10 else "neutral" if r <= 22 else "tough"


UNAVAILABLE_ROSTER = {"RES": "is on reserve (RES)", "CUT": "is not on a roster (CUT)", "SUS": "is suspended (SUS)"}


QUESTION_OUT = "is out, as the question says"


def unavailable(results: dict[str, tuple[list[str], list[list]]], question: str = "") -> dict[str, str]:
    """{player: why he cannot play} in the matchup week: on bye, listed Out, or on reserve
    (QA run: Monangai, Out in week 7, and Adams, RES, both got "Start"); with the question,
    also any player it says is out, whichever player he is named as ("Kittle or Evans if
    Evans is out?" started Evans; QA 26 October 2026)."""
    t = _Rows(*results.get("Next matchup", ([], [])))
    out = {name: f"is on bye in week {week}" for name, week in on_bye(results).items()}
    statuses = zip(t.text("player"), t.text("game_week"), t.text("report_status"), t.text("report_primary_injury"),
                   t.text("roster_status"))
    for name, week, report, injury, roster in statuses:
        if name in out:
            continue
        if report and report.lower() == "out":
            out[name] = f"is listed Out for week {week}" + (f" ({injury.lower()})" if injury else "")
        elif roster in UNAVAILABLE_ROSTER:
            out[name] = UNAVAILABLE_ROSTER[roster]
        elif question and says_out(question, name):
            out[name] = QUESTION_OUT
    return out


def on_bye(results: dict[str, tuple[list[str], list[list]]]) -> dict[str, str]:
    """{player: week} for each player on bye in the matchup week."""
    t = _Rows(*results.get("Next matchup", ([], [])))
    return {name: week for name, week, opp in zip(t.text("player"), t.text("game_week"), t.text("opponent"))
            if week and not opp}


def status_verdict(
    player: Player, results: dict[str, tuple[list[str], list[list]]], question: str = ""
) -> tuple[str, str]:
    """"No: he is listed Out for week 7 (thumb)" from the injury report and roster status;
    "Is X out?" gets "Yes" for the same facts."""
    asks_out = re.search(r"\b(?:out|injured|hurt|inactive)\b", question, re.I) is not None
    week = _week(results)
    away = next((r for n, r in unavailable(results).items() if same_player(n, player.name)), None)
    t = _Rows(*results.get("Status", ([], [])))
    entry = next((i for i, w in enumerate(t.text("week")) if w == week), None)
    practice = t.text("practice_status")[entry] if entry is not None else ""
    report = t.text("report_status")[entry] if entry is not None else ""
    source = f"Source: the week {week} injury report and the rosters table."
    if away:
        return f"{'Yes' if asks_out else 'No'}: {player.name} {away}", f"{source} Sit {player.name}."
    status = f"listed {report} for week {week}" if report else f"has no game status on the week {week} injury report"
    detail = f" ({practice})" if practice else ""
    lead = "Probably not" if report in ("Doubtful",) else "Questionable" if report == "Questionable" else "Yes"
    lead = {"Yes": "No", "Probably not": "Probably"}.get(lead, lead) if asks_out else lead
    return f"{lead}: {player.name} {status}{detail}", source


def _line_for(text: str, name: str) -> str:
    """The summary sentence about this player ("Bijan Robinson: 6 games, ..."), else the first."""
    full, last = name_key(name), name_key(name).split()[-1:]
    parts = sentences(text)
    for s in parts:  # the full name first: "Kyren Williams", not "Javonte Williams"
        if full and full in name_key(s):
            return s.rstrip(".")
    for s in parts:
        if last and re.search(rf"\b{re.escape(last[0])}\b", name_key(s)):
            return s.rstrip(".")
    return _first_sentence(text)


def _backing(pick: str, ranked: list[tuple[str, str, str]], favours: dict[str, str | None], ruled_out: list[str]) -> str:
    """"Most supported by the data for <pick>: ..." with only the factors that favour him (QA run:
    the list quoted the other player's lines)."""
    mine = [(f, s, text) for f, s, text in ranked
            if s in ("strong", "moderate") and favours.get(f) and same_player(str(favours[f]), pick)]
    reasons = "; ".join(f"{f} ({s}): {_line_for(text, pick)}" for f, s, text in mine[:3])
    why = f"Most supported by the data for {pick}: {reasons}." if reasons else f"No factor strongly favours {pick}."
    return why + (f" Not supported: {', '.join(ruled_out)}." if ruled_out else "")


def _week(results: dict[str, tuple[list[str], list[list]]]) -> str:
    return (_Rows(*results.get("Next matchup", ([], []))).text("game_week") or ["the next"])[0]


def matchup_lines(results: dict[str, tuple[list[str], list[list]]]) -> str:
    rows = results.get("Next matchup", ([], []))
    return " ".join(summarize("Next matchup", *rows)) if rows[1] else ""


def _with_matchup(why: str, results: dict[str, tuple[list[str], list[list]]]) -> str:
    """The rule-based why, with the matchup lines unless they are already quoted."""
    lines = matchup_lines(results)
    return f"{why} {lines}" if lines and "Next matchup (" not in why else why


def _per_game_by_player(usage: tuple[list[str], list[list]]) -> dict[str, float | None]:
    t = _Rows(*usage)
    return dict(zip(t.text("player"), t.col(f"{t.scoring.key}_per_game")))


def _row_name(name: str, by_name: dict[str, Any]) -> str:
    """The data's spelling of a player's name ("Deebo Samuel Sr." for "Deebo Samuel")."""
    return next((n for n in by_name if same_player(n, name)), name)


def rule_verdict(
    question_type: str, player: Player, results: dict[str, tuple[list[str], list[list]]],
    ranked: list[tuple[str, str, str]], roster: tuple[str, ...] = (), out: bool = False,
    players: list[Player] | None = None, question: str = "", favours: dict[str, str | None] | None = None,
) -> tuple[str, str]:
    """(verdict, why) from fixed rules; ranked is (factor, support, summary), most supported first.

    roster: names already on the user's roster, never recommended as a pickup.
    out: the question says this player is out, so a pickup or start never names him: the
    stand-in rule (as for a replacement question) picks who to add instead.
    """
    backed = [(f, s, text) for f, s, text in ranked if s in ("strong", "moderate")]
    own = _usage(player, results, "recent_target_share_pct") if question_type in ("start_sit", "waiver") else None
    own_line = f"{player.name}'s recent target share is {_fmt(own)}%" if own is not None else None
    reasons = "; ".join(f"{f} ({s}): {own_line if f == 'Team usage' and own_line else _line_for(text, player.name)}"
                        for f, s, text in backed[:3])
    why = f"Most supported by the data: {reasons}." if reasons else "No factor is strongly supported by the data."
    ruled_out = [f for f, s, _ in ranked if s == "not supported"]
    if ruled_out:
        why += f" Not supported: {', '.join(ruled_out)}."

    if question_type == "unsupported":
        topic = unsupported_topic(question) or "this question"
        if players and len(players) >= 2:
            verdict, rule = compare_verdict(players, results, question)
            verdict = f"{unsupported_message(topic)} For week {_week(results)} only: {verdict[:1].lower()}{verdict[1:]}"
            return verdict, _with_matchup(f"{why} {rule}", results)
        verdict, why = rule_verdict("start_sit", player, results, ranked)
        return f"{unsupported_message(topic)} For week {_week(results)} only: {verdict[:1].lower()}{verdict[1:]}", why
    if question_type == "status":
        return status_verdict(player, results, question)
    if question_type == "compare" and players and len(players) >= 2:
        verdict, rule = compare_verdict(players, results, question)
        if favours is not None and verdict.startswith("Start "):
            why = _backing(verdict.removeprefix("Start ").split(" over ")[0], ranked, favours, ruled_out)
        why += f" {rule}"
        why = _with_matchup(why, results)
    elif question_type == "replacement" or (out and question_type in ("start_sit", "waiver")):
        stand_in, reason = _next_up(player, results, roster)
        verdict = f"Pick up {stand_in} if available" if stand_in else f"Hold until {player.team}'s next depth chart"
        why = f"{why} {reason}" if reason else why
    elif question_type == "start_sit":
        s = _scoring(results)
        ppr = _usage(player, results, f"{s.key}_per_game")
        away = next((r for n, r in unavailable(results).items() if same_player(n, player.name)), None)
        if away:
            verdict = f"Sit {player.name}"
            why += f" Rule: he {away}."
        else:
            verdict = f"{'Start' if ppr is not None and ppr >= START_PPR else 'Sit'} {player.name}"
            why += f" Rule: start at {_fmt(START_PPR)}+ {s.label} per game; he averages {_fmt(ppr)}."
        why = _with_matchup(why, results)
    elif question_type == "waiver" and DROP_CUE.search(question or ""):
        # "Should I drop Dalton Kincaid?": keep or drop, never "Pick up" (QA run).
        s = _scoring(results)
        share = _usage(player, results, "recent_target_share_pct")
        ppr = _usage(player, results, f"{s.key}_per_game")
        runs = _carries_per_game(player, results)
        keep = (share is not None and share >= PICKUP_SHARE) or (ppr is not None and ppr >= START_PPR) or (
            runs is not None and runs >= PICKUP_CARRIES)
        verdict = f"{'Keep' if keep else 'Drop'} {player.name}"
        if runs is not None:
            why += (f" Rule: keep at {_fmt(PICKUP_SHARE)}%+ recent target share, {_fmt(PICKUP_CARRIES)}+ carries per game "
                    f"or {_fmt(START_PPR)}+ {s.label} per game; his are {_fmt(share)}%, {_fmt(runs)} and {_fmt(ppr)}.")
        else:
            why += (f" Rule: keep at {_fmt(PICKUP_SHARE)}%+ recent target share or {_fmt(START_PPR)}+ {s.label} per game; "
                    f"his are {_fmt(share)}% and {_fmt(ppr)}.")
        why = _with_matchup(why, results)
    elif question_type == "waiver":
        share = _usage(player, results, "recent_target_share_pct")
        if any(same_player(player.name, x) for x in roster):
            verdict = f"Hold {player.name} (already on your roster)"
        runs = _carries_per_game(player, results)
        busy = (share is not None and share >= PICKUP_SHARE) or (runs is not None and runs >= PICKUP_CARRIES)
        if not any(same_player(player.name, x) for x in roster):
            verdict = f"{'Pick up' if busy else 'Hold off on'} {player.name}"
        if runs is not None:
            why += (f" Rule: pick up at {_fmt(PICKUP_SHARE)}%+ recent target share or, for an RB, "
                    f"{_fmt(PICKUP_CARRIES)}+ carries per game; his are {_fmt(share)}% and {_fmt(runs)}.")
        else:
            why += f" Rule: pick up at {_fmt(PICKUP_SHARE)}%+ recent target share; his is {_fmt(share)}%."
        why = _with_matchup(why, results)
    elif question_type == "why":
        verdict = f"Hold {player.name}"
    else:
        # An unrecognised question never gets "Hold <player>" (QA run): say what can be answered.
        verdict = f"No call on {player.name}"
        why = (f"I can't tell which decision this asks about; ask whether to start, sit, pick up or drop "
               f"{player.name}. {why}")
    return verdict, why
