"""JSONL trace lines for every agent step, written to stdout and logs/trace-<date>.jsonl."""

from __future__ import annotations

import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import REPO_ROOT

LOG_DIR = REPO_ROOT / "logs"
_lock = threading.Lock()  # factor agents trace from parallel threads
_subscribers: list[Callable[[dict[str, Any]], None]] = []


def subscribe(fn: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
    """Also send every trace line to fn (e.g. to collect one run's lines); returns an unsubscribe."""
    with _lock:
        _subscribers.append(fn)

    def unsubscribe() -> None:
        with _lock:
            if fn in _subscribers:
                _subscribers.remove(fn)

    return unsubscribe


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def trace(
    run_id: str,
    agent_name: str,
    action: str,
    status: str,
    *,
    target_agent: str | None = None,
    retry_count: int = 0,
    sql: str | None = None,
    model: str | None = None,
    rows_returned: int | None = None,
    duration_ms: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    line = {
        "timestamp": now.isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "agent_name": agent_name,
        "action": action,
        "target_agent": target_agent,
        "status": status,
        "retry_count": retry_count,
        "sql": sql,
        "model": model,
        "rows_returned": rows_returned,
        "duration_ms": duration_ms,
        **extra,
    }
    text = json.dumps(line, ensure_ascii=False)
    with _lock:
        print(text, file=sys.stdout, flush=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / f"trace-{now:%Y%m%d}.jsonl", "a", encoding="utf-8") as log:
            log.write(text + "\n")
        subscribers = list(_subscribers)
    for fn in subscribers:
        fn(line)
    return line
