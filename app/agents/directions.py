"""Factor direction, computed in code: who or what each factor's numbers favour.

The factor agents get these lines as facts ("Target share fell: 25.8% in weeks 1-3 vs
18.6% in weeks 4-6."; "Next matchup: George Pickens has the easier matchup ..."), and
analyst._rate_factors replaces a model summary that contradicts them with the code
summary. The Critic runs the same text checks on the answer (check_directions).

A summary contradicts the numbers when it:
- says a head-to-head factor favours the player the code rule does not
- uses "higher"/"more" for the lower number of a pair ("31.9% vs 34.1%"), or the reverse
- calls the worse side of a pair "easier" or "steadier", by the metric's polarity (POLARITY)
- says a value rose "from A to B" when B < A, or the reverse
- says a share rose (or fell) when the code computed the opposite
- says a player ranks above one with a higher share
- gives the easier matchup to the player whose opponent allows fewer points
- calls a matchup easy or favorable when its code label is tough, or tough when it is
  favorable, or "top-third"/"bottom-third" when that is not its label (matchup_label:
  ranks 1-10 of 32 favorable, 11-22 neutral, 23-32 tough; rank 1 allows the most)
- quotes a number that is not in the rows or the computed facts (factor summaries only:
  unknown_numbers, as the Critic's numbers check)

"He" or "his" is the sentence's first-named player: in "Bowers also outperforms ...
versus Pickens's 16.9, and he faces a significantly easier matchup" he is Bowers.

Only unambiguous words are checked. A vague one ("edge", "advantage", "better",
"leads") does not say which number is which, so it is never checked, and it ends the
reach of an earlier word: in "a higher average that outweighs his touchdown share edge
(17.5% vs 21.9%)" the "higher" is not read against 17.5 vs 21.9 (run c6522e90539f).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agents import factor_queries as fq
from app.agents.factor_queries import EVEN, _avg, _fmt, _Rows, name_key, same_player, sentences

Results = dict[str, tuple[list[str], list[list]]]
FLAT = 0.5  # a gap under this (points or percentage points) is level: neither higher nor lower

# --- words ---

# A comparison word for a pair of numbers. Size words compare the numbers themselves;
# good/bad words ("easier", "steadier") compare them by the metric's polarity; vague words
# are not checked. "more/less <word>" is one unit: "less touchdown-dependent" is a size
# word, "more favorable" a good word, "more consistent" a vague one.
COMPARE = re.compile(
    r"\b(?P<good>easier|softer|friendlier|more\s+favou?rable|favou?rable|steadier|more\s+stable)\b"
    r"|\b(?P<bad>tougher|harder|stingier|less\s+favou?rable|riskier)\b"
    r"|\b(?P<vague>edges?|advantages?|better|worse|ahead|outpac\w*|leads?|leading|tops|trails?|trailing|behind"
    r"|stronger|weaker|(?:more|less)\s+(?:consistent|reliable|efficient|productive|valuable|explosive))\b"
    r"|\b(?P<moreless>more|less)\s+[\w-]+"
    r"|\b(?P<higher>higher|greater|larger|bigger)\b"
    r"|\b(?P<lower>lower|fewer|smaller)\b",
    re.I,
)
# Which number of a pair is the good side, by the metric named with it:
# (metric, pattern, the higher number is the good side?, what the good side is).
# In the allowed_rank column rank 1 allows the most points, so a lower rank number is
# the easier matchup.
POLARITY = [
    ("defense rank", re.compile(r"\brank", re.I), False, "easier matchup"),
    ("points allowed", re.compile(r"\ballow", re.I), True, "easier matchup"),
    ("touchdown share", re.compile(r"\btouchdown|\bTDs?\b", re.I), False, "steadier, less touchdown-dependent side"),
]
WORD_REACH = 60  # characters a comparison word reaches forward, not counting the pairs it already covers
RISE = re.compile(r"\b(?:rose|risen|rises?|rising|grew|grown|grows?|growing|increas(?:e[sd]?|ing)|jump(?:s|ed|ing)?"
                  r"|climb(?:s|ed|ing)?|spik(?:es|ed|ing)|surg(?:es|ed|ing)|boost(?:s|ed|ing)?|improv(?:e[sd]?|ing))\b", re.I)
FALL = re.compile(r"\b(?:fell|fallen|falls?|falling|drop(?:s|ped|ping)?|declin(?:e[sd]?|ing)|decreas(?:e[sd]?|ing)"
                  r"|shr(?:ank|inks?|inking)|dipp?(?:ed|ing)?|slipp?(?:ed|ing)?)\b", re.I)
EASIER = re.compile(r"\b(?:easier|softer|friendlier|more favou?rable|favou?rable|better matchup)\b", re.I)
TOUGHER = re.compile(r"\b(?:tougher|harder|tough|stingier|difficult|less favou?rable)\b", re.I)
AHEAD = re.compile(r"\b(?:rank(?:s|ed)?\s+(?:higher|above|ahead)|ahead of|outpac\w*|higher than)\b", re.I)
BEHIND = re.compile(r"\b(?:rank(?:s|ed)?\s+(?:lower|below|behind)|behind|trail(?:s|ed|ing)?|lower than)\b", re.I)
# Clauses are checked on their own: "McBride has the higher share, but Bowers ..." compares twice.
CLAUSE = re.compile(r";|:|,?\s+\b(?:but|while|whereas|although|though|yet)\b", re.I)
# "21.9% vs 15.2%", "26 half-PPR points to WRs versus PHI's 31.8"
PAIR = re.compile(
    r"(?<![\w.])(?P<a>\d+(?:\.\d+)?)\s*%?\)?(?P<gap>[^\d;:()]{0,45}?)\b(?:vs\.?|versus|compared (?:to|with))\s+"
    r"(?P<gap2>[^\d;:]{0,40}?)(?P<b>\d+(?:\.\d+)?)(?![\w])",
    re.I,
)
# "from 25.8% to 18.6%", "from 10.6 in weeks 1-3 to 13.9"
FROM_TO = re.compile(
    r"\bfrom\s+(?P<a>\d+(?:\.\d+)?)\s*%?(?:\s+in\s+weeks?\s+\d+(?:-\d+)?)?(?:\s+[a-zA-Z%-]+){0,4}?\s+to\s+"
    r"(?P<b>\d+(?:\.\d+)?)(?![\w])",
    re.I,
)
ELLIPSIS = re.compile(r"\.\.\.|…")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")
# Where the players a ranking word compares against end: "ahead of McCaffrey and Samuel, indicating ..."
LIST_END = re.compile(r",\s+(?=[a-z])|[.;]")
# metric -> words that name it in a summary
METRICS = {
    "target share": r"target share|share of (?:the )?targets",
    "snap share": r"snap (?:share|rate|count)|snaps",
    "yards per target": r"yards per target",
    "air yards share": r"air yards",
    "pass rate": r"pass(?:ing)? rate",
    "points per game": r"points per game|fantasy points|\bPPR\b|scoring",
}


@dataclass
class Directions:
    lines: list[str] = field(default_factory=list)  # facts for the prompts, computed in code
    favours: str | None = None  # head-to-head: the player the factor's code rule favours, or EVEN
    shares: dict[str, float] = field(default_factory=dict)  # player -> the factor's ranking value
    share_label: str = ""  # what shares hold ("recent target share")
    trends: dict[str, float] = field(default_factory=dict)  # metric -> change (later minus earlier, or with minus without)
    trend_label: str = ""  # what the trends compare, for the reason
    allowed: dict[str, float] = field(default_factory=dict)  # player -> next opponent's points allowed (higher = easier)
    matchups: dict[str, dict] = field(default_factory=dict)  # player -> {opp, rank, teams, label} (matchup_label)


def _direction(a: float | None, b: float | None, up: str = "higher", down: str = "lower", level: str = "level") -> str:
    if a is None or b is None or abs(a - b) < FLAT:
        return level
    return up if a > b else down


def _pct(column: str) -> str:
    return "%" if column.endswith("_pct") else ""


def _halves(t: _Rows, column: str) -> tuple[float | None, float | None, str, str] | None:
    """Average of a column over the earlier vs the later half of the weeks (as _Rows.early_late)."""
    half = len(t.rows) // 2
    if half == 0:
        return None
    weeks, values = t.text("week"), t.col(column)
    span = lambda idx: f"weeks {weeks[idx[0]]}-{weeks[idx[-1]]}" if len(idx) > 1 else f"week {weeks[idx[0]]}"
    early, late = range(half), range(half, len(t.rows))
    return _avg(values[i] for i in early), _avg(values[i] for i in late), span(early), span(late)


def directions(factor: str, results: Results, subject: str | None = None) -> Directions:
    """The direction facts for one factor, from all the planned queries' results."""
    headers, rows = results.get(factor, ([], []))
    d = Directions()
    if not rows and factor != "Teammate absences":
        return d
    t = _Rows(headers, rows)
    label = fq._scoring(results).label
    if factor in fq.COMPARE_FACTORS and len(fq._by_player(t)) >= 2:
        return _head_to_head(factor, t, results, d)
    if factor in ("Opportunity", "Big plays", "Team pass rate and game script"):
        columns = {
            "Opportunity": [("target_share_pct", "target share"), ("snap_pct", "snap share"),
                            (t.points, "points per game")],
            "Big plays": [("yards_per_target", "yards per target"), ("air_yards_share_pct", "air yards share")],
            "Team pass rate and game script": [("pass_rate_pct", "pass rate")],
        }[factor]
        d.trend_label = "from the earlier to the later weeks"
        for column, metric in columns:
            halves = _halves(t, column)
            if not halves or halves[0] is None or halves[1] is None:
                continue
            a, b, early, late = halves
            d.trends[metric] = round(b - a, 1)
            word = _direction(b, a, "rose", "fell", "held level")
            name = f"{label} points per game" if metric == "points per game" else metric[:1].upper() + metric[1:]
            u = _pct(column)
            d.lines.append(f"{name} {word}: {_fmt(a)}{u} in {early} vs {_fmt(b)}{u} in {late}.")
        if factor == "Team pass rate and game script":
            rate, margin = t.col("pass_rate_pct"), t.col("final_margin")
            losses = _avg(r for r, m in zip(rate, margin) if m is not None and m < 0)
            others = _avg(r for r, m in zip(rate, margin) if m is not None and m >= 0)
            if losses is not None and others is not None:
                d.lines.append(f"Pass rate is {_direction(losses, others)} in losses than in wins or ties "
                               f"({_fmt(losses)}% vs {_fmt(others)}%).")
    elif factor == "Teammate absences":
        _absence_weeks(t, results, d, label)
    elif factor == "Matchups":
        ranks, pts = t.col("allowed_rank"), t.col(t.points)
        soft = _avg(p for r, p in zip(ranks, pts) if r is not None and r <= 10)
        rest = _avg(p for r, p in zip(ranks, pts) if r is not None and r > 10)
        if soft is not None and rest is not None:
            d.lines.append(f"{label} points per game are {_direction(soft, rest)} against top-10 soft defenses "
                           f"than against the rest ({_fmt(soft)} vs {_fmt(rest)}).")
    elif factor == "Team usage":
        names, pos, share = t.text("player_display_name"), t.text("position"), t.col("recent_target_share_pct")
        d.shares = {n: s for n, s in zip(names, share) if s is not None}
        d.share_label = "recent target share"
        top = sorted(d.shares.items(), key=lambda kv: -kv[1])[:6]
        position = dict(zip(names, pos))
        d.lines.append("Ranked by recent target share, highest first: " + ", ".join(
            f"{i}. {n} ({position.get(n, '')}) {_fmt(s)}%" for i, (n, s) in enumerate(top, 1)) + ".")
    elif factor == "Games without the player":
        status, names, share = t.text("player_status"), t.text("player_display_name"), t.col("avg_target_share_pct")
        missed = {n: s for n, st, s in zip(names, status, share) if st == "missed" and s is not None}
        played = {n: s for n, st, s in zip(names, status, share) if st == "played" and s is not None}
        d.shares, d.share_label = missed, "target share in the games he missed"
        for n, s in sorted(missed.items(), key=lambda kv: -kv[1])[:4]:
            if n in played:
                d.lines.append(f"{n}'s target share was {_direction(s, played[n])} without him "
                               f"({_fmt(s)}% vs {_fmt(played[n])}% with him).")
    elif factor == "Next matchup":
        _matchup_labels(t, d)
    return d


