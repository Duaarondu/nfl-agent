"""Queries the Analyst runs in code before the model's first turn.

The player named in the question is looked up in rosters, then a fixed bundle
of SQL runs for that player: one query per "why" factor for why-questions, or
status, team usage and depth chart for everything else. All SQL is plain
standard SQL that runs on both Spark SQL (Zetaris) and DuckDB (sample mode).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
QUESTION_TYPES = ("why", "replacement", "start_sit", "waiver", "other")
MAX_NAME_CANDIDATES = 60
WHY_FACTORS = (
    "Opportunity", "Teammate absences", "Team pass rate and game script",
    "Big plays", "Touchdowns and red zone", "Matchups",
)

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
    "LA": ("rams",),
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


@dataclass
class PlannedQuery:
    factor: str
    purpose: str
    sql: str


def guess_question_type(question: str) -> str:
    """Keyword fallback for when the model cannot classify the question."""
    text = question.lower()
    if is_why_question(text):
        return "why"
    if re.search(r"\b(becomes?|replace|replaces|takes? over|next man up|wr1|rb1|te1)\b", text):
        return "replacement"
    if re.search(r"\b(start|sit|bench|flex)\b", text):
        return "start_sit"
    if re.search(r"\b(pick (him )?up|waiver|add|drop|stash)\b", text):
        return "waiver"
    return "other"


def is_why_question(question: str) -> bool:
    return re.search(r"\b(why|explain|what explains|how come)\b", question, re.I) is not None


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def name_candidates(question: str) -> list[str]:
    """Every run of 2-3 words in the question, lowercased: possible full names."""
    words = re.findall(r"[A-Za-z][A-Za-z.'\-]*", question)
    words = [w.rstrip(".").removesuffix("'s").removesuffix("'") for w in words]
    seen: list[str] = []
    for size in (2, 3):
        for i in range(len(words) - size + 1):
            candidate = " ".join(words[i : i + size]).lower()
            if candidate not in seen:
                seen.append(candidate)
    return seen[:MAX_NAME_CANDIDATES]


def lookup_sql(candidates: list[str], season: int) -> str:
    """Latest roster row this season for each skill player whose full name is a candidate."""
    names = ", ".join(_quote(c) for c in candidates)
    positions = ", ".join(_quote(p) for p in SKILL_POSITIONS)
    return (
        "SELECT r.gsis_id, r.full_name, r.team, r.position, r.status, r.week "
        "FROM NFLVERSE.rosters r "
        "JOIN (SELECT gsis_id, MAX(week) AS week FROM NFLVERSE.rosters "
        f"WHERE season = {season} AND LOWER(full_name) IN ({names}) GROUP BY gsis_id) latest "
        "ON r.gsis_id = latest.gsis_id AND r.week = latest.week "
        f"WHERE r.season = {season} AND r.position IN ({positions}) "
        "ORDER BY r.full_name"
    )


def parse_players(rows: list[list], question: str) -> list[Player]:
    """Players from lookup rows, in the order the question names them."""
    players = [
        Player(str(r[0]), str(r[1]), str(r[2]), str(r[3]), r[4], int(r[5])) for r in rows
    ]
    text = question.lower()
    return sorted(players, key=lambda p: text.find(p.name.lower()))


def teams_mentioned(question: str) -> list[str]:
    """Team codes the question refers to by name or nickname, in order of appearance."""
    text = question.lower()
    found = []
    for code, names in TEAM_NAMES.items():
        positions = [m.start() for n in names for m in re.finditer(rf"\b{re.escape(n)}\b", text)]
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
        for name in TEAM_NAMES[code]:
            for match in re.finditer(rf"\b{re.escape(name)}\b", text):
                before = text[max(0, match.start() - 20) : match.start()]
                if not re.search(r"\b(vs\.?|versus|against|facing|plays|play)\s+(the\s+)?$", before):
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


def why_bundle(p: Player, season: int) -> list[PlannedQuery]:
    """One query per factor in the Analyst prompt's "why" list, plus injury status."""
    pid, team = _quote(p.player_id), _quote(p.team)
    pos = p.position if p.position in SKILL_POSITIONS else "WR"
    return [
        status_query(p, season),
        PlannedQuery(
            "Opportunity",
            f"{p.name}: snap %, targets, target share and PPR points by week",
            "SELECT ps.week, ps.opponent_team, sc.offense_snaps, "
            "ROUND(100 * sc.offense_pct, 1) AS snap_pct, ps.targets, "
            "ROUND(100 * ps.target_share, 1) AS target_share_pct, ps.receptions, ps.carries, "
            "ROUND(ps.fantasy_points_ppr, 1) AS ppr_points "
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
            f"{p.name}: touchdowns, TD points vs PPR points, red-zone targets and carries by week",
            "SELECT ps.week, ps.receiving_tds, ps.rushing_tds, "
            "6 * (ps.receiving_tds + ps.rushing_tds) AS td_points, "
            "ROUND(ps.fantasy_points_ppr, 1) AS ppr_points, "
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
            f"{p.name}: PPR points by opponent, and each opponent's average PPR allowed to {pos}s "
            "(rank 1 = most allowed)",
            "WITH allowed AS (SELECT opponent_team, week, SUM(fantasy_points_ppr) AS pts "
            f"FROM NFLVERSE.player_stats WHERE season = {season} AND position = {_quote(pos)} "
            "GROUP BY opponent_team, week), "
            "avg_allowed AS (SELECT opponent_team, ROUND(AVG(pts), 1) AS avg_ppr_allowed "
            "FROM allowed GROUP BY opponent_team), "
            "ranked AS (SELECT opponent_team, avg_ppr_allowed, "
            "RANK() OVER (ORDER BY avg_ppr_allowed DESC) AS allowed_rank FROM avg_allowed) "
            "SELECT ps.week, ps.opponent_team, ROUND(ps.fantasy_points_ppr, 1) AS ppr_points, "
            f"r.avg_ppr_allowed AS opp_avg_ppr_allowed_to_{pos.lower()}, r.allowed_rank "
            "FROM NFLVERSE.player_stats ps LEFT JOIN ranked r ON r.opponent_team = ps.opponent_team "
            f"WHERE ps.season = {season} AND ps.player_id = {pid} ORDER BY ps.week",
        ),
    ]


