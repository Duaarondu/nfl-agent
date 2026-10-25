"""League memory (app/agents/memory.py), its pipeline wiring and critic check (f)."""

import json

import pytest
from helpers import classify, load_example, read_trace

from app import pipeline
from app.adapters import meterless
from app.agents import analyst, critic, memory
from app.agents.memory import Fact, RosterPlayer, UserContext, mine_facts

SESSION_1 = "12-team half-PPR, my TE is George Kittle and my WR is Davante Adams"
BUCS = "Who becomes the Bucs' WR1 if Mike Evans is out?"
KITTLE = RosterPlayer("00-0033288", "George Kittle", "SF", "TE")
ADAMS = RosterPlayer("00-0031381", "Davante Adams", "LA", "WR")
COMPARE = ("I have Jameson Williams on my bench and George Pickens in my starting lineup, "
           "who should I pick?")


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    path = tmp_path / "memory"
    monkeypatch.setenv("MEMORY_DIR", str(path))
    return path


def facts(text):
    return [(f.kind, f.value) for f in mine_facts(text)]


# --- mining by code ---


@pytest.mark.parametrize("text, expected", [
    (SESSION_1, [("teams", "12"), ("scoring", "half"), ("roster", "George Kittle"), ("roster", "Davante Adams")]),
    ("10 team league, 0.5 PPR", [("teams", "10"), ("scoring", "half")]),
    ("We play standard scoring. I have Kittle, Adams and Mike Evans.",
     [("scoring", "standard"), ("roster", "Kittle"), ("roster", "Adams"), ("roster", "Mike Evans")]),
    ("non-PPR league", [("scoring", "standard")]),
    ("14-team full PPR", [("teams", "14"), ("scoring", "ppr")]),
    ("my RBs are Bijan Robinson & Breece Hall; who do I start?", [("roster", "Bijan Robinson"), ("roster", "Breece Hall")]),
    ("I dropped Davante Adams yesterday.", [("drop", "Davante Adams")]),
    (COMPARE, [("roster", "Jameson Williams"), ("roster", "George Pickens")]),
    ("Pickens is in my lineup and Jameson Williams is on my bench. Who do I start?",
     [("roster", "Pickens"), ("roster", "Jameson Williams")]),
    ("Start Pickens in my lineup?", [("roster", "Pickens")]),
    # Not facts about the user's league or roster:
    ("How many PPR points did Mike Evans score?", []),
    ("I have a question about Mike Evans.", []),
    ("Should I start a standard WR3?", []),
])
def test_mine_facts(text, expected):
    assert facts(text) == expected


def test_resolve_players_by_full_name_or_unique_surname(real_sample):
    found, unresolved, sql = memory.resolve_players(["George Kittle", "Adams", "Nobody Atall"])
    assert found == {"George Kittle": KITTLE, "Adams": ADAMS}
    assert unresolved == ["Nobody Atall"]
    assert sql.startswith("SELECT r.gsis_id, r.full_name") and ";" not in sql


# --- store and retrieve ---


def test_store_then_retrieve(real_sample, memory_dir, trace_dir):
    written = memory.store("u1", SESSION_1, "run1", session_id="s1", miner_fn=None)
    assert [r.content for r in written] == [
        "The user's league has 12 teams.",
        "The user's league uses half-PPR scoring.",
        "George Kittle (SF, TE) is on the user's roster.",
        "Davante Adams (LA, WR) is on the user's roster.",
    ]
    r = written[2]
    assert (r.type, r.layer, r.source, r.confidence, r.chatId, r.goalRunId) == (
        "preference", "working", "interaction:chat_message", 0.9, "s1", "run1")
    assert r.provenance["origin"] == "chat_message" and "george kittle" in r.entities

    ctx = memory.retrieve("u1", BUCS, "run2")
    assert (ctx.scoring, ctx.teams, ctx.roster, ctx.remembered) == ("half", 12, [KITTLE, ADAMS], True)
    assert ctx.context.startswith("[MEMORY CONTEXT]\n## fantasy")
    assert "League: 12-team league, half-PPR scoring." in ctx.prompt_block()

    ledger = [json.loads(l) for l in (trace_dir / "hmem" / "u1.ledger.jsonl").read_text().splitlines()]
    assert [e["action"] for e in ledger] == ["create"] * 4 + ["read"] * 4
    assert {e["actor"] for e in ledger} == {"user:u1"}
    lines = [l for l in read_trace(trace_dir) if l["agent_name"] == "memory"]
    assert [(l["action"], l["status"]) for l in lines] == [("resolve_players", "ok"), ("store", "ok"), ("retrieve", "ok")]
    assert lines[1]["by"] == "code" and len(lines[1]["record_ids"]) == 4
    assert lines[2]["roster"] == ["George Kittle", "Davante Adams"] and lines[2]["target_agent"] == "analyst"