def _matchup_labels(t: _Rows, d: Directions) -> None:
    """ "Brock Bowers's week 7 opponent LA: rank 31 of 32, tough matchup (...)." or a bye line."""
    for name, week, opp, rank, teams in zip(t.text("player"), t.text("game_week"), t.text("opponent"),
                                            t.col("allowed_rank"), t.col("teams_ranked")):
        if week and not opp:
            d.lines.append(f"{name} is on bye in week {week}: no game.")
            continue
        label = fq.matchup_label(rank, teams)
        if opp and label:
            d.matchups[name] = {"opp": opp, "rank": rank, "teams": teams, "label": label}
            d.lines.append(f"{name}'s week {week} opponent {opp}: rank {_fmt(rank)} of {_fmt(teams)}, {label} matchup "
                           "(rank 1 allows the most points; 1-10 favorable, 11-22 neutral, 23-32 tough).")


def _absence_weeks(t: _Rows, results: Results, d: Directions, label: str) -> None:
    """The player's numbers in the weeks a teammate was out vs the other weeks."""
    weeks = sorted(set(t.text("week")), key=lambda w: int(w) if w.isdigit() else 0)
    opp, big = _Rows(*results.get("Opportunity", ([], []))), _Rows(*results.get("Big plays", ([], [])))
    parts = []
    for rows, column, metric, unit in ((opp, "target_share_pct", "target share", "%"),
                                       (opp, opp.points, "points per game", ""),
                                       (big, "yards_per_target", "yards per target", "")):
        by_week = {w: v for w, v in zip(rows.text("week"), rows.col(column)) if v is not None}
        inside = _avg(v for w, v in by_week.items() if w in weeks)
        outside = _avg(v for w, v in by_week.items() if w not in weeks)
        if inside is None or outside is None:
            continue
        d.trends[metric] = round(inside - outside, 1)
        name = f"{label} points per game" if metric == "points per game" else metric
        parts.append(f"{name} {_fmt(inside)}{unit} vs {_fmt(outside)}{unit} ({_direction(inside, outside)})")
    if parts:
        d.trend_label = "in the weeks a teammate was out vs the other weeks"
        d.lines.append(f"In the weeks a teammate was out ({', '.join(weeks)}) vs the other weeks: " + "; ".join(parts) + ".")