def team_bundle(p: Player, season: int, latest_week: int) -> list[PlannedQuery]:
    """Status, team usage and depth chart: for waiver, start/sit and replacement questions."""
    team = _quote(p.team)
    pos = p.position if p.position in SKILL_POSITIONS else "WR"
    recent = max(1, latest_week - 1)
    return [
        status_query(p, season),
        PlannedQuery(
            "Team usage",
            f"{p.team} RB/WR/TE usage this season and in weeks {recent}-{latest_week}",
            "SELECT player_display_name, position, COUNT(*) AS games, SUM(targets) AS targets, "
            "ROUND(100 * AVG(target_share), 1) AS avg_target_share_pct, "
            f"ROUND(100 * AVG(CASE WHEN week >= {recent} THEN target_share END), 1) AS recent_target_share_pct, "
            "SUM(carries) AS carries, ROUND(AVG(fantasy_points_ppr), 1) AS ppr_per_game "
            f"FROM NFLVERSE.player_stats WHERE season = {season} AND team = {team} "
            "AND position IN ('RB', 'WR', 'TE') "
            "GROUP BY player_display_name, position ORDER BY SUM(targets) DESC LIMIT 12",
        ),
        PlannedQuery(
            "Depth chart",
            f"{p.team} current {pos} depth chart (pos_rank 1 = top)",
            "SELECT DISTINCT pos_abb, pos_rank, player_name FROM NFLVERSE.depth_charts "
            f"WHERE team = {team} AND pos_abb = {_quote(pos)} "
            f"AND dt = (SELECT MAX(dt) FROM NFLVERSE.depth_charts WHERE team = {team}) "
            "ORDER BY pos_rank LIMIT 25",
        ),
    ]