def test_repeating_a_fact_writes_nothing(real_sample, memory_dir):
    memory.store("u1", SESSION_1, "run1", miner_fn=None)
    assert memory.store("u1", SESSION_1, "run2", miner_fn=None) == []


def test_a_changed_fact_supersedes_the_old_one(real_sample, memory_dir):
    first = memory.store("u1", SESSION_1, "run1", miner_fn=None)
    [new] = memory.store("u1", "Actually we switched to full PPR.", "run2", miner_fn=None)
    mem = memory.open_memory("u1")
    old = mem.store.get(first[1].id)
    assert (old.supersededBy, new.supersedes) == (new.id, old.id)  # kept, not deleted
    assert memory.retrieve("u1", BUCS, "run3").scoring == "ppr"


def test_a_dropped_player_leaves_the_roster(real_sample, memory_dir):
    memory.store("u1", SESSION_1, "run1", miner_fn=None)
    [drop] = memory.store("u1", "I dropped Davante Adams.", "run2", miner_fn=None)
    assert "no longer on the user's roster" in drop.content
    assert memory.retrieve("u1", BUCS, "run3").roster == [KITTLE]
    assert memory.store("u1", "I dropped Davante Adams.", "run4", miner_fn=None) == []


def test_unresolved_names_are_not_stored(real_sample, memory_dir, trace_dir):
    assert memory.store("u1", "my WR is Nobody Atall", "run1", miner_fn=None) == []
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "store"]
    assert (line["status"], line["unresolved"]) == ("none", ["Nobody Atall"])


def test_model_mines_only_when_code_finds_nothing(real_sample, memory_dir, trace_dir):
    prompts = []

    def miner(prompt):
        prompts.append(prompt)
        return '```json\n["half-PPR scoring", "My WR is Davante Adams"]\n```'

    written = memory.store("u1", "our league gives 0.5 per reception, and Adams is on my squad", "run1", miner_fn=miner)
    assert len(prompts) == 1 and memory.MINER_INSTRUCTIONS in prompts[0]
    assert [r.confidence for r in written] == [0.7, 0.7]
    assert memory.retrieve("u1", BUCS, "run2").roster == [ADAMS]
    assert [l["by"] for l in read_trace(trace_dir) if l["action"] == "store"] == ["model"]

    memory.store("u1", SESSION_1, "run3", miner_fn=miner)  # code parses it all: no model call
    assert len(prompts) == 1


def test_model_failure_keeps_code_facts_only(real_sample, memory_dir, trace_dir):
    def miner(prompt):
        raise meterless.MeterlessError("down")

    assert memory.store("u1", "what does my league look like?", "run1", miner_fn=miner) == []
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "model_call"]
    assert (line["agent_name"], line["status"]) == ("memory", "fallback")


def test_default_miner_goes_through_meterless(real_sample, memory_dir, model):
    model.replies = ['["12-team league"]']
    memory.store("u1", "how big is my league again? it's twelve teams", "run1")
    assert model.calls[0][0]["content"].startswith("Extract durable memories from this chat_message")