# (column, label, how per-week rows combine) per head-to-head factor's compared metrics
_H2H_METRICS = {
    "Weekly opportunity": [("targets", "targets per game", "avg"), ("target_share_pct", "average target share", "avg"),
                           ("snap_pct", "average snap share", "avg"), ("{points}", "{label} points per game", "avg")],
    "Team usage share": [("avg_target_share_pct", "average target share", "first"),
                         ("avg_air_yards_share_pct", "average air yards share", "first"),
                         ("{key}_per_game", "{label} points per game", "first"), ("targets", "targets", "first")],
    "Recent trend": [("late_{key}_per_game", "{label} points per game in the later weeks", "first")],
    "Touchdown share": [],
    "Next matchup": [],
}


def _head_to_head(factor: str, t: _Rows, results: Results, d: Directions) -> Directions:
    key, label = t.scoring.key, t.scoring.label
    by_player = fq._by_player(t)
    names = list(by_player)[:2]
    for column, what, how in _H2H_METRICS[factor]:
        column = column.format(points=t.points, key=key)
        values = t.col(column)
        v = {n: (_avg(values[i] for i in by_player[n]) if how == "avg" else values[by_player[n][0]]) for n in names}
        a, b = names
        if v[a] is None or v[b] is None:
            continue
        u = _pct(column)
        lead = _direction(v[a], v[b], f"{a} higher", f"{b} higher", "level")
        what = what.format(label=label)
        d.lines.append(f"{what[:1].upper() + what[1:]}: {a} {_fmt(v[a])}{u} vs {b} {_fmt(v[b])}{u} ({lead}).")
    if factor == "Recent trend":
        split = int(t.col("split_week")[0] or 0)
        for name, early, late in zip(t.text("player"), t.col("early_target_share_pct"), t.col("late_target_share_pct")):
            if early is not None and late is not None:
                d.lines.append(f"{name}'s target share {_direction(late, early, 'rose', 'fell', 'held level')}: "
                               f"{_fmt(early)}% in weeks 1-{split} vs {_fmt(late)}% from week {split + 1} on.")
    elif factor == "Touchdown share":
        share = dict(zip(t.text("player"), t.col("td_share_pct")))
        a, b = names
        if share.get(a) is not None and share.get(b) is not None:
            steadier = a if share[a] < share[b] else b
            d.lines.append(f"Share of points from touchdowns: {a} {_fmt(share[a])}% vs {b} {_fmt(share[b])}%; "
                           f"{steadier} is less touchdown-dependent (lower is steadier).")
    elif factor == "Next matchup":
        _matchup_labels(t, d)
        allowed = next((h for h in t.headers if h.startswith("opp_avg_")), "")
        rows = {n: i for n, i in zip(t.text("player"), range(len(t.rows)))}
        opp, rank, value = t.text("opponent"), t.col("allowed_rank"), t.col(allowed)
        d.allowed = {n: value[i] for n, i in rows.items() if opp[i] and value[i] is not None}
        if len(d.allowed) == 2:
            (x, vx), (y, vy) = sorted(d.allowed.items(), key=lambda kv: -kv[1])
            ix, iy = rows[x], rows[y]
            if vx - vy >= FLAT:
                d.lines.append(
                    f"Easier matchup: {x} ({opp[ix]} allow {_fmt(vx)}, rank {_fmt(rank[ix])}) over {y} "
                    f"({opp[iy]} allow {_fmt(vy)}, rank {_fmt(rank[iy])}); more points allowed and a lower rank "
                    "number mean an easier matchup.")
            else:
                d.lines.append(f"The matchups are level: {opp[ix]} allow {_fmt(vx)} and {opp[iy]} allow {_fmt(vy)}.")
    favours, _, rule = fq.compare_rating(factor, results)
    d.favours = favours
    d.lines.append(f"By the code rule ({rule.split(';')[0]}), this factor "
                   + ("is even." if favours == EVEN else f"favours {favours}."))
    return d


