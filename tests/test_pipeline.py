"""The critique -> revise loop: only the verdict is rerun, at most 3 critic rounds."""

import json

import pytest
from helpers import classify, read_trace

from app.adapters import meterless
from app.agents import analyst, critic
from app import pipeline

BUCS = "Who becomes the Bucs' WR1 if Mike Evans is out?"
SAMUEL = json.dumps({"verdict": "Start Deebo Samuel", "why": "The depth chart ranks him second."})
KITTLE = json.dumps({"verdict": "Pick up George Kittle", "why": "His 24.9% recent target share leads the 49ers after Evans."})
# A replacement answer opens with the depth chart's answer, then the fantasy advice.
SAMUEL_LEAD = "Deebo Samuel is next at WR on the depth chart (11.1% recent target share), so for fantasy: start Deebo Samuel."
KITTLE_LEAD = ("Deebo Samuel is next at WR on the depth chart, but the target share points to George Kittle (24.9%), "
               "so for fantasy: pick up George Kittle")
NO_ISSUES = json.dumps({"issues": []})


def script(model, verdicts, revised=None, review=NO_ISSUES, summaries=None):
    """Bucs question: verdicts for the first verdict call, revised for revise calls."""
    summaries = summaries or {}
    revised = list(revised or verdicts)

    def respond(messages):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classify("Mike Evans", "replacement")
        if system == analyst.FACTOR_PROMPT:
            name = user.split("Factor: ")[1].split("\n")[0]
            return json.dumps({"support": "moderate", "summary": summaries.get(name, f"{name} facts.")})
        if system == analyst.VERDICT_PROMPT:
            pool = revised if "Rules from a check against the data" in user else verdicts
            return pool.pop(0) if len(pool) > 1 else pool[0]
        if system == critic.REVIEW_PROMPT:
            return review
        raise AssertionError(system[:60])

    model.respond = respond


def calls(model, prompt):
    return [c for c in model.calls if c[0]["content"] == prompt]


def test_flagged_verdict_is_revised_then_approved(real_sample, model, trace_dir):
    script(model, [SAMUEL], revised=[KITTLE])
    run = pipeline.answer(BUCS)

    assert run.first_answer == f"{SAMUEL_LEAD} The depth chart ranks him second."
    assert run.result.answer == f"{KITTLE_LEAD}. His 24.9% recent target share leads the 49ers after Evans."
    assert run.approved and [c.status for c in run.critiques] == ["needs_revision", "approved"]
    assert run.critiques[0].blocking[0].check == "verdict_support"
    # Factor agents ran once (3 factors); the verdict ran twice: first answer and one revision.
    assert len(calls(model, analyst.FACTOR_PROMPT)) == 3
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 2
    revision_prompt = calls(model, analyst.VERDICT_PROMPT)[1][-1]["content"]
    # The revision gets the facts and the critic's issues as rules, not the previous answer.
    assert "Rules from a check against the data (follow every one):" in revision_prompt
    assert "previous answer" not in revision_prompt and SAMUEL_LEAD not in revision_prompt
    assert "trails George Kittle (TE) 24.9% and Christian McCaffrey (RB) 22.8%" in revision_prompt

    lines = read_trace(trace_dir)
    assert [(l["agent_name"], l["action"], l["status"]) for l in lines if l["action"] in ("critique", "revise", "final")] == [
        ("critic", "critique", "needs_revision"),
        ("analyst", "revise", "ok"),
        ("critic", "critique", "approved"),
        ("critic", "final", "approved"),
    ]


def test_review_gets_60s_and_revise_65s(real_sample, model):
    script(model, [SAMUEL], revised=[KITTLE])
    pipeline.answer(BUCS)
    by_step = {}
    for c, k in zip(model.calls, model.kwargs):
        step = "revise" if "Rules from a check against the data" in c[-1]["content"] else c[0]["content"]
        by_step.setdefault(step, []).append(k)
    review, revise = by_step[critic.REVIEW_PROMPT][0], by_step["revise"][0]
    verdict = by_step[analyst.VERDICT_PROMPT][0]
    assert (review["timeout"], review["max_tokens"]) == (60, 8192)
    assert (revise["timeout"], revise["max_tokens"]) == (65, 8192)
    assert (verdict["timeout"], verdict["max_tokens"]) == (60, 4096)  # the first verdict is unchanged
    assert pipeline.RUN_BUDGET == 360


