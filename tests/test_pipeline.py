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
            pool = revised if "A critic checked it" in user else verdicts
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

    assert run.first_answer == "Start Deebo Samuel. The depth chart ranks him second."
    assert run.result.answer == "Pick up George Kittle. His 24.9% recent target share leads the 49ers after Evans."
    assert run.approved and [c.status for c in run.critiques] == ["needs_revision", "approved"]
    assert run.critiques[0].blocking[0].check == "verdict_support"
    # Factor agents ran once (3 factors); the verdict ran twice: first answer and one revision.
    assert len(calls(model, analyst.FACTOR_PROMPT)) == 3
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 2
    revision_prompt = calls(model, analyst.VERDICT_PROMPT)[1][-1]["content"]
    assert "Your previous answer:\nStart Deebo Samuel." in revision_prompt
    assert "trails George Kittle (TE) 24.9% and Christian McCaffrey (RB) 22.8%" in revision_prompt

    lines = read_trace(trace_dir)
    assert [(l["agent_name"], l["action"], l["status"]) for l in lines if l["action"] in ("critique", "revise", "final")] == [
        ("critic", "critique", "needs_revision"),
        ("analyst", "revise", "ok"),
        ("critic", "critique", "approved"),
        ("critic", "final", "approved"),
    ]


def test_loop_stops_after_three_rounds_with_a_critic_note(real_sample, model, trace_dir):
    script(model, [SAMUEL])  # every revision repeats the flagged verdict
    run = pipeline.answer(BUCS)

    assert not run.approved
    assert [c.round for c in run.critiques] == [1, 2, 3]
    assert len(calls(model, analyst.VERDICT_PROMPT)) == 3  # first answer + 2 revisions
    assert len(calls(model, critic.REVIEW_PROMPT)) == 3
    assert run.result.answer.startswith("Start Deebo Samuel. The depth chart ranks him second. Critic note: ")
    assert "trails George Kittle (TE) 24.9%" in run.result.answer
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
    assert run.result.answer.startswith("Pick up George Kittle if available.")
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
    assert run.result.answer.startswith("Pick up George Kittle.")
    assert not calls(model, analyst.FACTOR_PROMPT) and not calls(model, analyst.CLASSIFY_PROMPT)