def games_without_query(p: Player, season: int) -> PlannedQuery:
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
        "ROUND(AVG(ps.fantasy_points_ppr), 1) AS ppr_per_game "
        "FROM NFLVERSE.player_stats ps JOIN team_games g ON g.game_id = ps.game_id "
        "LEFT JOIN missed m ON m.game_id = ps.game_id "
        f"WHERE ps.season = {season} AND ps.team = {team} AND ps.player_id <> {pid} "
        "AND ps.position IN ('RB', 'WR', 'TE') "
        f"GROUP BY {split}, ps.player_display_name, ps.position "
        "ORDER BY player_status, targets DESC LIMIT 30",
    )


def plan(question_type: str, player: Player, season: int, latest_week: int) -> list[PlannedQuery]:
    if question_type == "why":
        return why_bundle(player, season)
    bundle = team_bundle(player, season, latest_week)
    if question_type == "replacement":
        bundle.append(games_without_query(player, season))
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
    return [
        f"{len(t.rows)} games, {_fmt(_total(t.col('targets')))} targets, average snap share "
        f"{_fmt(_avg(t.col('snap_pct')))}%, average target share {_fmt(_avg(share))}%, "
        f"{_fmt(_avg(t.col('ppr_points')))} PPR points per game.",
        f"Highest target share: week {weeks[best]} ({_fmt(share[best])}%).",
        t.early_late("snap_pct", "Snap share", "%"),
        t.early_late("target_share_pct", "Target share", "%"),
        t.early_late("ppr_points", "PPR points per game"),
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
    td_points, ppr = _total(t.col("td_points")), _total(t.col("ppr_points"))
    rz, team_rz = _total(t.col("rz_targets")), _total(t.col("team_rz_targets"))
    weeks = [w for w, a, b in zip(t.text("week"), rec, rush) if (a or 0) + (b or 0) > 0]
    return [
        f"{_fmt(_total(rec) + _total(rush))} touchdowns = {_fmt(td_points)} of {_fmt(ppr)} PPR points "
        f"({_fmt(_pct(td_points, ppr))}%). Scored in weeks: {', '.join(weeks) or 'none'}.",
        f"{_fmt(rz)} of the team's {_fmt(team_rz)} red-zone targets ({_fmt(_pct(rz, team_rz))}%); "
        f"{_fmt(_total(t.col('rz_carries')))} red-zone carries.",
    ]


def _matchups(t: _Rows) -> list[str]:
    ranks, ppr = t.col("allowed_rank"), t.col("ppr_points")
    soft = [p for r, p in zip(ranks, ppr) if r is not None and r <= 10]
    rest = [p for r, p in zip(ranks, ppr) if r is not None and r > 10]
    return [
        f"Average opponent rank in PPR points allowed to the position: {_fmt(_avg(ranks))} of 32 (1 = most allowed).",
        f"{_fmt(_avg(soft))} PPR per game vs top-10 soft defenses ({len(soft)} games), "
        f"{_fmt(_avg(rest))} vs the rest ({len(rest)} games).",
    ]


def _team_usage(t: _Rows) -> list[str]:
    recent, names, pos = t.col("recent_target_share_pct"), t.text("player_display_name"), t.text("position")
    top = sorted(range(len(t.rows)), key=lambda i: -(recent[i] or 0))[:4]
    return ["Highest recent target share: " + "; ".join(f"{names[i]} ({pos[i]}) {_fmt(recent[i])}%" for i in top) + "."]


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


def _depth(t: _Rows) -> list[str]:
    return ["Depth order: " + ", ".join(f"{r}. {n}" for r, n in zip(t.text("pos_rank"), t.text("player_name"))) + "."]


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
    "Depth chart": _depth,
    "Games without the player": _without,
}


# --- Rule-based ratings: the fallback when a factor agent's model call fails ---

RATED_FACTORS = (*WHY_FACTORS, "Team usage", "Depth chart", "Games without the player")


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
    return {w: p for w, p in zip(t.text("week"), t.col("ppr_points")) if p is not None}


def _split_gain(ppr: dict[str, float], weeks: set[str]) -> float | None:
    """PPR per game in the given weeks minus PPR per game in the other weeks."""
    inside = [p for w, p in ppr.items() if w in weeks]
    outside = [p for w, p in ppr.items() if w not in weeks]
    if not inside or not outside:
        return None
    return round(_avg(inside) - _avg(outside), 1)


