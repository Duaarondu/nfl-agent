"""Zetaris adapter: every data query goes through run_sql().

Uses the Zetaris UI-proxy route (POST /api/proxy/sql-editor/sqls/run-query).
Settings come from the repo's .env (never overrides variables already set):

    ZETARIS_BASE_URL         HTTP(S) origin, no path (default http://localhost:3000)
    ZETARIS_ORG_ID           numeric organization ID
    ZETARIS_API_KEY          bearer token, or else both of:
    ZETARIS_USERNAME / ZETARIS_PASSWORD
    ZETARIS_ENGINE_ID        optional
    ZETARIS_QUERY_LIMIT      max rows (default 1000)
    ZETARIS_TIMEOUT_SECONDS  per-request timeout (default 60)
    SAMPLE_MODE              "true" runs the SQL with DuckDB against local Parquet

Sample mode: each data/sample/<SCHEMA>/<table>.parquet is exposed as the view
<SCHEMA>.<table> (e.g. NFLVERSE.player_stats), so the same SQL runs in both
modes. Results use the live response shape, with values as strings.

Retry: a live query that fails fast with a transient cluster error (Thrift
TTransportException, "Could not create ResultSet") is retried once after a short
pause. A timeout is not retried: it already used the whole time limit.

Fallback: if a live query fails, run_sql() returns the cached result for the
exact same SQL from data/sample/zetaris_cache/ when one exists, otherwise
raises ZetarisError.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import REPO_ROOT, load_env

SAMPLE_DIR = REPO_ROOT / "data" / "sample"
CACHE_DIR = SAMPLE_DIR / "zetaris_cache"
RUN_QUERY_PATH = "/api/proxy/sql-editor/sqls/run-query"


class ZetarisError(RuntimeError):
    pass


load_env()

_token: str | None = None
_duckdb: Any = None


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ZetarisError(f"{name} must be a positive integer.") from error
    if value < 1:
        raise ZetarisError(f"{name} must be a positive integer.")
    return value


def _sample_mode() -> bool:
    return os.environ.get("SAMPLE_MODE", "").strip().lower() in ("1", "true", "yes")


def _base_url() -> str:
    base_url = os.environ.get("ZETARIS_BASE_URL", "http://localhost:3000").removesuffix("/")
    if not re.fullmatch(r"https?://[^/]+", base_url):
        raise ZetarisError("ZETARIS_BASE_URL must be an HTTP(S) origin without a path.")
    return base_url


def _org_id() -> str:
    org_id = os.environ.get("ZETARIS_ORG_ID")
    if not org_id or not re.fullmatch(r"[0-9]+", org_id):
        raise ZetarisError("Set ZETARIS_ORG_ID to the numeric organization ID in .env.")
    return org_id


def _single_statement(sql: str) -> str:
    """Return sql without a trailing semicolon; reject multiple statements."""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise ZetarisError("SQL must not be empty.")
    quote = None
    for char in sql:
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == ";":
            raise ZetarisError("run_sql accepts exactly one SQL statement per call.")
    return sql


def _cache_path(sql: str) -> Path:
    normalized = " ".join(sql.split()).lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.json"


def _read_cache(sql: str) -> Any:
    path = _cache_path(sql)
    if not path.is_file():
        raise ZetarisError(f"No cached result for this query ({path.name}).")
    return json.loads(path.read_text(encoding="utf-8"))


def _identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ZetarisError(f"Invalid sample table or schema name: {name!r}")
    return name


def _sample_connection() -> Any:
    """Open one in-memory DuckDB with a view per sample Parquet file."""
    global _duckdb
    if _duckdb is None:
        import duckdb

        connection = duckdb.connect(":memory:")
        for path in sorted(SAMPLE_DIR.glob("*/*.parquet")):
            schema = _identifier(path.parent.name)
            table = _identifier(path.stem)
            source = path.as_posix().replace("'", "''")
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            connection.execute(
                f"CREATE VIEW {schema}.{table} AS SELECT * FROM read_parquet('{source}')"
            )
        _duckdb = connection
    return _duckdb


def _as_text(value: Any) -> str | None:
    """Format a DuckDB value as live Zetaris does (dates are already identical)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        # Java Timestamp style: fractional seconds without trailing zeros, at least ".0".
        fraction = f"{value.microsecond:06d}".rstrip("0") or "0"
        return f"{value:%Y-%m-%d %H:%M:%S}.{fraction}"
    return str(value)