# --- the checks ---


def _clauses(text: str) -> list[tuple[str, str]]:
    """(sentence, clause) pairs."""
    return [(s, c) for s in sentences(text) for c in CLAUSE.split(s) if c and c.strip()]


def _mentions(text: str, names) -> list[tuple[int, str]]:
    """(position, name) of each player named in text, by surname."""
    out = []
    for name in names:
        last = name_key(name).split()[-1:]
        if last:
            out += [(m.start(), name) for m in re.finditer(rf"\b{re.escape(last[0])}\b", text, re.I)]
    return sorted(out)


def _family(m: re.Match) -> str:
    """higher or lower (size words), good or bad (by polarity), or vague."""
    if m.group("moreless"):
        return "higher" if m.group("moreless").lower() == "more" else "lower"
    return next(k for k in ("good", "bad", "vague", "higher", "lower") if m.group(k))


def _polarity(text: str):
    """The POLARITY entry for the metric named in text, the one nearest the end (the pair)."""
    found = [(m.start(), p) for p in POLARITY for m in p[1].finditer(text)]
    return max(found, key=lambda f: f[0])[1] if found else None


def contradictions(text: str, d: Directions, favours: str | None = None) -> list[str]:
    """Reasons text contradicts the computed directions (empty if it agrees)."""
    problems = []
    if favours and d.favours and d.favours != EVEN and favours != EVEN and not same_player(favours, d.favours):
        problems.append(f"it says this factor favours {favours}, but the numbers favour {d.favours}")
    if ELLIPSIS.search(text):
        problems.append("it is unfinished (an ellipsis)")
    for sentence, clause in _clauses(text):
        # The compare rule's own tie-break ("more PPR points per game (19.8 vs 19.8); they are
        # within 0.5, so the later weeks decide") is not a direction claim (QA run).
        tie = "within 0.5" in sentence and "later weeks decide" in sentence
        problems += ([] if tie else _pairs(clause)) + _from_to(clause) + _trend_words(clause, d) + _matchup_words(sentence, clause, d)
        problems += _ranking(sentence, clause, d) + _label_words(sentence, clause, d)
    return list(dict.fromkeys(problems))