def test_retrieve_with_nothing_remembered(memory_dir, trace_dir):
    ctx = memory.retrieve("nobody", BUCS, "run1")
    assert (ctx.remembered, ctx.scoring, ctx.prompt_block()) == (False, "ppr", "")
    assert [l["status"] for l in read_trace(trace_dir) if l["action"] == "retrieve"] == ["empty"]


@pytest.mark.parametrize("user_id", ["", "../etc", "a b", "x" * 65])
def test_bad_user_ids_are_refused(memory_dir, user_id):
    with pytest.raises(ValueError):
        memory.open_memory(user_id)


# --- the answer uses the memory ---


def all_fail(model):
    def respond(messages):
        raise meterless.MeterlessError("down")
    model.respond = respond


def test_answer_uses_half_ppr_and_skips_the_rostered_player(real_sample, memory_dir, model, trace_dir):
    all_fail(model)  # every model call falls back to code: rule-based verdict
    memory.store("u1", SESSION_1, "run0", miner_fn=None)
    run = pipeline.answer(BUCS, user_id="u1", model_review=False)

    usage = next(q for q in run.result.queries if q.factor == "Team usage")
    assert "AVG((fantasy_points + fantasy_points_ppr) / 2), 1) AS half_ppr_per_game" in usage.sql
    assert run.result.answer.startswith("Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey if available.")
    assert "among his teammates not already on your roster (22.8%)" in run.result.answer
    assert run.approved
    assert [l["action"] for l in read_trace(trace_dir) if l["agent_name"] == "memory"][-2:] == ["store", "retrieve"]


def test_session_one_question_is_about_the_player_who_is_out(real_sample, memory_dir, model):
    all_fail(model)  # no model name for the player: the lookup must not pick rostered Kittle
    run = pipeline.answer(f"{SESSION_1}. {BUCS}", user_id="u1", model_review=False)
    assert run.result.player.name == "Mike Evans"
    assert run.result.answer.startswith("Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey if available.")


def test_verdict_prompt_carries_the_memory(real_sample, memory_dir, model):
    memory.store("u1", SESSION_1, "run0", miner_fn=None)
    replies = {"verdict": json.dumps({"verdict": "Pick up Christian McCaffrey",
                                      "why": "His 22.8% recent target share is the top among players you do not have."})}

    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classify("Mike Evans", "replacement")
        if system == analyst.FACTOR_PROMPT:
            return json.dumps({"support": "moderate", "summary": "Facts."})
        if system == analyst.VERDICT_PROMPT:
            return replies["verdict"]
        raise AssertionError(system[:60])

    model.respond = respond
    run = pipeline.answer(BUCS, user_id="u1", model_review=False)
    [prompt] = [c[-1]["content"] for c in model.calls if c[0]["content"] == analyst.VERDICT_PROMPT]
    assert "[MEMORY CONTEXT]" in prompt and "Their roster: George Kittle (SF, TE); Davante Adams (LA, WR)." in prompt
    assert "Quote fantasy points as half-PPR points." in prompt
    assert run.approved and run.result.user_context.scoring == "half"


def test_no_user_id_means_no_memory(real_sample, memory_dir, model, trace_dir):
    all_fail(model)
    run = pipeline.answer(BUCS, model_review=False)
    assert run.result.user_context is None
    assert "fantasy_points_ppr), 1) AS ppr_per_game" in next(q.sql for q in run.result.queries if q.factor == "Team usage")
    assert not [l for l in read_trace(trace_dir) if l["agent_name"] == "memory"]
    assert not memory_dir.exists()


# --- critic check (f) ---


def bucs_with(answer, ctx):
    result = load_example("who-becomes-the-bucs", run="d52e2e813360")
    result.answer, result.user_context = answer, ctx
    return result


HALF_CTX = UserContext("u1", scoring="half", teams=12, roster=[KITTLE, ADAMS], remembered=True)


