"""H-MEM: human-style memory for agents (store, retrieval, ledger, mining, conflicts, sleep, dreaming).

Implements the Meterless H-MEM spec: github.com/Meterless/Meterless, engines/hmem
(AGENTS.md, docs/, conformance/; Apache-2.0; read at commit 1742dec). The spec is a
reference architecture to implement, not a package; this module follows its record
shape, service names, ranking formula, feedback deltas, reinjection format and
append-only trust ledger. The deterministic embedder is a port of the reference's
FNV-1a mock (reference/src/embeddings.ts).

Services (spec section 11): MemoryStoreService, MemoryRetrievalService,
MemoryMiningService (model extraction only; callers do their own code-first mining),
TrustLedgerService, ConflictDetectionService (scan, gated auto-resolve),
SleepCycleService (preview, execute with backup, restore) and DreamingService
(proposals behind an approval boundary). League memory sets supersession itself when a
newer fact replaces an older one (supersedes / supersededBy); conflict resolution sets
it the same way. Neither deletes the old record; only the sleep cycle deletes.

Storage: with persist_dir, records live in <persist_dir>/state.json, dream proposals in
dreams.json and sleep backups in backups/; with ledger_path, every mutation is appended
to that JSONL file. Without them everything stays in memory. Times are epoch
milliseconds from an injectable clock.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

FEEDBACK_DELTAS = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.20}
LEDGER_ACTIONS = (
    "create", "read", "update", "delete", "feedback", "promote", "demote", "merge",
    "conflict_detected", "conflict_resolved", "sleep_consolidate", "sleep_archive",
    "sleep_synthesize", "dream_proposed", "dream_approved", "dream_rejected", "restore",
)
MEMORY_TYPES = ("personal", "factual", "preference", "general")
LAYERS = ("short_term", "working", "long_term")
LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
DEFAULTS = {
    "retrieval_top_n": 5,
    "retrieval_threshold": 0.35,  # on the final score, after the confidence multiplier
    "entity_cap": 10,
    "related_cap": 5,
    "recency_days": 14,
    # spec section 13, operational defaults
    "consolidation_days": 7,
    "archive_min_days": 30,
    "archive_max_access": 2,
    "synthesis_cosine": 0.82,
    "dream_cluster_min_size": 2,
    "dream_relatedness": 0.35,
    "max_dream_proposals_per_type": 8,
    "conflict_auto_resolve_gate": 0.70,
}
HUB_THRESHOLD = 3  # relatedTo links that make a record a relationship hub, never archived
DAY_MS = 24 * 60 * 60 * 1000
EMBED_DIM = 64

DOMAIN_KEYWORDS = {
    "fantasy": ["fantasy", "league", "scoring", "ppr", "roster", "waiver", "lineup", "points",
                "start", "sit", "targets", "qb", "rb", "wr", "te", "wr1", "rb1", "te1", "nfl"],
    "tech": ["code", "bug", "api", "database", "deploy", "framework", "library", "server",
             "react", "python", "typescript", "docker", "sql"],
    "work": ["meeting", "deadline", "client", "project", "sprint", "review", "report"],
    "personal": ["family", "hobby", "prefer", "like", "dislike", "morning", "evening"],
}
CORRECTION = re.compile(r"\b(actually|instead|no longer|not anymore|changed to|correction)\b", re.I)
NOT_ENTITIES = {"the", "this", "that", "with", "who", "what", "when", "why", "how"}

Clock = Callable[[], int]


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def now_ms() -> int:
    return int(time.time() * 1000)


# --- deterministic embedder (port of the reference's mock) ---


def tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", re.sub(r"[^a-z0-9\s]", " ", text.lower())) if len(t) > 1]


def _fnv1a(text: str) -> int:
    h = 0x811C9DC5
    for ch in text:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def embed(text: str) -> list[float]:
    vec = [0.0] * EMBED_DIM
    for token in tokenize(text):
        h = _fnv1a(token)
        sign = 1 if (h >> 8) % 2 == 0 else -1
        vec[h % EMBED_DIM] += sign * (1 + ((h >> 16) % 8) / 8)
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0 else [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both unit length


def jaccard(a, b) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


# --- the record (spec section 2, docs/memory-record.md) ---


@dataclass
class MemoryRecord:
    id: str
    content: str
    type: str
    layer: str
    timestamp: int
    lastAccessed: int
    accessCount: int
    tags: list[str]
    confidence: float  # mandatory
    source: str  # mandatory; a record without one is rejected by construction
    provenance: dict[str, Any]  # {origin, learnedAt, label, refs?}
    domain: str
    namespace: str
    entities: list[str] = field(default_factory=list)  # cap 10
    relatedTo: list[str] = field(default_factory=list)  # cap 5
    embedding: list[float] = field(default_factory=list)
    chatId: str | None = None
    missionId: str | None = None
    goalRunId: str | None = None
    supersedes: str | None = None
    supersededBy: str | None = None  # drives the retrieval penalty; never deleted
    derivedFrom: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        """The record without its embedding, for ledger states."""
        data = dataclasses.asdict(self)
        data.pop("embedding")
        return data


@dataclass
class RetrievedMemory:
    memory: MemoryRecord
    relevance: float


@dataclass
class QueryResult:
    memories: list[RetrievedMemory]
    context: str  # the reinjection block
    trace: dict[str, Any]  # retrievalReason, strategy, scores, ...


# --- trust ledger (spec section 9) ---


class TrustLedgerService:
    """Append-only audit of every mutation and read. Entries are never changed or removed."""

    def __init__(self, clock: Clock, path: Path | None = None) -> None:
        self.clock, self.path = clock, path
        self.entries: list[dict[str, Any]] = []
        if path and path.is_file():
            self.entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def log(
        self, memory_id: str, action: str, actor: str, *, previous_state: dict | None = None,
        new_state: dict | None = None, details: dict | None = None,
    ) -> dict[str, Any]:
        if action not in LEDGER_ACTIONS:
            raise ValueError(f"H-MEM: unknown ledger action {action!r}")
        entry = {"id": f"led-{uuid.uuid4().hex[:12]}", "memoryId": memory_id, "action": action,
                 "actor": actor, "timestamp": self.clock()}
        for key, value in (("previousState", previous_state), ("newState", new_state), ("details", details)):
            if value is not None:
                entry[key] = value
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e["memoryId"] == memory_id]

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries:
            out[e["action"]] = out.get(e["action"], 0) + 1
        return out


# --- store with enrichment (spec sections 2, 3, 5) ---


class MemoryStoreService:
    def __init__(self, clock: Clock, ledger: TrustLedgerService, actor: str, persist_dir: Path | None = None) -> None:
        self.clock, self.ledger, self.actor = clock, ledger, actor
        self.records: dict[str, MemoryRecord] = {}
        self.state_file = persist_dir / "state.json" if persist_dir else None
        if self.state_file and self.state_file.is_file():
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
            for r in saved["records"]:
                record = MemoryRecord(**r)
                record.embedding = record.embedding or embed(record.content)  # backfill
                self.records[record.id] = record

    def persist(self) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        records = [dataclasses.asdict(r) for r in sorted(self.records.values(), key=lambda r: r.timestamp)]
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"records": records}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.state_file)

    def add(
        self, content: str, source: str, *, type: str = "general", layer: str = "working",
        tags: list[str] | None = None, confidence: float = 0.7, provenance: dict[str, Any] | None = None,
        entities: list[str] | None = None, chat_id: str | None = None, mission_id: str | None = None,
        goal_run_id: str | None = None, supersedes: str | None = None, derived_from: list[str] | None = None,
    ) -> MemoryRecord:
        if not source or not source.strip():
            raise ValueError("H-MEM: a memory record with no source is rejected by construction (spec section 2)")
        if type not in MEMORY_TYPES or layer not in LAYERS:
            raise ValueError(f"H-MEM: bad type {type!r} or layer {layer!r}")
        now = self.clock()
        tags = list(tags or [])
        domain = self.classify_domain(content, tags, type)
        found = self.extract_entities(content)
        record = MemoryRecord(
            id=f"mem-{uuid.uuid4().hex[:12]}", content=content, type=type, layer=layer,
            timestamp=now, lastAccessed=now, accessCount=0, tags=tags,
            confidence=clamp01(confidence), source=source,
            provenance=provenance or {"origin": "manual", "learnedAt": now, "label": source},
            domain=domain, namespace=_namespace(domain, type),
            entities=list(dict.fromkeys([*(entities or []), *found]))[: DEFAULTS["entity_cap"]],
            embedding=embed(content), chatId=chat_id, missionId=mission_id, goalRunId=goal_run_id,
            supersedes=supersedes, derivedFrom=list(derived_from or []),
        )
        self._discover_relationships(record)
        self.records[record.id] = record
        self.ledger.log(record.id, "create", self.actor, new_state=record.snapshot())
        self.persist()
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self.records.get(memory_id)

    def all(self) -> list[MemoryRecord]:
        return list(self.records.values())

    def update(self, memory_id: str, details: dict | None = None, **patch: Any) -> MemoryRecord:
        record = self._must_get(memory_id)
        previous = record.snapshot()
        for key, value in patch.items():
            if not hasattr(record, key) or key in ("id", "embedding"):
                raise ValueError(f"H-MEM: cannot update {key!r}")
            setattr(record, key, value)
        if "content" in patch:
            record.embedding = embed(record.content)
        self.ledger.log(memory_id, "update", self.actor, previous_state=previous, new_state=record.snapshot(),
                        details=details)
        self.persist()
        return record

    def supersede(self, old_id: str, new_id: str, reason: str) -> None:
        """Mark old as replaced by new: penalized in ranking, kept in the store and the ledger."""
        self.update(old_id, details={"reason": reason, "supersededBy": new_id}, supersededBy=new_id)

    def touch(self, memory_id: str) -> None:
        record = self._must_get(memory_id)
        record.lastAccessed = self.clock()
        record.accessCount += 1

    def promote(self, memory_id: str, layer: str) -> None:
        if layer not in LAYERS:
            raise ValueError(f"H-MEM: bad layer {layer!r}")
        record = self._must_get(memory_id)
        previous = record.snapshot()
        record.layer = layer
        self.ledger.log(memory_id, "promote", self.actor, previous_state=previous, new_state=record.snapshot())
        self.persist()

    def delete(self, memory_id: str, reason: str) -> None:
        """Only the sleep cycle deletes (archive, synthesis); the ledger keeps the last state."""
        record = self._must_get(memory_id)
        del self.records[memory_id]
        self.ledger.log(memory_id, "delete", self.actor, previous_state=record.snapshot(), details={"reason": reason})
        self.persist()

    def snapshot_all(self) -> list[dict[str, Any]]:
        return [dataclasses.asdict(r) for r in self.records.values()]

    def restore_all(self, records: list[dict[str, Any]]) -> None:
        self.records = {r["id"]: MemoryRecord(**r) for r in records}
        self.persist()

    def _must_get(self, memory_id: str) -> MemoryRecord:
        record = self.records.get(memory_id)
        if record is None:
            raise KeyError(f"H-MEM: unknown memory id {memory_id}")
        return record

    def classify_domain(self, content: str, tags: list[str], type: str) -> str:
        """Multi-pass: explicit tags first, then weighted keywords (spec section 5)."""
        for tag in tags:
            if tag.startswith("project:"):
                return tag[len("project:"):]
            prefix = tag.split(":", 1)[0]
            if ":" in tag and prefix in DOMAIN_KEYWORDS:
                return prefix
        tokens = set(tokenize(content))
        best, best_score = "general", 0
        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for k in keywords if k in tokens)
            if domain == "personal" and type in ("personal", "preference"):
                score += 1
            if score > best_score:
                best, best_score = domain, score
        return best

    def extract_entities(self, content: str) -> list[str]:
        found = [m.lower() for m in re.findall(r"\b([A-Z][a-zA-Z]{2,})\b", content)]
        return list(dict.fromkeys(e for e in found if e not in NOT_ENTITIES))[: DEFAULTS["entity_cap"]]

    def _discover_relationships(self, record: MemoryRecord) -> None:
        cap = DEFAULTS["related_cap"]
        for other in self.records.values():
            if len(record.relatedTo) >= cap:
                break
            if not record.supersedes and cosine(record.embedding, other.embedding) > 0.85 and CORRECTION.search(record.content):
                record.supersedes = other.id
                continue
            if set(other.entities) & set(record.entities) and other.domain == record.domain:
                record.relatedTo.append(other.id)
                if len(other.relatedTo) < cap and record.id not in other.relatedTo:
                    other.relatedTo.append(record.id)  # bidirectional


def _namespace(domain: str, type: str) -> str:
    bucket = "profile" if type in ("preference", "personal") else "facts" if type == "factual" else "notes"
    return f"{domain}/{bucket}"


# --- retrieval and reinjection (spec section 6) ---


class MemoryRetrievalService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Clock, actor: str) -> None:
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor

    def score(self, memory: MemoryRecord, query: str) -> float:
        return self._score(memory, *self._prepare(query))

    def _prepare(self, query: str) -> tuple[list[float], list[str], list[str], str]:
        return (embed(query), tokenize(query)[:8], self.store.extract_entities(query),
                self.store.classify_domain(query, [], "general"))

    def _score(self, m: MemoryRecord, q_embedding, q_tokens, q_entities, q_domain) -> float:
        """raw = .35 semantic + .20 keyword + .10 tag + .10 domain + .15 entity + .05 layer
        + .05 recency - .20 superseded; score = clamp01(raw) * confidence."""
        semantic = clamp01(cosine(q_embedding, m.embedding))
        keyword = jaccard(q_tokens, tokenize(m.content))
        tag = jaccard(q_tokens, [t.lower() for t in m.tags])
        domain = 1.0 if m.domain == q_domain else 0.0
        entity = jaccard(q_entities, m.entities)
        recency = math.exp(-((self.clock() - m.lastAccessed) / DAY_MS) / DEFAULTS["recency_days"])
        superseded = 1.0 if m.supersededBy else 0.0
        raw = (0.35 * semantic + 0.20 * keyword + 0.10 * tag + 0.10 * domain + 0.15 * entity
               + 0.05 * LAYER_WEIGHT[m.layer] + 0.05 * recency - 0.20 * superseded)
        return clamp01(raw) * m.confidence

    def query(
        self, query: str, top_n: int | None = None, threshold: float | None = None,
        chat_id: str | None = None, include_review: bool = False,
    ) -> QueryResult:
        """Hybrid ranking, top N above threshold; each memory returned is touched and its read ledgered.

        Memories tagged "review" (marked wrong) are left out unless include_review (spec reinjection rules).
        """
        top_n = DEFAULTS["retrieval_top_n"] if top_n is None else top_n
        threshold = DEFAULTS["retrieval_threshold"] if threshold is None else threshold
        prepared = self._prepare(query)
        scored, suppressed = [], 0
        for m in self.store.all():
            if chat_id and m.chatId and m.chatId != chat_id:
                continue
            if "review" in m.tags and not include_review:
                continue
            s = self._score(m, *prepared)
            if s >= threshold:
                scored.append(RetrievedMemory(m, s))
        scored.sort(key=lambda r: (-r.relevance, r.memory.id))
        top = scored[:top_n]
        for r in top:
            self.store.touch(r.memory.id)
            self.ledger.log(r.memory.id, "read", self.actor, details={"query": query[:300]})
            suppressed += 1 if r.memory.supersededBy else 0
        self.store.persist()
        personal = any(r.memory.type in ("personal", "preference") for r in top)
        strategy = "minimal" if len(top) <= 1 else "personal" if personal else "comprehensive"
        return QueryResult(top, self.format_reinjection(top), {
            "retrievalReason": f'hybrid ranking for "{query[:120]}" (domain: {prepared[3]})',
            "strategy": strategy,
            "queryDomain": prepared[3],
            "queryEntities": prepared[2],
            "scores": {r.memory.id: round(r.relevance, 4) for r in top},
            "supersededReturned": suppressed,
            "weights": "hmem-spec@1742dec",
            "threshold": threshold,
            "topN": top_n,
        })

    @staticmethod
    def format_reinjection(items: list[RetrievedMemory]) -> str:
        """Domain-grouped block with layer markers and entities (spec section 6.2)."""
        if not items:
            return ""
        lines = ["[MEMORY CONTEXT]"]
        for domain in sorted({r.memory.domain for r in items}):
            lines.append(f"## {domain}")
            for r in (r for r in items if r.memory.domain == domain):
                m = r.memory
                marker = {"long_term": "LT", "working": "WK", "short_term": "ST"}[m.layer]
                ents = f" (entities: {', '.join(m.entities)})" if m.entities else ""
                old = " (superseded)" if m.supersededBy else ""
                lines.append(f"- [{marker}] {m.content}{old}{ents} <{m.id}>")
        lines.append("[/MEMORY CONTEXT]")
        return "\n".join(lines)

    def feedback(self, memory_id: str, kind: str) -> None:
        """Exact deltas (spec section 9.2): helpful +0.05 and accessCount + 1, not_helpful -0.03,
        wrong -0.20 and a "review" tag; confidence is clamped to [0, 1]."""
        if kind not in FEEDBACK_DELTAS:
            raise ValueError(f"H-MEM: feedback kind must be one of {', '.join(FEEDBACK_DELTAS)}")
        m = self.store._must_get(memory_id)
        previous = m.snapshot()
        if kind == "helpful":
            m.accessCount += 1
        m.confidence = round(clamp01(m.confidence + FEEDBACK_DELTAS[kind]), 10)
        if kind == "wrong" and "review" not in m.tags:
            m.tags.append("review")
        self.ledger.log(memory_id, "feedback", self.actor, previous_state=previous, new_state=m.snapshot(),
                        details={"kind": kind, "delta": FEEDBACK_DELTAS[kind]})
        self.store.persist()


# --- mining: the model extraction step (spec section 4.1) ---


def parse_strict_json_array(raw: str) -> list[str]:
    """Strings from a JSON array reply; fences, <think> blocks and noise around it are tolerated."""
    text = re.sub(r"(?s)<think>.*?</think>", "", raw).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"```\s*$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [x.strip() for x in parsed if isinstance(x, str) and len(x.strip()) >= 6]


class MemoryMiningService:
    """Builds an event-specific extraction prompt and asks the injected miner_fn for
    a strict JSON array of memory strings. Callers validate and store what comes back."""

    def __init__(self, miner_fn: Callable[[str], str] | None = None) -> None:
        self.miner_fn = miner_fn

    def extract(self, event: str, text: str, instructions: str = "") -> list[str]:
        """Raises RuntimeError if no miner_fn was injected; miner_fn's own errors propagate."""
        if self.miner_fn is None:
            raise RuntimeError("H-MEM: no miner_fn injected")
        prompt = (
            f"Extract durable memories from this {event} as a strict JSON array of strings."
            + (f"\n{instructions}" if instructions else "") + f"\n\n{text[:8000]}"
        )
        return parse_strict_json_array(self.miner_fn(prompt))