PRONOUN = re.compile(r"\b(?:he|his|him)\b", re.I)


def _subject(sentence: str, clause: str, at: int, names) -> str | None:
    """The player a word at `at` in clause is about: the nearest one named before it, or,
    if "he"/"his" stands between, the sentence's first-named player."""
    before = [(p, n) for p, n in _mentions(clause, names) if p < at]
    last = before[-1][0] if before else -1
    if PRONOUN.search(clause[last + 1:at]):
        first = _mentions(sentence, names)
        return first[0][1] if first else None
    return before[-1][1] if before else None


def _pairs(clause: str) -> list[str]:
    out = []
    pairs = list(PAIR.finditer(clause))
    in_pair = lambda at: any(p.start("a") <= at < p.end() for p in pairs)
    for m in pairs:
        words = list(COMPARE.finditer(clause[:m.start("a")]))
        if not words:
            continue
        word, family = words[-1], _family(words[-1])
        if family == "vague":
            continue  # "edge", "better": not checkable, and it ends an earlier word's reach
        # The word carries over "higher target share (21.9% vs 15.2%) and air yards share (31.9% vs 34.1%)",
        # but not past a number of its own ("52 targets and 0 carries in 6 games compared to 29"),
        # and not far: "a higher average that outweighs ..." does not reach a later pair.
        between = [word.end() + n.start() for n in NUMBER.finditer(clause[word.end():m.start("a")])]
        if any(not in_pair(at) for at in between):
            continue
        gap = len(clause[word.end():m.start("a")]) - sum(
            p.end() - p.start("a") for p in pairs if word.end() <= p.start("a") and p.end() <= m.start("a"))
        if gap > WORD_REACH:
            continue
        a, b = float(m.group("a")), float(m.group("b"))
        rank_pair = "rank" in clause[max(0, m.start() - 6):m.start()].lower()
        if family in ("higher", "lower"):
            if rank_pair:
                continue  # "a higher rank": the number or the standing? ambiguous
            if family == "higher" and a <= b or family == "lower" and a >= b:
                out.append(f"'{word.group(0)}' does not fit {m.group('a')} vs {m.group('b')}")
            continue
        polarity = _polarity(clause[word.start():m.end()])
        if polarity is None or a == b:
            continue  # "easier" with no metric named: which number is easier is not known
        metric, _, higher_is_good, meaning = polarity
        a_is_good = a > b if higher_is_good else a < b
        if (family == "good") != a_is_good:
            out.append(f"'{word.group(0)}' does not fit {m.group('a')} vs {m.group('b')}: for {metric}, "
                       f"the {'higher' if higher_is_good else 'lower'} number is the {meaning}")
    return out


