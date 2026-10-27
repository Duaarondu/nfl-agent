"""Run a .sql file from this folder live on Zetaris and write the results as Markdown.

One-off helper for the USL docs; the app does not use it. It goes through the app's
Zetaris adapter (app/adapters/zetaris.py: same settings from .env, same UI-proxy route)
with two differences:

- No cached-result fallback: every result in the Markdown came from the live cluster.
- A COMPILE USL statement and the CREATE TABLE definitions after it are sent as ONE
  request, with the ";" separators kept. run_sql() rejects that (one statement per
  call) and the SQL Workspace splits it, so this calls the adapter's _run_live().

Statements are split at a ";" that ends a line. The "--" comment lines just above a
statement are its title in the output.

    .venv/Scripts/python docs/zetaris-usl/run_usl.py docs/zetaris-usl/03-nfl-usl.sql \
        --out docs/zetaris-usl/03-nfl-usl-results.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.adapters import zetaris  # noqa: E402

MAX_ROWS = 25
MAX_CELL = 600  # COMPILE and REGISTER DQ return the whole model as one JSON cell


def statements(text: str) -> list[tuple[str, str]]:
    """(title, sql) pairs; CREATE TABLE definitions join the COMPILE USL before them."""
    chunks: list[tuple[list[str], list[str]]] = []
    comments: list[str] = []
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not body and stripped.startswith("--"):
            comments.append(stripped.lstrip("-").strip())
            continue
        if not body and not stripped:
            if comments and comments[-1]:
                comments.append("")
            continue
        if stripped.startswith("--"):
            continue  # a comment inside a statement is not sent
        body.append(line)
        if stripped.endswith(";"):
            chunks.append((comments, body))
            comments, body = [], []
    if body:
        chunks.append((comments, body))

    result: list[tuple[str, str]] = []
    for comments, body in chunks:
        sql = "\n".join(body).strip()
        title = " ".join(c for c in _last_paragraph(comments) if c)
        if result and re.match(r"(?i)CREATE\s+TABLE\b", sql) and re.match(r"(?i)COMPILE\s+USL\b", result[-1][1]):
            result[-1] = (result[-1][0], result[-1][1] + "\n" + sql)
        else:
            result.append((title, sql))
    return [(title, sql.rstrip().rstrip(";")) for title, sql in result]


def _last_paragraph(comments: list[str]) -> list[str]:
    paragraphs = " \n".join(comments).split(" \n \n")
    return paragraphs[-1].split(" \n") if paragraphs else []


def _redact(text: str) -> str:
    for name in ("ZETARIS_BASE_URL", "ZETARIS_API_KEY", "ZETARIS_PASSWORD", "ZETARIS_USERNAME", "ZETARIS_ORG_ID"):
        value = os.environ.get(name)
        if value and len(value) > 3:
            text = text.replace(value, f"<{name}>")
    return text


def _cell(value) -> str:
    text = "NULL" if value is None else str(value)
    if len(text) > MAX_CELL:
        text = text[:MAX_CELL] + f" … [{len(text):,} characters; the first {MAX_CELL} are shown]"
    return text.replace("|", "\\|").replace("\n", " ")


def run(sql: str) -> tuple[object, float]:
    started = time.perf_counter()
    if ";" in sql:  # the multi-table COMPILE USL: keep it as one request
        response = zetaris._run_live(sql, zetaris._positive_int("ZETARIS_QUERY_LIMIT", 1000))
    else:
        response = zetaris._run_live_with_retry(sql, zetaris._positive_int("ZETARIS_QUERY_LIMIT", 1000))
    return response, time.perf_counter() - started


def render(response: object) -> list[str]:
    if not isinstance(response, dict) or "headers" not in response:
        return ["", "Response: `" + _redact(str(response))[:500] + "`"]
    headers, rows = response["headers"], response.get("data") or []
    lines = [""]
    if not rows:
        return lines + ["Columns: " + ", ".join(f"`{h}`" for h in headers) + ". No rows."]
    if len(rows) == 1 and len(headers) > 6:  # one wide row reads better as a list
        lines += ["| column | value |", "|---|---|"]
        lines += [f"| {_cell(h)} | {_cell(v)} |" for h, v in zip(headers, rows[0])]
    else:
        lines += ["| " + " | ".join(_cell(h) for h in headers) + " |", "|" + "---|" * len(headers)]
        lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows[:MAX_ROWS]]
    total = response.get("total", len(rows))
    if len(rows) > MAX_ROWS:
        lines += ["", f"{len(rows)} rows returned; the first {MAX_ROWS} are shown."]
    elif total not in (None, len(rows)):
        lines += ["", f"{len(rows)} rows shown (total reported: {total})."]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql_file", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument("--from", dest="start", type=int, default=1,
                        help="rerun from statement N and append to --out (after a cluster error)")
    args = parser.parse_args()
    if zetaris._sample_mode():
        print("SAMPLE_MODE is on; these docs need the live cluster.", file=sys.stderr)
        return 2

    pairs = statements(args.sql_file.read_text(encoding="utf-8"))
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if args.start > 1:
        out = ["---", "", f"## Rerun from statement {args.start}", "",
               f"Statements {args.start}-{len(pairs)} run again on {when}, after the errors above.", ""]
    else:
        out = [f"# {args.title or args.sql_file.stem}", "",
               f"Live results of [`{args.sql_file.name}`]({args.sql_file.name}), run on {when} through the "
               "Zetaris UI-proxy route by [`run_usl.py`](run_usl.py) (no cached results). "
               "Pasted as returned; nothing edited except that long results show their first "
               f"{MAX_ROWS} rows and cells over {MAX_CELL} characters are cut.", ""]
    failures = 0
    for number, (title, sql) in enumerate(pairs, 1):
        if number < args.start:
            continue
        print(f"[{number}/{len(pairs)}] {sql.splitlines()[0][:100]}", flush=True)
        out += [f"## {number}. {title or sql.splitlines()[0][:80]}", "", "```sql", sql, "```"]
        try:
            response, seconds = run(sql)
        except zetaris.ZetarisError as error:
            failures += 1
            out += ["", f"**Error:** `{_redact(str(error))[:800]}`", ""]
            print("   error:", _redact(str(error))[:300], flush=True)
            continue
        out += render(response)
        out += ["", f"_{seconds:.1f}s_", ""]
    ran = len(pairs) - args.start + 1
    out += [f"{ran} statements, {failures} errors."]
    if args.start > 1:
        with args.out.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "\n".join(out) + "\n")
    else:
        args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{ran} statements, {failures} errors -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