def test_a_hard_rule_broken_twice_gets_the_rule_based_verdict_in_round_3(real_sample, model, trace_dir):
    script(model, [SAMUEL])  # every revision repeats the flagged verdict
    run = pipeline.answer(BUCS)

    assert run.approved and [c.round for c in run.critiques] == [1, 2, 3]
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 2  # first answer + 1 revision; round 3 needs no model
    assert len(calls(model, critic.REVIEW_PROMPT)) == 3  # the Critic checks the rule-based verdict too
    assert run.result.verdict_by == "rule-based"
    assert "pick up George Kittle" in run.result.answer
    assert run.result.answer.endswith("(Rule-based verdict: the model recommended a player the usage numbers "
                                      "do not back twice, so fixed thresholds were applied.)")
    lines = read_trace(trace_dir)
    assert [l["status"] for l in lines if l["action"] == "critique"] == ["needs_revision", "needs_revision", "approved"]
    revises = [l for l in lines if l["action"] == "revise"]
    assert [l["status"] for l in revises] == ["ok", "fallback"]
    assert revises[1]["reason"] == "the model recommended a player the usage numbers do not back twice"
    [final] = [l for l in lines if l["action"] == "final"]
    assert (final["status"], final["rounds"], final["revisions"]) == ("approved", 3, 2)


def test_loop_stops_after_three_rounds_with_a_critic_note(real_sample, model, trace_dir):
    # A copied support label is not a hard rule, so the model keeps the revisions and the
    # run can end unresolved, with the reason in the critic note.
    labelled = json.dumps({"verdict": "Pick up George Kittle", "why": "Team usage [strong]: 24.9% recent target share."})
    script(model, [labelled])
    run = pipeline.answer(BUCS)

    assert not run.approved
    assert [c.round for c in run.critiques] == [1, 2, 3]
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 3  # first answer + 2 revisions
    assert len(calls(model, critic.REVIEW_PROMPT)) == 3
    assert run.result.answer.endswith("Critic note: '[strong]' is a support label copied from the prompt.")
    lines = read_trace(trace_dir)
    assert [l["status"] for l in lines if l["action"] == "critique"] == ["needs_revision"] * 3
    assert len([l for l in lines if l["action"] == "revise"]) == 2
    [final] = [l for l in lines if l["action"] == "final"]
    assert (final["status"], final["rounds"], final["revisions"]) == ("unresolved", 3, 2)


def test_summary_issues_are_recorded_without_using_a_round(real_sample, model):
    script(model, [KITTLE], summaries={"Games without the player": "Mike Evans has missed 0.0 games."})
    run = pipeline.answer(BUCS)

    assert run.approved and len(run.critiques) == 1
    [issue] = run.critiques[0].issues
    assert (issue.check, issue.where, issue.blocking) == ("artifacts", "factor:Games without the player", False)


def test_failed_revision_falls_back_to_the_rule_verdict(real_sample, model, trace_dir):
    script(model, [SAMUEL], revised=[meterless.MeterlessError("down")])
    run = pipeline.answer(BUCS)

    # The rule-based stand-in follows target share, so it passes on round 2.
    assert run.approved and run.result.verdict_by == "rule-based"
    assert run.result.answer.startswith(f"{KITTLE_LEAD} if available.")
    [revise] = [l for l in read_trace(trace_dir) if l["action"] == "revise"]
    assert (revise["status"], revise["verdict_by"]) == ("fallback", "rule-based")


def test_out_of_time_review_and_revision_fall_back_to_rules(real_sample, model, monkeypatch):
    script(model, [SAMUEL])
    monkeypatch.setattr(pipeline, "RUN_BUDGET", 0)
    run = pipeline.answer(BUCS)

    assert not calls(model, critic.REVIEW_PROMPT)  # skipped: no time left
    assert [c.reviewed_by for c in run.critiques] == ["rule-based", "rule-based"]
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 1  # the revision call was skipped too
    assert run.approved and run.result.verdict_by == "rule-based"