def _from_to(clause: str) -> list[str]:
    out = []
    for m in FROM_TO.finditer(clause):
        before = clause[:m.start()]
        rises, falls = list(RISE.finditer(before)), list(FALL.finditer(before))
        if not rises and not falls:
            continue
        last = max(rises + falls, key=lambda w: w.start())
        a, b = float(m.group("a")), float(m.group("b"))
        if last in rises and b < a or last in falls and b > a:
            out.append(f"'{last.group(0)}' does not fit from {m.group('a')} to {m.group('b')}")
    return out


def _trend_words(clause: str, d: Directions) -> list[str]:
    if not d.trends or FROM_TO.search(clause) or PAIR.search(clause):
        return []  # numbers in the clause are checked by _from_to and _pairs
    rises, falls = bool(RISE.search(clause)), bool(FALL.search(clause))
    if rises == falls:
        return []  # no change word, or both: not one claim
    out = []
    for metric, pattern in METRICS.items():
        change = d.trends.get(metric)
        if change is None or abs(change) < FLAT or not re.search(pattern, clause, re.I):
            continue
        if rises and change < 0 or falls and change > 0:
            out.append(f"it says {metric} {'rose' if rises else 'fell'}, but it {'fell' if change < 0 else 'rose'} "
                       f"{d.trend_label} ({'+' if change > 0 else ''}{_fmt(change)})")
    return out


