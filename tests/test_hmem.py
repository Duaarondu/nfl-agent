"""H-MEM engine (app/engines/hmem.py) against the spec's exact-tier rules."""

import json
import math

import pytest

from app.engines import hmem
from app.engines.hmem import HMEM

T0 = 1_750_000_000_000  # the conformance vectors' clock
DAY = hmem.DAY_MS


def make(tmp_path=None, **kwargs):
    if tmp_path is None:
        return HMEM(clock=lambda: T0, **kwargs)
    return HMEM(clock=lambda: T0, persist_dir=tmp_path / "store", ledger_path=tmp_path / "ledger.jsonl", **kwargs)


def test_record_without_a_source_is_rejected():
    m = make()
    with pytest.raises(ValueError, match="no source"):
        m.add("no source here", source="")
    with pytest.raises(ValueError):
        m.add("blank source", source="   ")
    assert m.add("valid record", source="test").source == "test"


def test_new_record_has_the_spec_fields():
    r = make().add("League scoring is half-PPR.", "interaction:chat_message", type="preference",
                   tags=["fantasy:scoring=half"], confidence=0.9, chat_id="s1", goal_run_id="run1")
    assert (r.type, r.layer, r.domain, r.namespace) == ("preference", "working", "fantasy", "fantasy/profile")
    assert (r.timestamp, r.lastAccessed, r.accessCount, r.confidence) == (T0, T0, 0, 0.9)
    assert (r.chatId, r.goalRunId, r.supersededBy, r.derivedFrom) == ("s1", "run1", None, [])
    assert r.provenance["origin"] == "manual" and len(r.embedding) == hmem.EMBED_DIM


@pytest.mark.parametrize("kind, start, confidence, access, tagged", [
    ("helpful", 0.7, 0.75, 1, False),
    ("not_helpful", 0.7, 0.67, 0, False),
    ("wrong", 0.7, 0.5, 0, True),
    ("wrong", 0.1, 0.0, 0, True),
    ("helpful", 0.98, 1.0, 1, False),
])
def test_feedback_deltas(kind, start, confidence, access, tagged):
    m = make()
    r = m.add("feedback target record", "conformance", confidence=start)
    m.feedback(r.id, kind)
    after = m.store.get(r.id)
    assert after.confidence == pytest.approx(confidence, abs=1e-9)
    assert after.accessCount == access and ("review" in after.tags) == tagged


def test_superseded_record_ranks_below_its_replacement():
    m = make()
    fresh = m.add("we deploy the api with docker on mondays", "conformance", confidence=0.9, layer="long_term")
    old = m.add("we deploy the api with docker on fridays", "conformance", confidence=0.9, layer="long_term")
    m.store.supersede(old.id, fresh.id, "newer schedule")
    order = [r.memory.id for r in m.query("when do we deploy the api with docker", threshold=0, top_n=10).memories]
    assert order.index(fresh.id) < order.index(old.id)
    assert m.store.get(old.id) is not None  # penalized, never deleted


def test_confidence_multiplies_the_score():
    m = make()
    high = m.add("the deploy window is monday morning", "conformance", confidence=0.9)
    low = m.add("the deploy window is monday morning", "conformance", confidence=0.4)
    result = m.query("deploy window", threshold=0, top_n=10)
    assert [r.memory.id for r in result.memories] == [high.id, low.id]
    assert result.trace["scores"][low.id] == pytest.approx(result.trace["scores"][high.id] * 0.4 / 0.9, abs=1e-3)


def test_score_formula_by_hand():
    m = make()
    r = m.add("league scoring", "test", tags=["fantasy:scoring"], confidence=0.5)
    # Query = content: semantic 1, keyword 1, tag 0, domain 1 (fantasy), entity 0 (no capitalized words),
    # layer working 0.8, recency 1 (same instant), not superseded.
    raw = 0.35 + 0.20 + 0 + 0.10 + 0 + 0.05 * 0.8 + 0.05
    assert m.retrieval.score(r, "league scoring") == pytest.approx(raw * 0.5)


def test_recency_decays_with_a_14_day_constant():
    now = [T0]
    m = HMEM(clock=lambda: now[0])
    r = m.add("league scoring", "test")
    fresh = m.retrieval.score(r, "unrelated words")
    now[0] = T0 + 14 * DAY
    stale = m.retrieval.score(r, "unrelated words")
    assert fresh - stale == pytest.approx(0.05 * (1 - math.exp(-1)) * 0.7)  # default confidence 0.7


def test_threshold_and_top_n_defaults():
    m = make()
    for i in range(7):
        m.add(f"deploy window note number {i}", "test", confidence=1.0)
    m.add("completely unrelated parking note", "test", confidence=0.2)
    result = m.query("deploy window note")
    assert len(result.memories) == 5  # top N 5
    assert all(r.relevance >= 0.35 for r in result.memories)