def test_check_f_blocks_picking_up_a_rostered_player():
    [issue] = critic.check_user_context(bucs_with("Pick up George Kittle. He leads with 24.9%.", HALF_CTX))
    assert (issue.check, issue.blocking) == ("user_context", True)
    assert "already on the user's roster" in issue.reason


@pytest.mark.parametrize("answer, flagged", [
    ("Pick up Christian McCaffrey. He averages 18.3 PPR points per game.", True),
    ("Pick up Christian McCaffrey. He averages 15.6 half-PPR points per game.", False),
    ("Pick up Christian McCaffrey. In half PPR he leads.", False),
])
def test_check_f_wants_the_league_scoring(answer, flagged):
    issues = critic.check_user_context(bucs_with(answer, HALF_CTX))
    assert bool(issues) == flagged


def test_check_f_standard_league_flags_any_ppr():
    ctx = UserContext("u1", scoring="standard", remembered=True)
    assert critic.check_user_context(bucs_with("Pick up Christian McCaffrey. 15.6 half-PPR points.", ctx))
    assert not critic.check_user_context(bucs_with("Pick up Christian McCaffrey. 12.1 standard points.", ctx))


def test_check_a_ignores_rostered_teammates():
    # McCaffrey trails Kittle 24.9% -- but Kittle is already on the roster, so he is not an option.
    result = bucs_with("Pick up Christian McCaffrey. His recent target share is 22.8%.", HALF_CTX)
    assert not critic.check_verdict_support(result)
    result.user_context = None
    assert critic.check_verdict_support(result)


def test_critic_sends_a_rostered_pickup_back(real_sample, memory_dir, model):
    memory.store("u1", SESSION_1, "run0", miner_fn=None)
    verdicts = [json.dumps({"verdict": "Pick up George Kittle", "why": "His 24.9% recent target share leads."}),
                json.dumps({"verdict": "Pick up Christian McCaffrey", "why": "His 22.8% recent target share is next."})]

    def respond(messages):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classify("Mike Evans", "replacement")
        if system == analyst.FACTOR_PROMPT:
            return json.dumps({"support": "moderate", "summary": "Facts."})
        if system == analyst.VERDICT_PROMPT:
            return verdicts[1] if "A critic checked it" in user else verdicts[0]
        raise AssertionError(system[:60])

    model.respond = respond
    run = pipeline.answer(BUCS, user_id="u1", model_review=False)
    assert [c.status for c in run.critiques] == ["needs_revision", "approved"]
    assert {i.check for i in run.critiques[0].blocking} == {"user_context"}
    assert run.result.answer.startswith("Deebo Samuel is next at WR on the depth chart, but the target share points to Christian McCaffrey (22.8%), so for fantasy: pick up Christian McCaffrey.")


def test_saved_runs_without_memory_still_load():
    assert load_example("who-becomes-the-bucs", run="d52e2e813360").user_context is None


def test_user_context_round_trips_through_json():
    import dataclasses
    data = json.loads(json.dumps(dataclasses.asdict(HALF_CTX)))
    assert memory.user_context_from_dict(data) == HALF_CTX


def test_bench_and_lineup_players_are_stored_as_rostered(real_sample, memory_dir):
    written = memory.store("u1", COMPARE, "run1", miner_fn=None)
    assert [r.content for r in written] == [
        "Jameson Williams (DET, WR) is on the user's roster.",
        "George Pickens (DAL, WR) is on the user's roster.",
    ]
    ctx = memory.retrieve("u1", COMPARE, "run2")
    assert ctx.roster_names == ("Jameson Williams", "George Pickens")


def test_compare_with_a_user_id_remembers_both_and_still_answers(real_sample, memory_dir, model):
    all_fail(model)
    run = pipeline.answer(COMPARE, user_id="u1", model_review=False)
    assert run.result.user_context.roster_names == ("Jameson Williams", "George Pickens")
    assert run.result.answer.startswith("Start George Pickens over Jameson Williams")
    assert run.approved