def _matchup_words(sentence: str, clause: str, d: Directions) -> list[str]:
    if len(d.allowed) != 2:
        return []
    out = []
    named = _mentions(clause, d.allowed)
    for pattern, easier in ((EASIER, True), (TOUGHER, False)):
        for m in pattern.finditer(clause):
            after = [n for at, n in named if at > m.start()]
            who = _opponent_after(clause, m.end(), d) or _subject(sentence, clause, m.start(), d.allowed) or (
                after[0] if after else None)
            if who is None:
                continue
            other = next(n for n in d.allowed if n != who)
            mine, theirs = d.allowed[who], d.allowed[other]
            if abs(mine - theirs) < FLAT:
                continue
            if easier and mine < theirs or not easier and mine > theirs:
                out.append(f"it gives {who} the {'easier' if easier else 'tougher'} matchup, but {who}'s opponent "
                           f"allows {_fmt(mine)} to {other}'s {_fmt(theirs)}; more points allowed is easier")
    return out


# Matchup words checked against the code's label (fq.matchup_label).
EASY_WORDS = re.compile(r"\b(?:easy|easier|easiest|favou?rable|soft|softer|softest|friendly|friendlier|friendliest)\b",
                        re.I)
TOUGH_WORDS = re.compile(r"\b(?:tough|tougher|toughest|hard|harder|hardest|stingy|stingier|stingiest|difficult)\b", re.I)
THIRD = re.compile(r"\b(?P<which>top|bottom)[- ]third\b", re.I)
NEGATED = re.compile(r"\b(?:not|less|never|isn't|wasn't|no)\s+(?:\w+\s+)?$", re.I)
MATCHUP_CONTEXT = re.compile(r"matchup|defen[cs]e|opponent|allow|\bfac(?:es|ing)\b|\brank", re.I)
# City names the team codes do not carry (fq.TEAM_NAMES has nicknames): "Los Angeles" for LA or LAC.
CITIES = {"los angeles": ("LA", "LAC"), "new york": ("NYG", "NYJ"), "arizona": ("ARI",), "atlanta": ("ATL",),
          "baltimore": ("BAL",), "buffalo": ("BUF",), "carolina": ("CAR",), "chicago": ("CHI",),
          "cincinnati": ("CIN",), "cleveland": ("CLE",), "dallas": ("DAL",), "denver": ("DEN",),
          "detroit": ("DET",), "green bay": ("GB",), "houston": ("HOU",), "indianapolis": ("IND",),
          "jacksonville": ("JAX",), "kansas city": ("KC",), "las vegas": ("LV",), "miami": ("MIA",),
          "minnesota": ("MIN",), "new england": ("NE",), "new orleans": ("NO",), "philadelphia": ("PHI",),
          "pittsburgh": ("PIT",), "san francisco": ("SF",), "seattle": ("SEA",), "tampa bay": ("TB",),
          "tennessee": ("TEN",), "washington": ("WAS",)}


def _opponent_mentions(text: str, d: Directions) -> list[tuple[int, str]]:
    """(position, player) for each mention of a player's opponent: "LA", "Rams", "Los Angeles"."""
    out = []
    for player, m in d.matchups.items():
        code = m["opp"]
        out += [(x.start(), player) for x in re.finditer(rf"\b{re.escape(code)}\b", text)]
        names = [n for n in fq.TEAM_NAMES.get(code, ())]
        names += [city for city, codes in CITIES.items()
                  if code in codes and sum(c in codes for c in (v["opp"] for v in d.matchups.values())) == 1]
        out += [(x.start(), player) for n in names for x in re.finditer(rf"\b{re.escape(n)}\b", text, re.I)]
    return sorted(out)


def _opponent_after(clause: str, at: int, d: Directions) -> str | None:
    """The player whose opponent is named just after a matchup word: "easier matchup with Los Angeles"."""
    near = [(p, n) for p, n in _opponent_mentions(clause, d) if at <= p <= at + 40]
    return near[0][1] if near else None