def rule_rating(factor: str, results: dict[str, tuple[list[str], list[list]]]) -> tuple[str, str]:
    """(support, rule) for one factor from fixed thresholds over the query results.

    results maps factor name -> (headers, rows) for every planned query, since some
    rules compare this factor's weeks with the player's weekly PPR points.
    """
    headers, rows = results.get(factor, ([], []))
    t = _Rows(headers, rows)
    ppr = _ppr_by_week(results)
    if not rows and factor != "Teammate absences":
        return "not supported", "no rows"

    if factor == "Opportunity":
        share, snap = _avg(t.col("target_share_pct")), _avg(t.col("snap_pct"))
        support = _grade(share, 22, 15, 10)
        if support == "strong" and (snap or 0) < 70:
            support = "moderate"
        return support, f"average target share {_fmt(share)}% (strong >= 22 with snap share >= 70%, moderate >= 15, weak >= 10)"
    if factor == "Teammate absences":
        gain = _split_gain(ppr, set(t.text("week")))
        return _grade(gain, 5, 2, 0.1), f"PPR per game in weeks with a teammate out minus other weeks: {_fmt(gain)} (strong >= 5, moderate >= 2, weak > 0)"
    if factor == "Team pass rate and game script":
        rate = dict(zip(t.text("week"), t.col("pass_rate_pct")))
        mean = _avg(rate.values())
        gain = _split_gain(ppr, {w for w, r in rate.items() if r is not None and mean is not None and r > mean})
        return _grade(gain, 5, 2, 0.1), f"PPR per game in above-average pass-rate weeks minus the rest: {_fmt(gain)} (strong >= 5, moderate >= 2, weak > 0)"
    if factor == "Big plays":
        targets, yards = _total(t.col("targets")), _total(t.col("receiving_yards"))
        ypt = round(yards / targets, 1) if targets else None
        return _grade(ypt, 10, 8.5, 7), f"{_fmt(ypt)} yards per target (strong >= 10, moderate >= 8.5, weak >= 7)"
    if factor == "Touchdowns and red zone":
        share = _pct(_total(t.col("td_points")), _total(t.col("ppr_points")))
        return _grade(share, 35, 25, 15), f"touchdowns are {_fmt(share)}% of PPR points (strong >= 35, moderate >= 25, weak >= 15)"
    if factor == "Matchups":
        soft = {w for w, r in zip(t.text("week"), t.col("allowed_rank")) if r is not None and r <= 10}
        gain = _split_gain(ppr, soft)
        return _grade(gain, 5, 2, 0.1), f"PPR per game vs top-10 soft defenses minus the rest: {_fmt(gain)} (strong >= 5, moderate >= 2, weak > 0)"
    if factor == "Team usage":
        top = max((x for x in t.col("recent_target_share_pct") if x is not None), default=None)
        return _grade(top, 20, 15, 0.1), f"highest recent target share {_fmt(top)}% (strong >= 20, moderate >= 15)"
    if factor == "Depth chart":
        return ("moderate" if len(rows) >= 2 else "weak"), f"{len(rows)} players listed on the depth chart"
    if factor == "Games without the player":
        missed = [g for s, g in zip(t.text("player_status"), t.col("games")) if s == "missed"]
        n = int(max(missed)) if missed else 0
        return _grade(n, 3, 2, 1), f"{n} games without him (strong >= 3, moderate 2, weak 1)"
    return "not supported", "no rule for this factor"


# --- Rule-based verdict: the fallback when the verdict model call fails ---

START_PPR = 12.0  # PPR per game at or above which a start/sit rule says start
PICKUP_SHARE = 15.0  # recent target share (%) at or above which a waiver rule says pick up