def test_query_touches_and_ledgers_reads():
    m = make()
    r = m.add("the deploy window is monday morning", "test", confidence=1.0)
    m.query("deploy window", threshold=0)
    assert m.store.get(r.id).accessCount == 1
    assert [e["action"] for e in m.ledger.history(r.id)] == ["create", "read"]


def test_review_tagged_memories_are_not_reinjected():
    m = make()
    r = m.add("the deploy window is monday morning", "test", confidence=1.0)
    m.feedback(r.id, "wrong")
    assert m.query("deploy window", threshold=0).memories == []
    assert m.query("deploy window", threshold=0, include_review=True).memories


def test_reinjection_block_is_grouped_by_domain():
    m = make()
    a = m.add("League scoring is half-PPR.", "test", type="preference", tags=["fantasy:scoring=half"], confidence=1.0)
    m.add("we deploy the api with docker", "test", confidence=1.0)
    result = m.query("league scoring docker deploy", threshold=0, top_n=10)
    lines = result.context.splitlines()
    assert lines[0] == "[MEMORY CONTEXT]" and lines[-1] == "[/MEMORY CONTEXT]"
    assert "## fantasy" in lines and "## tech" in lines
    assert f"- [WK] League scoring is half-PPR. (entities: league, ppr) <{a.id}>" in lines
    assert result.trace["strategy"] == "personal"


def test_ledger_reconstructs_create_then_feedback(tmp_path):
    m = make(tmp_path)
    r = m.add("audited record", "conformance", confidence=0.7)
    m.feedback(r.id, "wrong")
    history = m.ledger.history(r.id)
    assert [e["action"] for e in history] == ["create", "feedback"]
    assert history[-1]["previousState"]["confidence"] == 0.7
    assert history[-1]["newState"]["confidence"] == pytest.approx(0.5)
    lines = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert lines == history
    assert set(lines[0]) == {"id", "memoryId", "action", "actor", "timestamp", "newState"}
    assert "embedding" not in lines[0]["newState"]


def test_supersede_is_an_audited_update():
    m = make()
    old = m.add("League scoring is PPR.", "test")
    new = m.add("League scoring is half-PPR.", "test", supersedes=old.id)
    m.store.supersede(old.id, new.id, "scoring changed")
    entry = m.ledger.history(old.id)[-1]
    assert entry["action"] == "update"
    assert (entry["previousState"]["supersededBy"], entry["newState"]["supersededBy"]) == (None, new.id)


def test_state_survives_a_new_instance(tmp_path):
    first = make(tmp_path, actor="user:u1")
    r = first.add("League scoring is half-PPR.", "test", confidence=0.9)
    first.feedback(r.id, "helpful")
    second = make(tmp_path, actor="user:u1")
    again = second.store.get(r.id)
    assert again.confidence == pytest.approx(0.95) and again.accessCount == 1
    assert [e["action"] for e in second.ledger.history(r.id)] == ["create", "feedback"]


def test_related_records_link_both_ways():
    m = make()
    a = m.add("George Kittle is on the roster", "test")
    b = m.add("Kittle had 24.9% of targets", "test")
    assert a.id in b.relatedTo and b.id in a.relatedTo


@pytest.mark.parametrize("raw, expected", [
    ('["12-team league", "half-PPR scoring"]', ["12-team league", "half-PPR scoring"]),
    ('```json\n["My WR is Davante Adams"]\n```', ["My WR is Davante Adams"]),
    ('<think>hmm</think> Here: ["Half-PPR scoring", 3, "tiny"]', ["Half-PPR scoring"]),
    ("no json at all", []),
    ('{"facts": []}', []),
])
def test_parse_strict_json_array(raw, expected):
    assert hmem.parse_strict_json_array(raw) == expected


def test_mining_uses_the_injected_miner_fn():
    prompts = []
    m = make(miner_fn=lambda p: prompts.append(p) or '["half-PPR scoring"]')
    assert m.mining.extract("chat_message", "we play half point ppr", "Only league facts.") == ["half-PPR scoring"]
    assert prompts[0].startswith("Extract durable memories from this chat_message as a strict JSON array")
    assert "Only league facts." in prompts[0] and prompts[0].endswith("we play half point ppr")
    with pytest.raises(RuntimeError):
        make().mining.extract("chat_message", "text")


def test_embedder_matches_the_reference_port():
    # FNV-1a of "a" is 0xe40c292c in the reference (32-bit, Math.imul).
    assert hmem._fnv1a("a") == 0xE40C292C
    v = hmem.embed("deploy window")
    assert sum(x * x for x in v) == pytest.approx(1.0)
    assert hmem.embed("") == [0.0] * hmem.EMBED_DIM
