// Conformance shim: exposes app/engines/hmem.py (Python) as the HMEM class the
// official Meterless runner loads (engines/hmem/conformance/runner.ts). Each call
// runs bridge.py once, synchronously, against a temp folder that holds this
// instance's state.json and ledger.jsonl. See docs/hmem-conformance.md.
//
//   HMEM_IMPL=<abs path to this file> npx tsx runner.ts
//
// HMEM_PYTHON overrides the interpreter (default: the repo's .venv).

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");
const python =
  process.env.HMEM_PYTHON ??
  path.join(repo, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const bridge = path.join(here, "bridge.py");

export class HMEM {
  private dir = fs.mkdtempSync(path.join(os.tmpdir(), "hmem-conformance-"));
  private clock: () => number;
  // Record objects handed to the runner, by id (for the ro-001 supersededBy shortcut).
  private handed = new Map<string, any>();

  readonly store = { get: (id: string) => this.call("get", { id }), all: () => this.call("all") };
  readonly ledger = { history: (id: string) => this.call("history", { id }) };
  readonly sleep = {
    preview: () => this.call("sleep_preview"),
    execute: (preview?: unknown) => this.call("sleep_execute", { preview }),
    restore: (backupId: string) => this.call("sleep_restore", { backupId }),
  };
  readonly conflicts = {
    scan: () => this.call("conflicts_scan"),
    autoResolve: (conflict: unknown) => this.call("conflicts_auto_resolve", { conflict }),
  };
  readonly dreaming = {
    dream: () => this.call("dream"),
    approve: (id: string) => this.call("dream_approve", { id }),
    reject: (id: string) => this.call("dream_reject", { id }),
  };

  constructor(opts: { clock?: () => number } = {}) {
    this.clock = opts.clock ?? Date.now;
  }

  add(input: Record<string, unknown>) {
    const rec = this.call("add", input);
    this.handed.set(rec.id, rec);
    return rec;
  }

  feedback(id: string, kind: string) {
    this.call("feedback", { id, kind });
  }

  query(query: string, opts: { topN?: number; threshold?: number } = {}) {
    // ro-001: the runner assigns supersededBy on returned objects; pass that on.
    const overrides: Record<string, unknown> = {};
    for (const [id, rec] of this.handed) {
      if (rec.supersededBy) overrides[id] = { supersededBy: rec.supersededBy };
    }
    return this.call("query", { query, ...opts }, overrides);
  }

  private call(op: string, args: Record<string, unknown> = {}, overrides: Record<string, unknown> = {}) {
    const input = JSON.stringify({ dir: this.dir, clock: this.clock(), op, args, overrides });
    const out = JSON.parse(execFileSync(python, [bridge], { input, encoding: "utf-8" }));
    if ("error" in out) throw new Error(out.error);
    return out.ok;
  }
}