@pytest.mark.parametrize("setting, review_calls", [("false", 0), (None, 1)])
def test_model_review_setting(real_sample, model, monkeypatch, setting, review_calls):
    if setting is None:
        monkeypatch.delenv("CRITIC_MODEL_REVIEW", raising=False)
    else:
        monkeypatch.setenv("CRITIC_MODEL_REVIEW", setting)
    script(model, [KITTLE])
    pipeline.answer(BUCS)
    assert len(calls(model, critic.REVIEW_PROMPT)) == review_calls


def test_review_runs_the_loop_on_a_saved_answer(model, trace_dir):
    """What scripts/demo_critic.py does: the Oct 22 "Start Deebo Samuel" answer, no Analyst run."""
    from helpers import load_example

    script(model, [KITTLE])
    run = pipeline.review(load_example("who-becomes-the-bucs", run="d52e2e813360"))

    assert run.first_answer.startswith("Start Deebo Samuel. The depth chart [strong]")
    assert [c.status for c in run.critiques] == ["needs_revision", "approved"]
    assert {i.check for i in run.critiques[0].blocking} == {"verdict_support", "artifacts"}
    assert run.result.answer.startswith(f"{KITTLE_LEAD}.")
    assert not calls(model, analyst.FACTOR_PROMPT) and not calls(model, analyst.CLASSIFY_PROMPT)


def test_after_a_review_timeout_later_rounds_use_the_code_checks_only(real_sample, model, trace_dir):
    # Smoke question 4: three review timeouts at 60s each, 257s in all.
    script(model, [SAMUEL], revised=[KITTLE], review=meterless.MeterlessError("No reply within 60s."))
    run = pipeline.answer(BUCS)
    assert run.approved and len(run.critiques) == 2
    assert len(calls(model, critic.REVIEW_PROMPT)) == 1  # round 2 does not call the reviewer
    assert run.critiques[1].reviewed_by == "rule-based"
    assert run.critiques[1].review_note == "the model review timed out in round 1; code checks only"
    [skipped] = [l for l in read_trace(trace_dir) if l["action"] == "review" and l["status"] == "skipped"]
    assert skipped["round"] == 2 and skipped["reason"] == run.critiques[1].review_note


def script_compare(model, names, verdict):
    """A compare question whose every verdict (first and revisions) is the same reply."""
    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return json.dumps({"player_name": names[0], "player_names": names, "question_type": "compare"})
        if system == analyst.COMPARE_FACTOR_PROMPT:
            return json.dumps({"favours": None, "support": "moderate", "summary": "Facts."})
        if system == analyst.VERDICT_PROMPT:
            return verdict
        if system == critic.REVIEW_PROMPT:
            return NO_ISSUES
        raise AssertionError(system[:60])

    model.respond = respond


@pytest.mark.parametrize("question, names, verdict", [
    # Smoke 7: LA is rank 31 of 32 (tough), called "easier" in all three rounds.
    ("Start Pickens or Bowers in week 7?", ["George Pickens", "Brock Bowers"],
     json.dumps({"verdict": "Start Brock Bowers over George Pickens",
                 "why": "Bowers averages 20.6 PPR points per game and faces an easier matchup against LA."})),
    # Smoke 1: the model kept giving Juwan Johnson the easier matchup.
    ("Who should I start, Johnson or McBride?", ["Juwan Johnson", "Trey McBride"],
     json.dumps({"verdict": "Start Trey McBride over Juwan Johnson",
                 "why": "McBride averages 17.2 PPR points per game; Juwan Johnson has the easier matchup."})),
])
def test_a_matchup_described_the_wrong_way_twice_gets_the_rule_based_verdict(
        real_sample, model, trace_dir, question, names, verdict):
    script_compare(model, names, verdict)
    run = pipeline.answer(question)

    assert run.critiques[0].status == "needs_revision"
    assert any(i.check == "direction" and i.rule == "direction" for i in run.critiques[0].blocking)
    assert run.approved and run.result.verdict_by == "rule-based"
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 2  # first answer + 1 revision; round 3 needs no model
    assert "described a matchup or a comparison the wrong way round twice" in run.result.answer
    assert run.result.answer.endswith("so fixed thresholds were applied.)")
    assert not any(i.check == "direction" for i in run.critiques[-1].blocking)
    [final] = [l for l in read_trace(trace_dir) if l["action"] == "final"]
    assert (final["status"], final["rounds"]) == ("approved", 3)
