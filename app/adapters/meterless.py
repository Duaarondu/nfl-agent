"""Meterless adapter: every model call goes through this module.

Talks to the Meterless Nightshift Runtime's OpenAI-compatible API.
Settings come from the repo's .env (never overrides variables already set):

    METERLESS_BASE_URL         runtime origin, with or without a trailing /v1
    METERLESS_RUNTIME_TOKEN    bearer token
    METERLESS_MODEL            default model for chat()
    METERLESS_TIMEOUT_SECONDS  per-request timeout (default 60)
    METERLESS_MAX_TOKENS       default max_tokens for chat() (default 2048)

Fallback: a chat request that gets a 5xx or an empty reply is retried once
with the same model, then raises MeterlessError.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import load_env

APP_HEADERS = {"meterless-app": "nfl-agent", "meterless-scope": "user"}


class MeterlessError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


load_env()


def configured() -> bool:
    """Whether a model runtime is set up (sample mode can run without one)."""
    return all(os.environ.get(k) for k in ("METERLESS_BASE_URL", "METERLESS_RUNTIME_TOKEN", "METERLESS_MODEL"))


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MeterlessError(f"Set {name} in .env.")
    return value


def _api_url(path: str) -> str:
    base_url = _require("METERLESS_BASE_URL").rstrip("/").removesuffix("/v1")
    if not re.fullmatch(r"https?://\S+", base_url):
        raise MeterlessError("METERLESS_BASE_URL must be an HTTP(S) URL.")
    return f"{base_url}/v1{path}"


def _timeout() -> float:
    raw = os.environ.get("METERLESS_TIMEOUT_SECONDS", "60")
    try:
        value = float(raw)
    except ValueError as error:
        raise MeterlessError("METERLESS_TIMEOUT_SECONDS must be a positive number.") from error
    if value <= 0:
        raise MeterlessError("METERLESS_TIMEOUT_SECONDS must be a positive number.")
    return value


def _max_tokens() -> int:
    raw = os.environ.get("METERLESS_MAX_TOKENS", "2048")
    try:
        value = int(raw)
    except ValueError as error:
        raise MeterlessError("METERLESS_MAX_TOKENS must be a positive integer.") from error
    if value < 1:
        raise MeterlessError("METERLESS_MAX_TOKENS must be a positive integer.")
    return value


def _request(path: str, method: str = "GET", body: Any = None, timeout: float | None = None) -> Any:
    url = _api_url(path)
    headers = {
        "Authorization": f"Bearer {_require('METERLESS_RUNTIME_TOKEN')}",
        "X-Request-ID": str(uuid.uuid4()),
        **APP_HEADERS,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout or _timeout()) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read(500).decode("utf-8", errors="replace")
        raise MeterlessError(
            f"{method} /v1{path} failed: HTTP {error.code} {detail}", status=error.code
        ) from error
    except (OSError, TimeoutError, URLError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        raise MeterlessError(
            f"Cannot reach Meterless Nightshift at {url}: {reason}. "
            "Check that the Nightshift runtime is running and METERLESS_BASE_URL is correct."
        ) from error


def list_models() -> list[str]:
    """Return the model IDs the runtime offers."""
    result = _request("/models")
    return [model["id"] for model in result.get("data", []) if "id" in model]


def chat(
    messages: list[dict[str, Any]],
    model: str | None = None,
    timeout: float | None = None,
    **params: Any,
) -> dict[str, Any]:
    """Send a chat completion request and return the full response.

    Retries once with the same model on a 5xx or an empty reply.
    """
    body = {
        "model": model or _require("METERLESS_MODEL"),
        "messages": messages,
        "max_tokens": _max_tokens(),
        **params,
    }
    for attempt in (1, 2):
        try:
            response = _request("/chat/completions", "POST", body, timeout)
        except MeterlessError as error:
            if attempt == 1 and error.status is not None and error.status >= 500:
                continue
            raise
        if not _is_empty(response):
            return response
        if attempt == 2:
            raise MeterlessError(f"Empty reply from {body['model']} after one retry.")
    raise AssertionError("unreachable")


def _is_empty(response: Any) -> bool:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return True
    return not (message.get("content") or "").strip() and not message.get("tool_calls")


def chat_text(messages: list[dict[str, Any]], **kwargs: Any) -> str:
    """Send a chat completion request and return the first reply's text."""
    response = chat(messages, **kwargs)
    try:
        return response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as error:
        raise MeterlessError("Unexpected chat response shape.") from error