def _label_words(sentence: str, clause: str, d: Directions) -> list[str]:
    if not d.matchups or not MATCHUP_CONTEXT.search(clause):
        return []
    out = []
    words = [(m, "easy") for m in EASY_WORDS.finditer(clause)] + [(m, "tough") for m in TOUGH_WORDS.finditer(clause)]
    words += [(m, m.group("which").lower()) for m in THIRD.finditer(clause)]
    for m, kind in words:
        if NEGATED.search(clause[:m.start()]):
            continue  # "not an easy matchup", "less favorable": not checked
        who = _opponent_after(clause, m.end(), d)
        if who is None:
            before = [(p, n) for p, n in sorted(_opponent_mentions(clause, d) + _mentions(clause, d.matchups))
                      if p < m.start()]
            last = before[-1][0] if before else -1
            if PRONOUN.search(clause[last + 1:m.start()]):
                first = _mentions(sentence, d.matchups)
                who = first[0][1] if first else None
            else:
                who = before[-1][1] if before else None
        if who is None and len(d.matchups) == 1:
            who = next(iter(d.matchups))
        if who is None:
            continue
        mu = d.matchups[who]
        label = mu["label"]
        fits = {"easy": label != "tough", "tough": label != "favorable",
                "top": label == "favorable", "bottom": label == "tough"}[kind]
        if not fits:
            out.append(f"'{m.group(0)}' does not fit {who}'s matchup: {mu['opp']} is rank {_fmt(mu['rank'])} of "
                       f"{_fmt(mu['teams'])} in points allowed, a {label} matchup (rank 1 allows the most)")
    return out


def unknown_numbers(text: str, allowed: list[float]) -> list[tuple[str, str]]:
    """(sentence, number) for each number in text that no allowed value matches to 1 decimal place.

    The difference or sum of two allowed numbers cited in the same sentence is allowed
    too: "a 3.4-point edge (20.6 vs 17.2)".
    """
    out = []
    known = lambda v: any(abs(v - a) < 0.051 for a in allowed)
    for sentence in sentences(text):
        values = [float(v) for v in NUMBER.findall(sentence)]
        cited = [v for v in values if known(v)]
        derived = {round(x + y, 1) for i, x in enumerate(cited) for y in cited[i + 1:]}
        derived |= {round(abs(x - y), 1) for i, x in enumerate(cited) for y in cited[i + 1:]}
        for value in NUMBER.findall(sentence):
            v = float(value)
            if not known(v) and not any(abs(v - d) < 0.051 for d in derived):
                out.append((sentence, value))
    return out


def numbers_in(texts) -> list[float]:
    return sorted({float(m) for text in texts for m in NUMBER.findall(str(text))})


def _ranking(sentence: str, clause: str, d: Directions) -> list[str]:
    if len(d.shares) < 2:
        return []
    out = []
    in_clause = _mentions(clause, d.shares)
    start = sentence.find(clause)
    outside = [n for at, n in _mentions(sentence, d.shares) if not start <= at < start + len(clause)]
    for pattern, ahead in ((AHEAD, True), (BEHIND, False)):
        for m in pattern.finditer(clause):
            # "if Mike Evans is out, Deebo Samuel ... behind George Kittle": the subject follows the comma.
            comma = clause.rfind(",", 0, m.start())
            left = list(dict.fromkeys(n for at, n in in_clause if comma < at < m.start()))
            end = LIST_END.search(clause, m.end())
            stop = end.start() if end else len(clause)
            right = list(dict.fromkeys(n for at, n in in_clause if m.end() <= at < stop)) or \
                [n for n in dict.fromkeys(outside) if n not in left]
            for x in left:
                for y in right:
                    if x == y:
                        continue
                    if ahead and d.shares[x] < d.shares[y] or not ahead and d.shares[x] > d.shares[y]:
                        out.append(f"it puts {x} {'above' if ahead else 'below'} {y}, but by {d.share_label} "
                                   f"{x} has {_fmt(d.shares[x])}% to {y}'s {_fmt(d.shares[y])}%")
    return out


def all_directions(results: Results, subject: str | None = None) -> Directions:
    """One Directions for a whole answer: the matchups, the team usage ranking and every line."""
    merged = Directions()
    for factor in results:
        if factor not in fq.RATED_FACTORS:
            continue
        d = directions(factor, results, subject)
        merged.lines += d.lines
        if d.allowed:
            merged.allowed = d.allowed
        merged.matchups.update(d.matchups)
        if factor == "Team usage":
            merged.shares, merged.share_label = d.shares, d.share_label
    return merged
