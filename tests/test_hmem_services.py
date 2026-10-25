"""The H-MEM sleep, conflict and dreaming services, and the conformance bridge for them.

tests/data/hmem_conformance_vectors.json is engines/hmem/conformance/vectors/vectors.json
from github.com/Meterless/Meterless at commit 1742dec (Apache-2.0), unchanged. The three
vector checks below mirror runner.ts for sg-001, cg-001 and db-001, first in process,
then through scripts/hmem_conformance/bridge.py, one process per call, as the shim runs it.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.engines.hmem import DAY_MS, HMEM, SleepPreview

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "scripts" / "hmem_conformance" / "bridge.py"
VECTORS = json.loads((Path(__file__).parent / "data" / "hmem_conformance_vectors.json").read_text())
T0 = VECTORS["clock"]
SLEEP, CONFLICT, DREAM = (VECTORS["sections"][k][0] for k in ("sleep-guardrails", "conflict-gate", "dream-boundary"))


# --- the three vectors, in process ------------------------------------------


def test_sg001_sleep_guardrails():
    now = [T0]
    m = HMEM(clock=lambda: now[0])
    keys = {r["key"]: m.add(r["content"], r["source"], derived_from=r.get("derivedFrom")) for r in SLEEP["records"]}
    now[0] = T0 + SLEEP["ageDays"] * DAY_MS
    before = sorted(r.id for r in m.store.all())
    preview = m.sleep.preview()
    assert sorted(r.id for r in m.store.all()) == before, "preview must not change the store"
    for k in SLEEP["expectArchived"]:
        assert keys[k].id in preview.toArchive
    for k in SLEEP["expectProtected"]:
        assert keys[k].id not in preview.toArchive
    report = m.sleep.execute(preview)
    for k in SLEEP["expectProtected"]:
        assert m.store.get(keys[k].id) is not None
    assert report.backupId


def test_cg001_conflict_gate():
    m = HMEM(clock=lambda: T0)
    a = m.add(CONFLICT["a"]["content"], "conformance", confidence=CONFLICT["a"]["confidence"])
    b = m.add(CONFLICT["b"]["content"], "conformance", confidence=CONFLICT["b"]["confidence"])
    found = m.conflicts.scan()
    assert found, "an always/never pair on similar content must be detected"
    outcome = m.conflicts.auto_resolve(found[0])
    assert outcome in ("resolved", "queued")
    if outcome == "resolved":
        assert any(r.supersededBy for r in (m.store.get(a.id), m.store.get(b.id)))
    assert m.store.get(a.id) and m.store.get(b.id), "conflict resolution never deletes"


def test_db001_dream_boundary():
    m = HMEM(clock=lambda: T0)
    for r in DREAM["records"]:
        m.add(r["content"], "conformance", type=r["type"])
    count = len(m.store.all())
    proposals = m.dreaming.dream()
    assert proposals, "two related preferences must produce a proposal"
    assert len(m.store.all()) == count, "nothing materializes before approval"
    created = m.dreaming.approve(proposals[0].id)
    if created:
        assert created.layer == "long_term" and created.derivedFrom


# --- the same three through the bridge, one process per call -----------------


class Shim:
    """What scripts/hmem_conformance/index.ts does: one bridge.py process per call."""

    def __init__(self, folder: Path, clock: int) -> None:
        self.folder, self.clock = folder, clock

    def __call__(self, op: str, **args):
        req = {"dir": str(self.folder), "clock": self.clock, "op": op, "args": args, "overrides": {}}
        out = subprocess.run([sys.executable, str(BRIDGE)], input=json.dumps(req), capture_output=True,
                             text=True, check=True, timeout=60)
        reply = json.loads(out.stdout)
        assert "error" not in reply, reply
        return reply["ok"]


def test_bridge_sleep(tmp_path):
    call = Shim(tmp_path, T0)
    keys = {r["key"]: call("add", content=r["content"], source=r["source"], derivedFrom=r.get("derivedFrom"))
            for r in SLEEP["records"]}
    call.clock = T0 + SLEEP["ageDays"] * DAY_MS
    preview = call("sleep_preview")
    assert keys["plain"]["id"] in preview["toArchive"] and keys["derived"]["id"] not in preview["toArchive"]
    report = call("sleep_execute", preview=preview)
    assert report["backupId"] and report["archived"] == 1
    assert call("get", id=keys["derived"]["id"]) is not None
    assert call("get", id=keys["plain"]["id"]) is None
    call("sleep_restore", backupId=report["backupId"])  # the backup survived the process ending
    assert call("get", id=keys["plain"]["id"]) is not None


def test_bridge_conflicts(tmp_path):
    call = Shim(tmp_path, T0)
    a = call("add", content=CONFLICT["a"]["content"], source="conformance", confidence=CONFLICT["a"]["confidence"])
    b = call("add", content=CONFLICT["b"]["content"], source="conformance", confidence=CONFLICT["b"]["confidence"])
    found = call("conflicts_scan")
    assert found
    assert call("conflicts_auto_resolve", conflict=found[0]) in ("resolved", "queued")
    assert call("get", id=a["id"]) and call("get", id=b["id"])


def test_bridge_dreaming(tmp_path):
    call = Shim(tmp_path, T0)
    for r in DREAM["records"]:
        call("add", content=r["content"], source="conformance", type=r["type"])
    proposals = call("dream")
    assert proposals and len(call("all")) == 2
    created = call("dream_approve", id=proposals[0]["id"])  # proposals survived the process ending
    if created:
        assert created["layer"] == "long_term" and created["derivedFrom"]


# --- service behavior ---------------------------------------------------------


def test_sleep_consolidates_stale_short_term_and_restore_undoes_it(tmp_path):
    now = [T0]
    m = HMEM(clock=lambda: now[0], persist_dir=tmp_path)
    r = m.add("a quick note about my bench depth", "test", layer="short_term")
    now[0] += 8 * DAY_MS
    report = m.sleep.execute()
    assert report.consolidated == 1 and m.store.get(r.id).layer == "long_term"
    assert (tmp_path / "backups" / f"{report.backupId}.json").is_file()
    later = HMEM(clock=lambda: now[0], persist_dir=tmp_path)  # a new instance restores from disk
    later.sleep.restore(report.backupId)
    assert later.store.get(r.id).layer == "short_term"
    assert later.ledger.entries[-1]["action"] == "restore"


def test_sleep_synthesizes_near_duplicates_with_lineage():
    m = HMEM(clock=lambda: T0)
    a = m.add("the user plays in a half ppr league", "test")
    b = m.add("the user plays in a half ppr league", "test")
    preview = m.sleep.preview()
    assert preview.toSynthesize == [[a.id, b.id]]
    m.sleep.execute(preview)
    [merged] = m.store.all()
    assert merged.derivedFrom == [a.id, b.id] and merged.layer == "long_term"
    assert m.ledger.stats()["sleep_synthesize"] == 1


@pytest.mark.parametrize("guard", ["supersedes", "hub"])
def test_sleep_never_archives_superseding_records_or_hubs(guard):
    now = [T0]
    m = HMEM(clock=lambda: now[0])
    r = m.add("a one-off note nobody reads", "test")
    if guard == "supersedes":
        r.supersedes = "mem-older"
    else:
        r.relatedTo = ["mem-a", "mem-b", "mem-c"]
    now[0] += 40 * DAY_MS
    assert r.id not in m.sleep.preview().toArchive


def test_sleep_preview_dict_round_trip():
    now = [T0]
    m = HMEM(clock=lambda: now[0])
    r = m.add("a one-off note nobody reads", "test")
    now[0] += 40 * DAY_MS
    preview = SleepPreview(**json.loads(json.dumps(m.sleep.preview().__dict__)))
    assert m.sleep.execute(preview.__dict__).archived == 1 and m.store.get(r.id) is None


def test_restore_rejects_unknown_backup():
    with pytest.raises(KeyError):
        HMEM(clock=lambda: T0).sleep.restore("backup-000000000000")
    with pytest.raises(KeyError):
        HMEM(clock=lambda: T0).sleep.restore("../../etc/passwd")


def test_conflict_with_close_weights_is_queued():
    m = HMEM(clock=lambda: T0)
    m.add("always start Christian Watson", "test", confidence=0.7)
    m.add("never start Christian Watson", "test", confidence=0.7)
    found = m.conflicts.scan()
    assert found and m.conflicts.auto_resolve(found[0]) == "queued"
    assert m.conflicts.queue() == found
    assert m.ledger.stats()["conflict_detected"] == 1


def test_superseded_pair_is_not_a_conflict():
    m = HMEM(clock=lambda: T0)
    old = m.add("the user's league uses half-PPR scoring", "test")
    new = m.add("the user's league uses PPR scoring", "test", supersedes=old.id)
    m.store.supersede(old.id, new.id, "scoring changed")
    assert m.conflicts.scan() == []


def test_resolved_conflict_is_ledgered_with_both_states():
    m = HMEM(clock=lambda: T0)
    m.add(CONFLICT["a"]["content"], "conformance", confidence=CONFLICT["a"]["confidence"])
    loser = m.add(CONFLICT["b"]["content"], "conformance", confidence=CONFLICT["b"]["confidence"])
    assert m.conflicts.auto_resolve(m.conflicts.scan()[0]) == "resolved"
    entry = m.ledger.history(loser.id)[-1]
    assert entry["action"] == "conflict_resolved"
    assert entry["previousState"]["supersededBy"] is None and entry["newState"]["supersededBy"]


def test_rejected_dream_never_materializes(tmp_path):
    m = HMEM(clock=lambda: T0, persist_dir=tmp_path)
    for r in DREAM["records"]:
        m.add(r["content"], "conformance", type=r["type"])
    proposal = m.dreaming.dream()[0]
    m.dreaming.reject(proposal.id)
    assert len(m.store.all()) == 2
    with pytest.raises(KeyError):
        HMEM(clock=lambda: T0, persist_dir=tmp_path).dreaming.approve(proposal.id)
    assert {"dream_proposed", "dream_rejected"} <= set(m.ledger.stats())


def test_domain_proposal_updates_the_source_record():
    m = HMEM(clock=lambda: T0)
    r = m.add("a note", "test")
    assert r.domain == "general"
    r.content = "refactor the database api"  # now tech keywords, still filed as general
    proposal = next(p for p in m.dreaming.dream() if p.type == "domain")
    assert m.dreaming.approve(proposal.id) is None
    assert m.store.get(r.id).domain == "tech"