# --- conflicts (spec section 10): losers are marked supersededBy, never deleted ---

OPPOSING_PAIRS = [
    (re.compile(r"\balways\b", re.I), re.compile(r"\bnever\b", re.I)),
    (re.compile(r"\benable[ds]?\b", re.I), re.compile(r"\bdisable[ds]?\b", re.I)),
    (re.compile(r"\bprefer[s]?\b", re.I), re.compile(r"\bavoid[s]?\b|\bdislike[s]?\b", re.I)),
    (re.compile(r"\bon\b", re.I), re.compile(r"\boff\b", re.I)),
    (re.compile(r"\byes\b", re.I), re.compile(r"\bno\b", re.I)),
]
NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class ConflictRecord:
    id: str
    memoryA: str
    memoryB: str
    reason: str
    confidence: float
    resolved: bool = False
    resolution: str | None = None  # keep_a | keep_b


class ConflictDetectionService:
    """Scan pairs for contradictions; auto-resolve only at decision confidence >= 0.70."""

    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Clock, actor: str) -> None:
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor
        self.found: list[ConflictRecord] = []

    def scan(self) -> list[ConflictRecord]:
        records = self.store.all()
        found = []
        for i, a in enumerate(records):
            for b in records[i + 1:]:
                conflict = self._check(a, b)
                if conflict:
                    found.append(conflict)
                    self.ledger.log(a.id, "conflict_detected", self.actor, details={
                        "with": b.id, "reason": conflict.reason, "confidence": conflict.confidence})
        self.found.extend(found)
        return found

    def _check(self, a: MemoryRecord, b: MemoryRecord) -> ConflictRecord | None:
        if b.id in (a.supersedes, a.supersededBy) or a.id in (b.supersedes, b.supersededBy):
            return None  # an intended replacement, not a conflict
        sim = cosine(a.embedding, b.embedding)
        reason, confidence = "", 0.0
        for p, q in OPPOSING_PAIRS:
            if sim > 0.5 and ((p.search(a.content) and q.search(b.content)) or (q.search(a.content) and p.search(b.content))):
                reason, confidence = "opposing phrase pair on similar content", 0.5 + 0.3 * sim
        if not reason and sim > 0.8:
            nums_a, nums_b = NUMBER.findall(a.content), NUMBER.findall(b.content)
            if nums_a and nums_b and nums_a != nums_b:
                reason, confidence = "high-similarity conflicting numeric values", 0.55 + 0.25 * sim
        if not reason:
            return None
        if set(a.entities) & set(b.entities):
            confidence += 0.1
        if a.domain == b.domain:
            confidence += 0.05
        if b.id in a.relatedTo:
            confidence -= 0.1  # an explicit relation lowers false positives
        return ConflictRecord(f"conflict-{uuid.uuid4().hex[:12]}", a.id, b.id, reason, round(clamp01(confidence), 10))

    def auto_resolve(self, conflict: ConflictRecord | dict[str, Any]) -> str:
        """"resolved" (the loser gets supersededBy) or "queued" for a person to decide."""
        if isinstance(conflict, dict):
            conflict = ConflictRecord(**conflict)
        a, b = self.store.get(conflict.memoryA), self.store.get(conflict.memoryB)
        if a is None or b is None:
            return "queued"
        now = max(1, self.clock())

        def weight(m: MemoryRecord) -> float:
            return (0.3 * (m.lastAccessed / now) + 0.2 * min(1.0, m.accessCount / 10) + 0.25 * m.confidence
                    + 0.1 * min(1.0, len(m.content) / 200)
                    + 0.15 * (1.0 if m.provenance.get("origin") == "user_correction" else 0.5))

        wa, wb = weight(a), weight(b)
        margin = abs(wa - wb) / max(wa, wb)
        decision = clamp01(conflict.confidence * 0.6 + margin * 0.8)
        if decision < DEFAULTS["conflict_auto_resolve_gate"]:
            return "queued"
        winner, loser = (a, b) if wa >= wb else (b, a)
        previous = loser.snapshot()
        loser.supersededBy = winner.id
        conflict.resolved, conflict.resolution = True, "keep_a" if winner.id == conflict.memoryA else "keep_b"
        self.ledger.log(loser.id, "conflict_resolved", self.actor, previous_state=previous,
                        new_state=loser.snapshot(), details={"conflictId": conflict.id, "winner": winner.id,
                                                             "decisionConfidence": round(decision, 3)})
        self.store.persist()
        return "resolved"

    def queue(self) -> list[ConflictRecord]:
        return [c for c in self.found if not c.resolved]