def _run_sample(sql: str, limit: int) -> dict[str, Any]:
    if not re.match(r"(?is)\s*(select|with)\b", sql):
        raise ZetarisError("Sample mode only supports SELECT and WITH queries.")
    import duckdb

    started = time.perf_counter()
    try:
        cursor = _sample_connection().execute(sql)
        rows = cursor.fetchmany(limit)
    except duckdb.Error as error:
        raise ZetarisError(f"Sample query failed: {error}") from error
    return {
        "headers": [column[0] for column in cursor.description],
        "data": [[_as_text(value) for value in row] for row in rows],
        "total": len(rows),
        "timeUsed": round((time.perf_counter() - started) * 1000),
    }


def _unreachable(base_url: str, error: BaseException) -> ZetarisError:
    reason = error.reason if isinstance(error, URLError) else error
    return ZetarisError(f"Cannot reach {base_url}: {reason}")


def _login(base_url: str, timeout: int) -> str:
    username = os.environ.get("ZETARIS_USERNAME")
    password = os.environ.get("ZETARIS_PASSWORD")
    if not username or not password:
        raise ZetarisError("Set ZETARIS_API_KEY or both ZETARIS_USERNAME and ZETARIS_PASSWORD.")

    request = Request(
        f"{base_url}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-ID": str(uuid.uuid4())},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            login = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ZetarisError(f"Zetaris login failed: HTTP {error.code}") from error
    except (OSError, TimeoutError, URLError) as error:
        raise _unreachable(base_url, error) from error

    token = None
    if isinstance(login, dict):
        token = login.get("idToken") or login.get("token") or login.get("accessToken")
    if not token:
        match = re.search(
            r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", json.dumps(login)
        )
        token = match.group(0) if match else None
    if not isinstance(token, str) or not token:
        raise ZetarisError("Zetaris login did not return an access token.")
    return token


def _get_token(base_url: str, timeout: int) -> str:
    global _token
    api_key = os.environ.get("ZETARIS_API_KEY")
    if api_key:
        return api_key
    if _token is None:
        _token = _login(base_url, timeout)
    return _token


def _run_live(sql: str, limit: int) -> Any:
    base_url = _base_url()
    org_id = _org_id()
    timeout = _positive_int("ZETARIS_TIMEOUT_SECONDS", 60)
    token = _get_token(base_url, timeout)

    body: dict[str, object] = {"sql": sql, "limit": limit}
    engine_id = os.environ.get("ZETARIS_ENGINE_ID")
    if engine_id:
        body["engineId"] = engine_id

    request = Request(
        f"{base_url}{RUN_QUERY_PATH}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Org-ID": org_id,
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if "text/html" in error.headers.get("content-type", ""):
            detail = "The server returned an HTML page; check the API route."
        else:
            detail = error.read(500).decode("utf-8", errors="replace")
        raise ZetarisError(f"POST {RUN_QUERY_PATH} failed: HTTP {error.code} {detail}") from error
    except (OSError, TimeoutError, URLError) as error:
        raise _unreachable(base_url, error) from error


# Errors the cluster returns within milliseconds when its Thrift connection drops; a
# retry a moment later succeeds (scripts/check_factor_queries_live.py, 2026-10-25).
TRANSIENT_ERROR = re.compile(r"TTransportException|Could not create ResultSet")
RETRY_PAUSE_SECONDS = 2.0


def _run_live_with_retry(sql: str, limit: int) -> Any:
    try:
        return _run_live(sql, limit)
    except ZetarisError as error:
        if not TRANSIENT_ERROR.search(str(error)):
            raise
    time.sleep(RETRY_PAUSE_SECONDS)
    return _run_live(sql, limit)


def run_sql(sql: str, limit: int | None = None) -> Any:
    """Run one SQL statement and return the parsed JSON response."""
    sql = _single_statement(sql)
    if limit is None:
        limit = _positive_int("ZETARIS_QUERY_LIMIT", 1000)

    if _sample_mode():
        return _run_sample(sql, limit)

    try:
        return _run_live_with_retry(sql, limit)
    except ZetarisError as live_error:
        try:
            return _read_cache(sql)
        except ZetarisError:
            raise live_error from None