# A sentence ends at . ! or ? before a capital or "(", but not after "Sr." / "Jr." or a
# numbered-list marker (": 1." / ", 2." as in "Depth order: 1. Mike Evans, 2. ...").
SENTENCE_BREAK = re.compile(r"(?<!\bSr\.)(?<!\bJr\.)(?<!: \d\.)(?<!, \d\.)(?<!, \d\d\.)(?<=[.!?])\s+(?=[A-Z(])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_BREAK.split(text.strip()) if s.strip()]


def _first_sentence(text: str) -> str:
    parts = sentences(text)
    return parts[0].rstrip(".") if parts else ""


def _next_up(player: Player, results: dict[str, tuple[list[str], list[list]]]) -> tuple[str | None, str]:
    """(stand-in, reason): top target share in games he missed, else top recent target
    share among his teammates, else the next name on the depth chart."""
    d = _Rows(*results.get("Depth chart", ([], [])))
    depth = [n for n in d.text("player_name") if not same_player(n, player.name)]
    t = _Rows(*results.get("Games without the player", ([], [])))
    missed = [i for i, s in enumerate(t.text("player_status")) if s == "missed"]
    if missed:
        share = t.col("avg_target_share_pct")
        best = max(missed, key=lambda i: share[i] or 0)
        name = t.text("player_display_name")[best]
        return name, f"{name} had the top target share ({_fmt(share[best])}%) in the games {player.name} missed."
    u = _Rows(*results.get("Team usage", ([], [])))
    recent = u.col("recent_target_share_pct")
    others = [i for i, n in enumerate(u.text("player_display_name")) if not same_player(n, player.name) and recent[i] is not None]
    if others:
        best = max(others, key=lambda i: recent[i])
        name, pos = u.text("player_display_name")[best], u.text("position")[best]
        reason = f"{name} ({pos}) has the top recent target share among his teammates ({_fmt(recent[best])}%)."
        if depth and not same_player(depth[0], name):
            reason += f" The depth chart lists {depth[0]} next at {player.position}."
        return name, reason
    return (depth[0], f"{depth[0]} is next on the depth chart.") if depth else (None, "")


def _usage(player: Player, results, column: str) -> float | None:
    t = _Rows(*results.get("Team usage", ([], [])))
    for name, value in zip(t.text("player_display_name"), t.col(column)):
        if same_player(name, player.name):
            return value
    return None


NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name: str) -> str:
    """'Deebo Samuel Sr.' and 'deebo samuel' -> 'deebo samuel' (sources disagree on suffixes)."""
    tokens = re.sub(r"[^a-z ]", " ", name.lower().replace("'", "")).split()
    return " ".join(t for t in tokens if t not in NAME_SUFFIXES)


def same_player(a: str, b: str) -> bool:
    return bool(name_key(a)) and name_key(a) == name_key(b)


def rule_verdict(
    question_type: str, player: Player, results: dict[str, tuple[list[str], list[list]]],
    ranked: list[tuple[str, str, str]],
) -> tuple[str, str]:
    """(verdict, why) from fixed rules; ranked is (factor, support, summary), most supported first."""
    backed = [(f, s, text) for f, s, text in ranked if s in ("strong", "moderate")]
    reasons = "; ".join(f"{f} ({s}): {_first_sentence(text)}" for f, s, text in backed[:3])
    why = f"Most supported by the data: {reasons}." if reasons else "No factor is strongly supported by the data."
    ruled_out = [f for f, s, _ in ranked if s == "not supported"]
    if ruled_out:
        why += f" Not supported: {', '.join(ruled_out)}."

    if question_type == "replacement":
        stand_in, reason = _next_up(player, results)
        verdict = f"Pick up {stand_in} if available" if stand_in else f"Hold until {player.team}'s next depth chart"
        why = f"{why} {reason}" if reason else why
    elif question_type == "start_sit":
        ppr = _usage(player, results, "ppr_per_game")
        verdict = f"{'Start' if ppr is not None and ppr >= START_PPR else 'Sit'} {player.name}"
        why += f" Rule: start at {_fmt(START_PPR)}+ PPR per game; he averages {_fmt(ppr)}."
    elif question_type == "waiver":
        share = _usage(player, results, "recent_target_share_pct")
        verdict = f"{'Pick up' if share is not None and share >= PICKUP_SHARE else 'Hold off on'} {player.name}"
        why += f" Rule: pick up at {_fmt(PICKUP_SHARE)}%+ recent target share; his is {_fmt(share)}%."
    else:
        verdict = f"Hold {player.name}"
    return verdict, why