# --- sleep cycle (spec section 8): preview first, backup before execute ---


@dataclass
class SleepPreview:
    toConsolidate: list[str]
    toArchive: list[str]
    toSynthesize: list[list[str]]


@dataclass
class SleepReport:
    backupId: str
    consolidated: int
    archived: int
    synthesized: int
    actionLog: list[str]


class SleepCycleService:
    """Consolidate stale short-term memories, archive low-value old ones, merge near-duplicates.

    Guardrails (spec 8.2): superseding records, derived/synthesized records and relationship
    hubs are never archived. Backups live in <persist_dir>/backups/ when the store persists.
    """

    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Clock, actor: str,
                 backup_dir: Path | None = None) -> None:
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor
        self.backup_dir = backup_dir
        self._backups: dict[str, list[dict[str, Any]]] = {}

    def preview(self) -> SleepPreview:
        """The full plan; changes nothing."""
        now, records = self.clock(), self.store.all()
        referenced: set[str] = set()
        for m in records:
            referenced.update(m.relatedTo)
            referenced.update(m.derivedFrom)
            if m.supersedes:
                referenced.add(m.supersedes)
        consolidate = [m.id for m in records if m.layer == "short_term"
                       and now - m.lastAccessed >= DEFAULTS["consolidation_days"] * DAY_MS]

        def archivable(m: MemoryRecord) -> bool:
            if now - m.timestamp < DEFAULTS["archive_min_days"] * DAY_MS:
                return False
            if m.accessCount > DEFAULTS["archive_max_access"] or m.id in referenced:
                return False
            return not (m.supersedes or m.derivedFrom or len(m.relatedTo) >= HUB_THRESHOLD)

        synthesize, used = [], set()
        for i, seed in enumerate(records):
            if seed.id in used:
                continue
            group = [seed] + [o for o in records[i + 1:] if o.id not in used
                              and cosine(seed.embedding, o.embedding) >= DEFAULTS["synthesis_cosine"]]
            if len(group) >= 2:
                used.update(g.id for g in group)
                synthesize.append([g.id for g in group])
        return SleepPreview(consolidate, [m.id for m in records if archivable(m)], synthesize)

    def execute(self, preview: SleepPreview | dict[str, Any] | None = None) -> SleepReport:
        if isinstance(preview, dict):
            preview = SleepPreview(**preview)
        plan = preview or self.preview()
        backup_id = f"backup-{uuid.uuid4().hex[:12]}"
        self._save_backup(backup_id, self.store.snapshot_all())
        log = [f"backup {backup_id} created"]
        for memory_id in plan.toConsolidate:
            if self.store.get(memory_id):
                self.store.promote(memory_id, "long_term")
                self.ledger.log(memory_id, "sleep_consolidate", self.actor, details={"from": "short_term", "to": "long_term"})
                log.append(f"consolidated {memory_id}")
        for memory_id in plan.toArchive:
            m = self.store.get(memory_id)
            if m:
                self.ledger.log(memory_id, "sleep_archive", self.actor,
                                details={"ageMs": self.clock() - m.timestamp, "accessCount": m.accessCount})
                self.store.delete(memory_id, "sleep archive")
                log.append(f"archived {memory_id}")
        synthesized = 0
        for group in plan.toSynthesize:
            members = [m for m in (self.store.get(i) for i in group) if m]
            if len(members) < 2:
                continue
            merged = self.store.add(
                "Synthesis: " + " | ".join(m.content for m in members), "sleep:synthesis",
                type="factual", layer="long_term", tags=list(dict.fromkeys(t for m in members for t in m.tags)),
                confidence=max(m.confidence for m in members), chat_id=members[0].chatId,
                provenance={"origin": "sleep_synthesis", "learnedAt": self.clock(),
                            "label": f"synthesized from {len(members)} memories"},
                derived_from=[m.id for m in members],
            )
            self.ledger.log(merged.id, "sleep_synthesize", self.actor, details={"sources": group})
            for m in members:
                self.store.delete(m.id, "merged by sleep synthesis")
            synthesized += 1
            log.append(f"synthesized {merged.id} from {', '.join(group)}")
        return SleepReport(backup_id, len(plan.toConsolidate), len(plan.toArchive), synthesized, log)

    def restore(self, backup_id: str) -> None:
        records = self._load_backup(backup_id)
        self.store.restore_all(records)
        self.ledger.log("*", "restore", self.actor, details={"backupId": backup_id})

    def _save_backup(self, backup_id: str, records: list[dict[str, Any]]) -> None:
        self._backups[backup_id] = records
        if self.backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            (self.backup_dir / f"{backup_id}.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    def _load_backup(self, backup_id: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r"backup-[0-9a-f]{12}", backup_id):
            raise KeyError(f"H-MEM: unknown backup {backup_id}")
        if backup_id in self._backups:
            return self._backups[backup_id]
        path = self.backup_dir / f"{backup_id}.json" if self.backup_dir else None
        if path is None or not path.is_file():
            raise KeyError(f"H-MEM: unknown backup {backup_id}")
        return json.loads(path.read_text(encoding="utf-8"))


# --- dreaming (spec section 7): proposals never take effect before approval ---


@dataclass
class DreamProposal:
    id: str
    type: str  # insight | domain | invariant
    content: str
    derivedFrom: list[str]
    suggestedDomain: str | None = None
    status: str = "proposed"  # proposed | approved | rejected


class DreamingService:
    """Clusters related memories into proposals; only approve() turns one into memory.

    Proposals live in <persist_dir>/dreams.json when the store persists.
    """

    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Clock, actor: str,
                 path: Path | None = None) -> None:
        self.store, self.ledger, self.clock, self.actor, self.path = store, ledger, clock, actor, path
        self.proposals: dict[str, DreamProposal] = {}
        if path and path.is_file():
            for p in json.loads(path.read_text(encoding="utf-8")):
                self.proposals[p["id"]] = DreamProposal(**p)

    def _persist(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps([dataclasses.asdict(p) for p in self.proposals.values()],
                                            ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def _relatedness(a: MemoryRecord, b: MemoryRecord) -> float:
        return (0.5 * max(0.0, cosine(a.embedding, b.embedding)) + 0.2 * jaccard(a.tags, b.tags)
                + 0.1 * (1.0 if a.domain == b.domain else 0.0) + 0.2 * jaccard(a.entities, b.entities))

    def _propose(self, type: str, content: str, derived_from: list[str], suggested: str | None = None) -> DreamProposal:
        proposal = DreamProposal(f"dream-{uuid.uuid4().hex[:12]}", type, content, derived_from, suggested)
        self.proposals[proposal.id] = proposal
        self.ledger.log(proposal.id, "dream_proposed", self.actor, details={"type": type, "derivedFrom": derived_from})
        return proposal

    def dream(self) -> list[DreamProposal]:
        cap, records, created = DEFAULTS["max_dream_proposals_per_type"], self.store.all(), []
        used: set[str] = set()
        for seed in records:  # insights from clusters
            if len([p for p in created if p.type == "insight"]) >= cap:
                break
            if seed.id in used:
                continue
            group = [seed] + [o for o in records if o.id != seed.id and o.id not in used
                              and self._relatedness(seed, o) >= DEFAULTS["dream_relatedness"]]
            if len(group) >= DEFAULTS["dream_cluster_min_size"]:
                used.update(g.id for g in group)
                domains = "/".join(dict.fromkeys(m.domain for m in group))
                created.append(self._propose("insight", f"Across {len(group)} related memories ({domains}): "
                                             + " + ".join(m.content for m in group), [m.id for m in group]))
        for m in records:  # domain suggestions for uncategorized memories
            if len([p for p in created if p.type == "domain"]) >= cap:
                break
            suggested = self.store.classify_domain(m.content, m.tags, m.type) if m.domain == "general" else "general"
            if suggested != "general":
                created.append(self._propose("domain", f'Reclassify "{m.content[:60]}" as {suggested}', [m.id], suggested))
        by_domain: dict[str, list[MemoryRecord]] = {}
        for m in records:  # invariants from preference, personal and correction signals
            if m.type in ("preference", "personal") or m.provenance.get("origin") == "user_correction":
                by_domain.setdefault(m.domain, []).append(m)
        for domain, items in by_domain.items():
            if len([p for p in created if p.type == "invariant"]) >= cap:
                break
            if len(items) >= 2:
                created.append(self._propose("invariant", f"Stable pattern in {domain}: "
                                             + "; ".join(m.content for m in items), [m.id for m in items]))
        self._persist()
        return created

    def pending(self) -> list[DreamProposal]:
        return [p for p in self.proposals.values() if p.status == "proposed"]

    def _pending(self, proposal_id: str) -> DreamProposal:
        p = self.proposals.get(proposal_id)
        if p is None or p.status != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        return p

    def approve(self, proposal_id: str) -> MemoryRecord | None:
        """insight -> long-term factual, invariant -> long-term preference, both with derivedFrom;
        domain -> updates the source records' domain and returns None."""
        p = self._pending(proposal_id)
        p.status = "approved"
        self.ledger.log(proposal_id, "dream_approved", self.actor, details={"type": p.type})
        self._persist()
        if p.type == "domain":
            for memory_id in p.derivedFrom:
                if self.store.get(memory_id) and p.suggestedDomain:
                    self.store.update(memory_id, details={"dream": proposal_id}, domain=p.suggestedDomain)
            return None
        return self.store.add(
            p.content, "dreaming", type="factual" if p.type == "insight" else "preference", layer="long_term",
            tags=[f"dream:{p.type}"], confidence=0.75, derived_from=p.derivedFrom,
            provenance={"origin": "dream", "learnedAt": self.clock(), "label": f"approved {p.type} proposal"},
        )

    def reject(self, proposal_id: str) -> None:
        p = self._pending(proposal_id)
        p.status = "rejected"  # logged, never materialized
        self.ledger.log(proposal_id, "dream_rejected", self.actor, details={"type": p.type})
        self._persist()


# --- facade (HOW_TO_USE_H-MEM.md) ---


class HMEM:
    def __init__(
        self, clock: Clock | None = None, persist_dir: Path | None = None, ledger_path: Path | None = None,
        actor: str = "system", miner_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.clock = clock or now_ms
        self.ledger = TrustLedgerService(self.clock, ledger_path)
        self.store = MemoryStoreService(self.clock, self.ledger, actor, persist_dir)
        self.retrieval = MemoryRetrievalService(self.store, self.ledger, self.clock, actor)
        self.mining = MemoryMiningService(miner_fn)
        self.conflicts = ConflictDetectionService(self.store, self.ledger, self.clock, actor)
        self.sleep = SleepCycleService(self.store, self.ledger, self.clock, actor,
                                       persist_dir / "backups" if persist_dir else None)
        self.dreaming = DreamingService(self.store, self.ledger, self.clock, actor,
                                        persist_dir / "dreams.json" if persist_dir else None)

    def add(self, content: str, source: str, **kwargs: Any) -> MemoryRecord:
        return self.store.add(content, source, **kwargs)

    def query(self, query: str, **kwargs: Any) -> QueryResult:
        return self.retrieval.query(query, **kwargs)

    def feedback(self, memory_id: str, kind: str) -> None:
        self.retrieval.feedback(memory_id, kind)
