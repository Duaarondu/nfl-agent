# H-MEM conformance

Our H-MEM engine (`app/engines/hmem.py`) implements the Meterless H-MEM spec:
[github.com/Meterless/Meterless](https://github.com/Meterless/Meterless), folder
`engines/hmem` (Apache-2.0), read at commit `1742dec56a66e58eef9dda2d2b865823758ca8cd`.
The spec is a reference architecture, not a package. It defines "done" as a green run
of its conformance suite, `engines/hmem/conformance/runner.ts`.

It has all seven services in spec section 11: `MemoryStoreService`,
`MemoryRetrievalService`, `TrustLedgerService`, the model-extraction step of
`MemoryMiningService`, `ConflictDetectionService`, `SleepCycleService` and
`DreamingService`.

## Result: 13 of 13 checks pass

Run on 2026-10-25, Windows 11 Enterprise, Node v24.12.0, tsx v4.23.15, Python 3.10.11.
Our code at commit `b2d8c7a` (which includes Justin Chen's `9ceb01f`: conflict detection,
sleep cycle and dreaming), with the shim in `scripts/hmem_conformance/`. A fresh clone of
the spec at `1742dec`, with no local changes; the runner was not modified, and its
`vectors/vectors.json` is byte-identical to `tests/data/hmem_conformance_vectors.json`.
The runner exited with code 0. The output, verbatim:

```
H-MEM conformance: implementation = C:/Users/duaar/nfl-agent/scripts/hmem_conformance/index.ts

  record-validation
    PASS rv-001 a record with no source is rejected by construction
    PASS rv-002 a record with a source is accepted

  feedback-deltas
    PASS fd-001 helpful adds exactly +0.05 confidence and +1 accessCount
    PASS fd-002 not_helpful subtracts exactly 0.03
    PASS fd-003 wrong subtracts exactly 0.20 and adds the review tag
    PASS fd-004 confidence clamps at 0 (wrong at 0.1)
    PASS fd-005 confidence clamps at 1 (helpful at 0.98)

  ranking-order
    PASS ro-001 superseded penalty dominates: a superseded record ranks below a fresh one with identical content relevance
    PASS ro-002 confidence multiplies the whole score: identical records rank by confidence

  sleep-guardrails
    PASS sg-001 old low-access plain record archives; dream-derived record with identical age does not

  conflict-gate
    PASS cg-001 auto-resolve marks the loser supersededBy and deletes nothing

  ledger-audit
    PASS la-001 create then feedback reconstructs: actions in order, previous and new confidence present

  dream-boundary
    PASS db-001 dream proposals never materialize before approval; approval creates a long_term record with lineage

  13/13 checks passed
```

Our own tests also cover the three newer checks:

- `tests/test_hmem_services.py` runs the three checks that failed before (sg-001,
  cg-001, db-001) from the official vectors file, copied unchanged to
  `tests/data/hmem_conformance_vectors.json`. Each runs in process and through
  `bridge.py`, one process per call, as the shim calls it.
- A harness that makes the same calls as `runner.ts`, run through `index.ts` with
  Node's built-in TypeScript support, passed 13 of 13.

The earlier official run, before conflicts, sleep and dreaming were built:

### 2026-10-25, before the last three services: 10 of 13

Run on Windows 11 Enterprise, Node v24.12.0, tsx v4.23.15, Python 3.10.11.
Our code at commit `32449da` plus the shim below. The runner was not modified (the
clone had no local changes). The output, verbatim:

```
H-MEM conformance: implementation = C:/Users/duaar/nfl-agent/scripts/hmem_conformance/index.ts

  record-validation
    PASS rv-001 a record with no source is rejected by construction
    PASS rv-002 a record with a source is accepted

  feedback-deltas
    PASS fd-001 helpful adds exactly +0.05 confidence and +1 accessCount
    PASS fd-002 not_helpful subtracts exactly 0.03
    PASS fd-003 wrong subtracts exactly 0.20 and adds the review tag
    PASS fd-004 confidence clamps at 0 (wrong at 0.1)
    PASS fd-005 confidence clamps at 1 (helpful at 0.98)

  ranking-order
    PASS ro-001 superseded penalty dominates: a superseded record ranks below a fresh one with identical content relevance
    PASS ro-002 confidence multiplies the whole score: identical records rank by confidence

  sleep-guardrails
    FAIL sg-001 old low-access plain record archives; dream-derived record with identical age does not
         sleep.preview: not implemented in the minimum H-MEM version

  conflict-gate
    FAIL cg-001 auto-resolve marks the loser supersededBy and deletes nothing
         conflicts.scan: not implemented in the minimum H-MEM version

  ledger-audit
    PASS la-001 create then feedback reconstructs: actions in order, previous and new confidence present

  dream-boundary
    FAIL db-001 dream proposals never materialize before approval; approval creates a long_term record with lineage
         dreaming.dream: not implemented in the minimum H-MEM version

  10/13 checks passed
```

Each of the three failing checks tested a service that wasn't built yet. All three now are:

| Check | Service it needs | Now |
|---|---|---|
| sg-001 | `SleepCycleService` (preview, execute, backup) | built; backups saved to `backups/` |
| cg-001 | `ConflictDetectionService` (scan, auto-resolve) | built |
| db-001 | `DreamingService` (proposals, approval) | built; proposals saved to `dreams.json` |

The shim used to expose `sleep`, `conflicts` and `dreaming` as objects whose methods
threw. They now call `bridge.py` like the other methods. Because each call is a new
process, sleep backups and dream proposals are saved in the instance's temp folder
between calls.

## How the runner reaches Python code

The runner can only load a TypeScript module that exports an `HMEM` class. Our engine
is Python, so `scripts/hmem_conformance/` has a thin bridge:

- `index.ts` is the `HMEM` class the runner loads. Each method call runs
  `bridge.py` once, synchronously (`execFileSync`), and passes the runner's clock value.
- `bridge.py` runs one operation (`add`, `feedback`, `query`, `get`, `all`,
  `history`) on `app.engines.hmem.HMEM`. Its state lives in a temp folder
  (`state.json` and `ledger.jsonl`), one folder per runner instance.

The bridge does no H-MEM logic. Validation, feedback amounts, ranking and the ledger
all come from `app/engines/hmem.py`.

To rerun (clone the spec outside this repo; don't vendor it):

```bash
git clone https://github.com/Meterless/Meterless
cd Meterless/engines/hmem/conformance
HMEM_IMPL=/abs/path/to/nfl-agent/scripts/hmem_conformance/index.ts npx tsx runner.ts
```

`HMEM_PYTHON` overrides the interpreter. The default is the repo's `.venv`.

## The ro-001 shortcut

ro-001 adds two records, then marks one as replaced by assigning
`byKey[old].supersededBy = id` directly on the JavaScript object that `add()` returned.
After that it queries. In the reference, the JavaScript object is the stored record,
so the assignment changes the store. Through the bridge, the object is a copy, and the
assignment never reaches Python.

So `index.ts` keeps every record object it hands out. Before each `query`, it sends
any `supersededBy` set on those objects, and `bridge.py` applies them before ranking.
Like the runner's direct assignment in the reference, this writes no ledger entry.
Without the shortcut, the Python store would never see the supersession, so ro-001
would not test the penalty at all.

Our own code doesn't depend on this. It sets `supersededBy` through
`MemoryStoreService.supersede()`, which ledgers an `update`. That path is unit-tested
(`tests/test_hmem.py::test_superseded_record_ranks_below_its_replacement`,
`test_supersede_is_an_audited_update`).

## Deliberate departures from the spec

These are choices for our use case, which is league scoring and roster remembered per
user across sessions (`app/agents/memory.py`).

1. **Recall is scoped by user, not chat.** The spec has no user field. Its recall
   scopes are `chatId`, `missionId` and `goalRunId`, and chat-turn recall filters to
   the active `chatId`. We keep one store per `user_id` (`data/memory/<user_id>/state.json`,
   gitignored), with the actor `user:<user_id>` on every ledger entry. Each record has
   `chatId` (the session) and `goalRunId` (the run), so no write is unscoped. But
   retrieval does not filter by `chatId`, because league settings must carry across
   sessions. The ledger goes to `logs/hmem/<user_id>.ledger.jsonl`.
2. **League facts are standing context: threshold 0 and top N 15.** The spec's
   defaults are threshold 0.35 on the final score and top N 5, and it says to tune them
   per domain. A question like "Who becomes the Bucs' WR1 if Mike Evans is out?"
   shares almost no words with "The user's league uses half-PPR scoring.", so at 0.35
   the scoring would be silently dropped. A roster of more than 5 players would also
   be cut. Retrieval still ranks with the spec formula, and every score is in the
   `memory`/`retrieve` trace line.

## Other differences from the reference

- **Code-first mining.** The spec's mining service uses the model whenever one is
  available. We parse league and roster facts with regexes first, and call the injected
  `miner_fn(prompt) -> str` (Meterless, via `app/adapters/meterless.py`) only when the
  question has league or roster cues the regexes could not parse. The model's JSON array
  of statements goes back through the same parser and player lookup, so it can't add a
  fact that code can't check.
- **Who sets `supersededBy`.** In the spec, conflict resolution sets it, and our
  `ConflictDetectionService` does too. League memory doesn't wait for a scan: when a
  newer fact replaces an older one with the same key (scoring, team count, or a
  player's roster state), it supersedes the old record straight away. Either way the
  old record is kept and penalized, never deleted.
- **Sleep and dreaming are not scheduled.** The services work and are tested, but
  league memory doesn't run them on a timer yet; a user's store is small enough not to
  need consolidation during the event.
- **IDs for conflicts, dream proposals and backups** are `<kind>-<random>`, like our
  memory IDs, not counters.
- **Record details.** IDs are `mem-<random>`, not a counter. `entities` are lowercase
  strings, as in the reference, not the `{name, type}` objects in
  `docs/memory-record.md`. `provenance.origin` uses the reference's event names
  (`chat_message`). `provenance.refs` is an object (`chatId`, `goalRunId`), as in the docs.
  Ledger entries have an `id` (`led-<random>`), as in `docs/trust-ledger.md`.
- **Feedback** (`helpful` / `not_helpful` / `wrong`) is implemented and tested, but no
  UI or agent calls it yet.

## Our own feature test

`tests/test_memory_sessions.py` runs two separate Python processes that share only
`MEMORY_DIR`:

1. Session 1 says "12-team half-PPR, my TE is George Kittle and my WR is Davante Adams."
2. Session 2 asks only "Who becomes the Bucs' WR1 if Mike Evans is out?"

Session 2 must answer in half-PPR points and must not recommend Kittle, who is already
on the roster. Meterless points at a closed port, so the test needs no credentials and
proves the code fallback.
