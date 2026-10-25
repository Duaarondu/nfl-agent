// NFL Fantasy Agent web UI: plain JS, no build step.
// The page makes the run_id, POSTs /run to the API, and polls GET /trace/<run_id> every
// 2s to show each agent step as it happens. The finished reply comes from the POST, or
// from the trace once it is done (if a long POST connection drops).
"use strict";

const CONFIG = window.NFL_AGENT_CONFIG || { apiPort: 8000 };
const API = new URLSearchParams(location.search).get("api")
  || `${location.protocol}//${location.hostname}:${CONFIG.apiPort}`;
const POLL_MS = 2000;
const MAX_ROWS_SHOWN = 25;

const $ = (id) => document.getElementById(id);
let current = null; // {runId, started, timer, poller, done}
let modelConfigured = true; // from /health; without a model, failed model calls are not shown

// --- small DOM helpers (text only: nothing from the API is parsed as HTML) ---

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const seconds = (ms) => (typeof ms === "number" ? `${(ms / 1000).toFixed(1)}s` : "");
const supportClass = (s) => (s || "").replace(/\s+/g, "-");

function newRunId() {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function modelName(model) {
  if (!model) return "";
  const m = /nemotron-([\d.]+)-([a-z]+)/i.exec(model);
  return m ? `Nemotron ${m[1]} ${m[2][0].toUpperCase()}${m[2].slice(1)}` : model;
}

// --- header badges ---

async function loadHealth() {
  const badges = $("badges");
  try {
    const res = await fetch(`${API}/health`);
    const h = await res.json();
    modelConfigured = Boolean(h.model_configured);
    badges.replaceChildren(
      el("span", { class: `badge ${h.sample_mode ? "sample" : "live"}`,
                   text: h.sample_mode ? "Sample mode" : "Live Zetaris" }),
      el("span", { class: `badge ${h.model_configured ? "on" : "off"}`,
                   text: h.model_configured ? "Model configured" : "Model not configured (rule-based)" }),
    );
  } catch (error) {
    badges.replaceChildren(el("span", { class: "badge off", text: `API unreachable at ${API}` }));
  }
}

// --- the timeline: one row per trace line worth showing ---

const SPONSOR = {
  zetaris: ["zetaris", "Zetaris query"],
  model: ["nightshift", "Nemotron via Nightshift"],
  hmemStore: ["hmem", "H-MEM store"],
  hmemRetrieve: ["hmem", "H-MEM retrieve"],
  rules: ["rules", "Code rules"],
  agent: ["agent", "Agent"],
};

function describe(l) {
  const agent = l.agent_name || "";
  const factor = agent.startsWith("factor_agent:") ? agent.slice("factor_agent:".length) : null;
  const ms = l.duration_ms;
  const row = (sponsor, title, sub, tone) => ({ sponsor, title, sub, tone });

  if (l.action === "model_call") {
    const who = factor ? `Factor agent: ${factor}` : ({ planner: "Planner: classify", critic: "Critic: review",
      analyst: l.step === "revise" ? "Analyst: revise verdict" : "Analyst: verdict" }[agent] || `${agent}: ${l.step}`);
    if (l.status === "ok") {
      const tokens = l.completion_tokens ? ` · ${l.completion_tokens} tokens` : "";
      return row("model", who, `${modelName(l.model)} · ${seconds(ms)}${tokens}`, null);
    }
    if (!modelConfigured) return null; // no model at all: the rule-based rows say what ran instead
    return row("model", who, `no usable reply (${l.error || l.status}) after ${seconds(ms)}: falls back to code rules`, "warn");
  }
  if (agent === "memory") {
    if (l.action === "resolve_players") return row("zetaris", "Memory: roster lookup", `${l.rows_returned ?? 0} players found`, null);
    if (l.action === "store") {
      const kinds = (l.facts || []).map((f) => `${f.kind}: ${f.value}`).join(", ");
      return row("hmemStore", "League memory stored", kinds || "nothing new to store", null);
    }
    if (l.action === "retrieve") return row("hmemRetrieve", "League memory retrieved", `${l.count ?? 0} memories · ${seconds(ms)}`, null);
  }
  if (agent === "planner") {
    if (l.action === "classify" && l.status === "fallback") return row("rules", "Planner: keyword fallback", `question type ${l.question_type}`, "warn");
    if (l.action === "handoff") {
      const about = l.player_name ? ` about ${l.player_name}` : "";
      return row("agent", "Planner → Analyst", `${l.question_type} question${about} (classified by ${l.classified_by})`, null);
    }
  }
  if (["season_context", "player_lookup", "factor_query", "query"].includes(l.action)) {
    const name = l.factor || { season_context: "Season context", player_lookup: "Player lookup" }[l.action] || "Query";
    if (l.status === "ok") return row("zetaris", name, `${l.rows_returned ?? 0} rows · ${seconds(ms)}`, null);
    return row("zetaris", name, `failed: ${l.error || l.status}`, "bad");
  }
  if (l.action === "rate_factor" && factor) {
    const by = l.rated_by === "model" ? "model" : "rules";
    return row(by, `Factor agent: ${factor}`, `${l.support} (${l.rated_by})`, by === "rules" ? "warn" : null);
  }
  if (agent === "analyst" && l.action === "verdict" && l.status === "fallback") {
    return row("rules", "Verdict: rule-based", l.verdict || "", "warn");
  }
  if (agent === "analyst" && l.action === "answer") {
    const premise = l.premise_corrected ? " · premise corrected from the data" : "";
    return row("agent", "Analyst answer ready", `${l.queries} queries · ${l.factors} factors · verdict by ${l.verdict_by}${premise}`, null);
  }
  if (agent === "critic" && l.action === "review" && l.status === "fallback") {
    return row("rules", `Critic round ${l.round}: code checks only`, "the model review had no usable reply", "warn");
  }
  if (agent === "critic" && l.action === "critique") {
    const tone = l.status === "approved" ? "good" : "warn";
    const sub = `${l.status.replace("_", " ")} · ${l.blocking} blocking of ${(l.issues || []).length} issues · reviewed by ${l.reviewed_by}`;
    return row("agent", `Critic round ${l.round}`, sub, tone);
  }
  if (agent === "analyst" && l.action === "revise") {
    return row(l.verdict_by === "model" ? "model" : "rules", `Analyst revised the verdict (round ${l.round})`, `by ${l.verdict_by || l.status}`, null);
  }
  if (agent === "critic" && l.action === "final") {
    return row("agent", `Final: ${l.status}`, `${l.rounds} critic round(s), ${l.revisions} revision(s) · ${seconds(ms)}`, l.status === "approved" ? "good" : "warn");
  }
  if (l.status === "error") return row("agent", `${agent}: ${l.action}`, l.error || "error", "bad");
  return null;
}

function renderTimeline(lines, running) {
  const list = $("timeline");
  const rows = [];
  for (const line of lines) {
    const d = describe(line);
    if (!d) continue;
    const at = (Date.parse(line.timestamp) - current.startedWall) / 1000;
    const [cls, label] = SPONSOR[d.sponsor];
    rows.push(el("li", { class: d.tone },
      el("span", { class: "t-time", text: `${Math.max(0, at).toFixed(1)}s` }),
      el("span", { class: `tag ${cls}`, text: label }),
      el("span", { class: "t-detail" }, el("strong", { text: d.title }), d.sub ? el("span", { class: "sub" }, ` · ${d.sub}`) : null),
    ));
  }
  if (running) {
    rows.push(el("li", { class: "pending" }, el("span", { class: "t-time" }), el("span"),
      el("span", { class: "t-detail", text: rows.length ? "Working on the next step…" : "Starting: the Planner reads the question…" })));
  }
  list.replaceChildren(...rows);
}

// --- running a question ---

async function ask(question, userId) {
  if (current && !current.done) return;
  const runId = newRunId();
  current = { runId, startedWall: Date.now(), started: performance.now(), done: false };
  $("error").hidden = true;
  $("result").hidden = true;
  $("result").replaceChildren();
  $("progress").hidden = false;
  $("run-id").textContent = runId;
  $("download").href = `${API}/trace/${runId}.jsonl`;
  setStatus("running", "Running");
  $("ask-button").disabled = true;
  renderTimeline([], true);

  const run = current;
  run.timer = setInterval(() => { $("elapsed").textContent = `${((performance.now() - run.started) / 1000).toFixed(1)}s`; }, 100);
  run.poller = setInterval(() => poll(run), POLL_MS);
  setTimeout(() => poll(run), 400);

  const body = { question, run_id: runId, ...(userId ? { user_id: userId } : {}) };
  try {
    const res = await fetch(`${API}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const reply = await res.json();
    await finish(run, res.status, reply);
  } catch (error) {
    // The connection dropped (or the browser gave up on a long request): the trace still
    // has the result once the run is done, so keep polling.
    console.warn("POST /run failed; waiting for the trace", error);
  }
}

async function poll(run) {
  if (run.done) return;
  try {
    const res = await fetch(`${API}/trace/${run.runId}`);
    if (!res.ok) return; // 404 until the server has registered the run
    const t = await res.json();
    if (run.done) return;
    renderTimeline(t.lines, !t.done);
    if (t.done) await finish(run, t.status, t.result, t.lines);
  } catch (error) {
    console.warn("trace poll failed", error);
  }
}

async function finish(run, status, reply, lines) {
  if (run.done) return;
  run.done = true;
  clearInterval(run.timer);
  clearInterval(run.poller);
  $("ask-button").disabled = false;
  if (!lines) {
    try {
      const res = await fetch(`${API}/trace/${run.runId}`);
      if (res.ok) lines = (await res.json()).lines;
    } catch (error) { /* the reply has the result; the timeline keeps its last poll */ }
  }
  if (lines) renderTimeline(lines, false);
  if (status !== 200) {
    setStatus("error", "Failed");
    showError(reply && reply.message ? reply.message : `The API returned HTTP ${status}.`);
    return;
  }
  setStatus(reply.approved ? "approved" : "unresolved", reply.approved ? "Approved" : "Unresolved");
  renderResult(reply);
}

function setStatus(cls, text) {
  const pill = $("run-status");
  pill.className = `pill ${cls}`;
  pill.textContent = text;
}

function showError(message) {
  const box = $("error");
  box.replaceChildren(el("strong", { text: "Could not answer. " }), message);
  box.hidden = false;
}

// --- the result ---

function stripDisclaimer(answer, disclaimer) {
  const text = (answer || "").trim();
  return disclaimer && text.endsWith(disclaimer) ? text.slice(0, -disclaimer.length).trim() : text;
}

function renderResult(r) {
  const out = $("result");
  const nodes = [];
  if (r.premise_correction) nodes.push(el("div", { class: "banner" }, "Premise corrected: ", r.premise_correction));

  const finalText = stripDisclaimer(r.answer, r.disclaimer);
  const steps = r.steps || {};
  const factorsByModel = Object.values(steps.factors || {}).filter((v) => v === "model").length;
  const factorCount = Object.keys(steps.factors || {}).length;
  nodes.push(el("section", { class: "card final" },
    el("div", { class: "final-head" },
      el("h2", { text: "Answer" }),
      el("span", { class: `pill ${r.approved ? "approved" : "unresolved"}`, text: r.approved ? "Critic approved" : "Critic: issues remain" }),
      el("span", { class: `tag ${steps.final_verdict === "model" ? "nightshift" : "rules"}`,
                   text: steps.final_verdict === "model" ? "verdict by Nemotron" : "verdict by code rules" }),
    ),
    el("p", { class: "answer", text: finalText }),
    el("p", { class: "disclaimer", text: r.disclaimer }),
    el("p", { class: "disclaimer" },
      `Planner: ${steps.planner || "?"} · factors by model: ${factorsByModel}/${factorCount} · `
      + `critic reviews: ${(steps.critic_reviews || []).join(", ") || "none"} · total ${seconds((r.timings || {}).total_ms)}`),
    memoryLine(r.memory),
  ));

  const compare = critiqueComparison(r, finalText);
  if (compare) nodes.push(compare);
  nodes.push(factorCards(r.factors || []));
  nodes.push(claimsDetails(r));
  nodes.push(criticDetails(r.critic || { rounds: [] }));
  if (r.memory) nodes.push(memoryDetails(r.memory));
  nodes.push(timingDetails(r.timings || {}));

  out.replaceChildren(...nodes);
  out.hidden = false;
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

function memoryLine(m) {
  if (!m || !m.remembered) return null;
  const roster = (m.roster || []).map((p) => `${p.name} (${p.team}, ${p.position})`).join(", ") || "none";
  const teams = m.teams ? `${m.teams}-team, ` : "";
  return el("div", { class: "memory-line" },
    el("span", { class: "tag hmem", text: "H-MEM" }), " ",
    `League memory for ${m.user_id}: ${teams}${m.scoring_label} scoring; roster: ${roster}.`);
}

function critiqueComparison(r, finalText) {
  const rounds = (r.critic || {}).rounds || [];
  const before = (r.answer_before_critic || "").trim();
  if (!before || before === finalText || !rounds.some((c) => c.status === "needs_revision")) return null;
  const blocking = rounds.filter((c) => c.status === "needs_revision")
    .flatMap((c) => c.issues.filter((i) => i.blocking).map((i) => ({ ...i, round: c.round })));
  return el("section", { class: "card" },
    el("h2", { text: "What the Critic changed" }),
    el("div", { class: "compare" },
      el("div", { class: "side before" }, el("h3", { text: "Answer before the critic" }), el("p", { text: before })),
      el("div", { class: "issues" },
        el("strong", { text: "Sent back because" }),
        el("ul", {}, blocking.map((i) => el("li", {}, `Round ${i.round}, ${i.check.replace("_", " ")}: ${i.reason}`))),
        el("div", { class: "arrow", text: "→" }),
      ),
      el("div", { class: "side after" }, el("h3", { text: r.approved ? "Final answer (approved)" : "Final answer" }), el("p", { text: finalText })),
    ),
  );
}

function factorCards(factors) {
  return el("section", { class: "card" },
    el("h2", { text: "Factors (most to least supported)" }),
    el("div", { class: "factors" }, factors.map((f) => el("div", { class: "factor" },
      el("div", { class: "factor-head" },
        el("h3", { text: f.factor }),
        el("span", {},
          el("span", { class: `support ${supportClass(f.support)}`, text: f.support }), " ",
          el("span", { class: `tag ${f.rated_by === "model" ? "nightshift" : "rules"}`, text: f.rated_by === "model" ? "model" : "rule-based" })),
      ),
      el("p", { text: f.summary }),
      f.rule ? el("p", { class: "rule", text: `Rule: ${f.rule}` }) : null,
    ))),
  );
}

function evidenceBlock(e) {
  const rows = e.rows || [];
  return el("details", {},
    el("summary", { text: `Query ${e.query_id} · ${rows.length} rows` }),
    el("pre", { class: "sql", text: e.sql }),
    el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, (e.headers || []).map((h) => el("th", { text: h })))),
      el("tbody", {}, rows.slice(0, MAX_ROWS_SHOWN).map((row) => el("tr", {}, row.map((v) => el("td", { text: v === null ? "" : v }))))),
    )),
    rows.length > MAX_ROWS_SHOWN ? el("p", { class: "disclaimer", text: `Showing ${MAX_ROWS_SHOWN} of ${rows.length} rows.` }) : null,
  );
}

function claimsDetails(r) {
  return el("details", { class: "card" },
    el("summary", { text: `Claims with their SQL and rows (${(r.claims || []).length})` }),
    (r.claims || []).map((c) => el("div", { class: "round" }, el("p", { text: c.text }), (c.evidence || []).map(evidenceBlock))),
    (r.not_measurable || []).length
      ? el("div", { class: "round" }, el("h3", { text: "Not measurable with this data" }),
           el("ul", {}, r.not_measurable.map((t) => el("li", { text: t }))))
      : null,
  );
}

function criticDetails(critic) {
  return el("details", { class: "card" },
    el("summary", { text: `Critic rounds (${critic.rounds.length})` }),
    critic.rounds.map((c) => el("div", { class: "round" },
      el("h3", {}, `Round ${c.round} `, el("span", { class: `pill ${c.status}`, text: c.status.replace("_", " ") }),
         ` reviewed by ${c.reviewed_by}`),
      c.issues.length ? c.issues.map((i) => el("div", { class: `issue ${i.blocking ? "blocking" : "recorded"}` },
        el("span", { class: "kind", text: i.blocking ? "Blocking" : "Recorded" }),
        ` · ${i.check.replace("_", " ")} in ${i.where}: ${i.reason}`,
        i.claim ? el("div", { class: "claim", text: `“${i.claim}”` }) : null,
      )) : el("p", { class: "disclaimer", text: "No issues." }),
    )),
  );
}

function memoryDetails(m) {
  return el("details", { class: "card" },
    el("summary", { text: "League memory (H-MEM)" }),
    el("dl", { class: "kv" },
      el("dt", { text: "User" }), el("dd", { text: m.user_id }),
      el("dt", { text: "Scoring" }), el("dd", { text: m.scoring_label || m.scoring }),
      el("dt", { text: "League size" }), el("dd", { text: m.teams ? `${m.teams} teams` : "not stated" }),
      el("dt", { text: "Roster" }), el("dd", { text: (m.roster || []).map((p) => `${p.name} (${p.team}, ${p.position})`).join(", ") || "none" }),
      el("dt", { text: "Stored this run" }), el("dd", { text: (m.stored_this_run || []).length ? m.stored_this_run.join(", ") : "nothing new" }),
      el("dt", { text: "Memories used" }), el("dd", { text: (m.memory_ids || []).join(", ") || "none" }),
    ),
  );
}

function timingDetails(t) {
  const busy = Object.entries(t.agent_busy_ms || {});
  return el("details", { class: "card" },
    el("summary", { text: `Timings (total ${seconds(t.total_ms)})` }),
    el("dl", { class: "kv" },
      el("dt", { text: "Total" }), el("dd", { text: seconds(t.total_ms) }),
      el("dt", { text: "Memory" }), el("dd", { text: seconds(t.memory_ms || 0) }),
      ...busy.flatMap(([agent, ms]) => [el("dt", { text: agent }), el("dd", { text: `${seconds(ms)} busy` })]),
    ),
    el("p", { class: "disclaimer", text: "Factor agents run in parallel, so busy times add up to more than the total." }),
    el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ["Agent", "Step", "Status", "Time", "Model"].map((h) => el("th", { text: h })))),
      el("tbody", {}, (t.model_calls || []).map((c) => el("tr", {},
        el("td", { text: c.agent }), el("td", { text: c.step || "" }), el("td", { text: c.status }),
        el("td", { text: seconds(c.duration_ms) }), el("td", { text: c.model ? `${modelName(c.model)} via Nightshift` : "-" }),
      ))),
    )),
  );
}

// --- wiring ---

document.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
  $("question").value = chip.dataset.question;
  $("user-id").value = chip.dataset.user || "";
  $("question").focus();
}));

$("ask-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  const userId = $("user-id").value.trim();
  if (question) ask(question, userId);
});

loadHealth();
