import duckdb
import pytest

from app import trace
from app.adapters import zetaris


@pytest.fixture
def sample_dir(tmp_path, monkeypatch):
    """A tiny NFLVERSE.player_stats in a temp dir, with sample mode on."""
    schema_dir = tmp_path / "NFLVERSE"
    schema_dir.mkdir()
    target = (schema_dir / "player_stats.parquet").as_posix()
    duckdb.sql(
        f"""
        COPY (
            SELECT * FROM (VALUES
                ('00-0031408', 'M.Evans', 'TB', 2026, 1, 9, 1.5, true),
                ('00-0031408', 'M.Evans', 'TB', 2026, 2, 7, NULL, false),
                ('00-0036900', 'J.Chase', 'CIN', 2026, 1, 12, 2.0, true)
            ) AS t(player_id, player_name, team, season, week, targets, epa, active)
        ) TO '{target}' (FORMAT parquet)
        """
    )
    monkeypatch.setattr(zetaris, "SAMPLE_DIR", tmp_path)
    monkeypatch.setattr(zetaris, "CACHE_DIR", tmp_path / "zetaris_cache")
    monkeypatch.setattr(zetaris, "_duckdb", None)
    monkeypatch.setenv("SAMPLE_MODE", "true")
    yield tmp_path
    if zetaris._duckdb is not None:
        zetaris._duckdb.close()


@pytest.fixture
def real_sample(monkeypatch):
    """The committed data/sample/ slice (2026 weeks 1-6), with sample mode on."""
    monkeypatch.setattr(zetaris, "_duckdb", None)
    monkeypatch.setenv("SAMPLE_MODE", "true")
    yield zetaris.SAMPLE_DIR
    if zetaris._duckdb is not None:
        zetaris._duckdb.close()


@pytest.fixture
def model(monkeypatch):
    """Scripted model, safe to call from parallel factor agents.

    Either set .replies (popped in call order) or .respond(messages) -> reply text;
    a reply that is an Exception is raised. Each call's messages and kwargs are kept.
    """
    import threading

    from app.agents import analyst

    class Stub:
        def __init__(self) -> None:
            self.replies: list = []
            self.respond = None
            self.calls: list[list[dict]] = []
            self.kwargs: list[dict] = []
            self.lock = threading.Lock()

        def chat(self, messages, **kwargs):
            with self.lock:
                self.calls.append([dict(m) for m in messages])
                self.kwargs.append(kwargs)
                if self.respond is None and not self.replies:
                    raise AssertionError("model called more times than scripted")
                reply = self.replies.pop(0) if self.respond is None else None
            if self.respond is not None:
                reply = self.respond(messages)
            if isinstance(reply, Exception):
                raise reply
            return {
                "model": "stub-model",
                "meterless": {"routed_model": "stub-routed"},
                "choices": [{"message": {"content": reply}}],
            }

    stub = Stub()
    monkeypatch.setattr(analyst.meterless, "chat", stub.chat)
    monkeypatch.delenv("ANALYST_FREE_SQL", raising=False)
    yield stub
    # Factor agents left running past their window must finish before tracing is unpatched.
    for thread in threading.enumerate():
        if thread.name.startswith(("factor_agent:", "model_call:")):
            thread.join(5)


@pytest.fixture(autouse=True)
def trace_dir(tmp_path, monkeypatch):
    """Keep test trace lines out of the real logs/ folder."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(trace, "LOG_DIR", log_dir)
    return log_dir
