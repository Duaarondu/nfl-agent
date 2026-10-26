"""The default Analyst flow: classify -> code (lookup, premise, factor queries)
-> one factor agent per factor, in parallel (rule-based fallback) -> verdict."""

import json
import re
import threading
import time

import pytest
from helpers import classify, read_trace

from app.adapters import meterless
from app.agents import analyst
from app.agents.analyst import AnalystError, analyze, round_numbers

WATSON_WHY = "Why is Christian Watson scoring so many fantasy points this season?"
BUCS = "Who becomes the Bucs' WR1 if Mike Evans is out?"
WHY_QUERIES = [
    "Player lookup", "Status", "Opportunity", "Teammate absences",
    "Team pass rate and game script", "Big plays", "Touchdowns and red zone", "Matchups",
]
WHY_FACTORS = WHY_QUERIES[2:]


def rating(support="moderate", summary="Some facts with 1 number."):
    return json.dumps({"support": support, "summary": summary})


def verdict(action="Hold him", why="He has a 22.2% target share."):
    return json.dumps({"verdict": action, "why": why})


def script(model, classification, factors=None, answer=None):
    """Answer each call by its prompt: classify, factor agent (by factor name) or verdict.

    factors maps factor name -> reply text, Exception, or callable(messages) -> either.
    """
    factors = factors or {}
    answers = list(answer) if isinstance(answer, list) else [answer or verdict()]

    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classification
        if system == analyst.FACTOR_PROMPT:
            name = re.search(r"Factor: (.+)", messages[1]["content"]).group(1)
            reply = factors.get(name, rating(summary=f"{name} facts."))
            return reply(messages) if callable(reply) else reply
        if system == analyst.VERDICT_PROMPT:
            return answers.pop(0) if len(answers) > 1 else answers[0]
        raise AssertionError(f"unexpected prompt: {system[:60]}")

    model.respond = respond


def calls_for(model, prompt):
    return [c for c in model.calls if c[0]["content"] == prompt]


def test_why_question_runs_one_agent_per_factor_then_verdict(real_sample, model):
    script(model, classify("Christian Watson", "why"), factors={
        "Opportunity": rating("strong", "Target share 22.2%."),
        "Matchups": rating("not supported", "No soft-matchup edge."),
        "Big plays": rating("weak", "11.2 yards per target."),
    }, answer=verdict("hold Christian Watson.", "his 22.24% target share leads the team."))
    result = analyze(WATSON_WHY)

    assert [q.factor for q in result.queries] == WHY_QUERIES
    assert len(calls_for(model, analyst.CLASSIFY_PROMPT)) == 1
    assert len(calls_for(model, analyst.FACTOR_PROMPT)) == 6
    assert len(calls_for(model, analyst.VERDICT_PROMPT)) == 1
    # A why question: the explanation first, the action last.
    assert result.answer == "His 22.2% target share leads the team. Verdict: hold Christian Watson."
    assert result.verdict_by == "model"
    assert result.disclaimer == analyst.DISCLAIMER
    assert [(f.factor, f.support) for f in result.factors] == [
        ("Opportunity", "strong"),
        ("Teammate absences", "moderate"), ("Team pass rate and game script", "moderate"),
        ("Touchdowns and red zone", "moderate"),
        ("Big plays", "weak"),
        ("Matchups", "not supported"),
    ]
    assert all(f.rated_by == "model" and f.evidence for f in result.factors)
    assert result.factors[0].evidence[0].headers[4] == "targets"
    assert result.not_measurable == list(analyst.NOT_MEASURABLE)


def test_each_agent_sees_only_its_factor_and_nobody_sees_the_schema(real_sample, model):
    script(model, classify("Christian Watson", "why"))
    analyze(WATSON_WHY)

    for call in calls_for(model, analyst.FACTOR_PROMPT):
        user = call[1]["content"]
        assert "Christian Watson: GB, WR" in user  # the player line
        if "Factor: Matchups" in user:
            assert "soft defenses" in user and "red-zone" not in user
    text = "\n".join(m["content"] for c in model.calls for m in c)
    assert "## NFLVERSE." not in text and "SELECT" not in text
    [verdict_call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert "- Opportunity [moderate]: Opportunity facts." in verdict_call[1]["content"]
    assert "Injury status: Latest injury report: week 7" in verdict_call[1]["content"]


def test_calls_disable_thinking_and_have_timeouts(real_sample, model):
    script(model, classify("Christian Watson", "why"))
    analyze(WATSON_WHY)

    assert all(k["chat_template_kwargs"] == {"enable_thinking": False} for k in model.kwargs)
    by_prompt = {c[0]["content"]: k for c, k in zip(model.calls, model.kwargs)}
    assert by_prompt[analyst.CLASSIFY_PROMPT]["timeout"] == analyst.CLASSIFY_TIMEOUT
    assert by_prompt[analyst.FACTOR_PROMPT]["timeout"] == analyst.FACTOR_TIMEOUT == 10
    assert 0 < by_prompt[analyst.VERDICT_PROMPT]["timeout"] <= 60


def test_factor_agents_are_named_in_traces(real_sample, model, trace_dir):
    script(model, classify("Christian Watson", "why"))
    analyze(WATSON_WHY)

    lines = read_trace(trace_dir)
    agents = {l["agent_name"] for l in lines if l["action"] == "model_call"}
    assert agents == {"planner", "analyst"} | {f"factor_agent:{f}" for f in WHY_FACTORS}
    rates = [l for l in lines if l["action"] == "rate_factor"]
    assert {l["agent_name"] for l in rates} == {f"factor_agent:{f}" for f in WHY_FACTORS}
    assert all(l["status"] == "ok" and l["rated_by"] == "model" for l in rates)
    calls = [l for l in lines if l["action"] == "model_call"]
    assert all(c["model"] == "stub-routed" and isinstance(c["duration_ms"], int) for c in calls)
    assert [l["step"] for l in calls if l["agent_name"] == "planner"] == ["classify"]
    assert [l["step"] for l in calls if l["agent_name"] == "analyst"] == ["verdict"]
    [handoff] = [l for l in lines if l["action"] == "handoff"]
    assert (handoff["agent_name"], handoff["target_agent"], handoff["classified_by"]) == ("planner", "analyst", "model")
    assert (handoff["player_name"], handoff["question_type"]) == ("Christian Watson", "why")


def test_failed_factor_agent_falls_back_to_rules(real_sample, model, trace_dir):
    script(model, classify("Christian Watson", "why"), factors={
        "Matchups": meterless.MeterlessError("provider_deadline", status=502),
        "Big plays": "not json",  # invalid twice: the repair retry fails too
    })
    result = analyze(WATSON_WHY)

    by_name = {f.factor: f for f in result.factors}
    assert by_name["Matchups"].rated_by == "rule-based"
    assert by_name["Matchups"].support == "not supported"  # 16 PPR vs soft defenses, 21.7 vs the rest
    assert "soft defenses" in by_name["Matchups"].rule
    assert by_name["Big plays"].rated_by == "rule-based" and by_name["Big plays"].support == "strong"
    assert by_name["Big plays"].summary.startswith("538 receiving yards on 48 targets")
    assert by_name["Opportunity"].rated_by == "model"

    fallbacks = [l for l in read_trace(trace_dir) if l["action"] == "rate_factor" and l["status"] == "fallback"]
    assert {l["agent_name"] for l in fallbacks} == {"factor_agent:Matchups", "factor_agent:Big plays"}
    assert all(l["rated_by"] == "rule-based" and l["rule"] for l in fallbacks)
    [answer_line] = [l for l in read_trace(trace_dir) if l["action"] == "answer"]
    assert sorted(answer_line["rule_based"]) == ["Big plays", "Matchups"]


def test_slow_factor_agent_is_cut_off_at_the_window(real_sample, model, monkeypatch, trace_dir):
    release = threading.Event()

    def slow(messages):
        release.wait(10)
        return rating("strong")

    monkeypatch.setattr(analyst, "FACTOR_WINDOW", 2)
    monkeypatch.setattr(analyst, "MIN_FACTOR_WINDOW", 2)
    script(model, classify("Christian Watson", "why"), factors={"Teammate absences": slow})
    started = time.perf_counter()
    result = analyze(WATSON_WHY)
    elapsed = time.perf_counter() - started
    release.set()

    assert elapsed < 5
    absences = next(f for f in result.factors if f.factor == "Teammate absences")
    assert absences.rated_by == "rule-based"
    [line] = [l for l in read_trace(trace_dir) if l["status"] == "fallback" and l["action"] == "rate_factor"]
    assert "no reply within" in line["reason"].lower()  # the window or the call limit, whichever fires first


def test_factor_agent_repair_retry_succeeds(real_sample, model):
    replies = iter(["not json", rating("strong", "Recovered.")])
    script(model, classify("Christian Watson", "why"), factors={"Matchups": lambda m: next(replies)})
    result = analyze(WATSON_WHY)

    matchups = next(f for f in result.factors if f.factor == "Matchups")
    assert (matchups.support, matchups.summary, matchups.rated_by) == ("strong", "Recovered.", "model")


def test_claims_are_code_facts_with_evidence(real_sample, model):
    script(model, classify("Christian Watson", "why"), factors={"Matchups": rating("not supported", "None.")})
    result = analyze(WATSON_WHY)

    texts = [c.text for c in result.claims]
    assert texts[0] == "Christian Watson: GB, WR, roster status ACT (week 7)."
    assert texts[1].startswith("Latest injury report: week 7")
    assert "None." not in texts  # unsupported factors are not claims
    assert all(c.evidence and c.evidence[0].rows for c in result.claims)


def test_replacement_question_rates_usage_depth_and_games_without(real_sample, model):
    script(model, classify("Mike Evans", "replacement"),
           answer=verdict("Pick up Deebo Samuel", "Deebo Samuel becomes the WR1 by depth chart."))
    result = analyze("Mike Evans is out. Who becomes the 49ers' WR1, and should I pick him up?")

    assert [q.factor for q in result.queries] == [
        "Player lookup", "Status", "Team usage", "Depth chart", "Games without the player",
    ]
    assert sorted(f.factor for f in result.factors) == ["Depth chart", "Games without the player", "Team usage"]
    depth_call = next(c for c in calls_for(model, analyst.FACTOR_PROMPT) if "Factor: Depth chart" in c[1]["content"])
    assert "WR depth chart: 1. Mike Evans (WR1), 2. Deebo Samuel (WR2)" in depth_call[1]["content"]
    without = next(c for c in calls_for(model, analyst.FACTOR_PROMPT) if "Factor: Games without" in c[1]["content"])
    assert "He played every team game this season" in without[1]["content"]
    assert result.answer == "Deebo Samuel is next at WR on the depth chart (11.1% recent target share), so for fantasy: pick up Deebo Samuel. Deebo Samuel becomes the WR1 by depth chart."
    assert result.premise_correction is None


def test_wrong_team_premise_is_corrected_from_the_data(real_sample, model, trace_dir):
    script(model, classify("Mike Evans", "replacement"))
    result = analyze(BUCS)

    assert result.premise_correction == "Mike Evans is on SF in the data (rosters, week 7), not TB."
    [verdict_call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert "Premise check: Mike Evans is on SF" in verdict_call[1]["content"]
    [answer_line] = [l for l in read_trace(trace_dir) if l["action"] == "answer"]
    assert answer_line["premise_corrected"] is True


def test_model_player_name_is_preferred(real_sample, model):
    script(model, classify("Christian Watson", "start_sit"))
    result = analyze("Should I start George Kittle or Christian Watson?")
    assert "Christian Watson" in result.queries[1].purpose


def test_model_full_name_finds_a_half_named_player(real_sample, model):
    script(model, classify("Christian Watson", "why"))
    assert analyze("why is watson so good lately?").queries[0].rows[0][1] == "Christian Watson"


def test_classify_falls_back_to_keywords(real_sample, model, trace_dir):
    script(model, "not json")
    result = analyze(WATSON_WHY)

    assert [q.factor for q in result.queries] == WHY_QUERIES
    assert any(l["action"] == "classify" and l["status"] == "fallback" for l in read_trace(trace_dir))


def test_no_player_found_raises(real_sample, model):
    script(model, classify(None, "start_sit"))
    with pytest.raises(AnalystError, match="Could not find the NFL player"):
        analyze("Who should I start at flex this week?")
    assert len(model.calls) == 1


def test_verdict_repaired_once(real_sample, model):
    bad_action = json.dumps({"verdict": "Deebo is the guy", "why": "x"})
    script(model, classify("Christian Watson", "why"), answer=[bad_action, verdict("Sit him", "Usage fell.")])
    result = analyze(WATSON_WHY)
    assert (result.answer, result.verdict_by) == ("Usage fell. Verdict: sit him.", "model")
    assert "must start with one of" in calls_for(model, analyst.VERDICT_PROMPT)[-1][-1]["content"]


@pytest.mark.parametrize("failure", [["nope", "still nope"], meterless.MeterlessError("down")])
def test_failed_verdict_falls_back_to_rules(real_sample, model, trace_dir, failure):
    script(model, classify("Christian Watson", "why"), factors={
        "Opportunity": rating("strong", "Target share 22.2%. More text."),
        "Matchups": rating("not supported", "None."),
    }, answer=failure)
    result = analyze(WATSON_WHY)

    assert result.verdict_by == "rule-based"
    assert result.answer.startswith("Most supported by the data: Opportunity (strong): Target share 22.2%;")
    assert result.answer.endswith(
        "Verdict: hold Christian Watson. (Rule-based verdict: the verdict model call failed, so fixed thresholds were applied.)"
    )
    assert "Not supported: Matchups." in result.answer
    assert "(Rule-based verdict: the verdict model call failed" in result.answer
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "verdict"]
    assert line["status"] == "fallback" and line["rated_by"] == "rule-based"
    [answer_line] = [l for l in read_trace(trace_dir) if l["action"] == "answer"]
    assert answer_line["verdict_by"] == "rule-based"


def test_rule_based_replacement_verdict_names_the_stand_in(real_sample, model):
    script(model, classify("Mike Evans", "replacement"), answer=meterless.MeterlessError("down"))
    result = analyze(BUCS)
    # Kittle's 24.9% recent target share beats Samuel's 11.1%; the depth chart's pick is still named.
    # The literal answer (the depth chart) first, then the fantasy advice (target share).
    assert result.answer.startswith("Deebo Samuel is next at WR on the depth chart, but the target share points to George Kittle (24.9%), so for fantasy: pick up George Kittle if available.")
    assert "George Kittle (TE) has the top recent target share among his teammates (24.9%)." in result.answer
    assert "The depth chart lists" not in result.answer  # said once, in the lead


def test_thinking_and_fences_are_ignored(real_sample, model):
    script(
        model, "<think>{not json}</think>" + classify("Christian Watson", "why"),
        answer='<think>maybe {"x": 1}</think>\n```json\n' + verdict("Start him", "Big week.") + "\n```",
    )
    assert analyze(WATSON_WHY).answer == "Big week. Verdict: start him."


def test_trace_lines_have_required_fields(real_sample, model, trace_dir):
    script(model, classify("Christian Watson", "why"))
    analyze(WATSON_WHY, run_id="run123")

    required = {
        "timestamp", "run_id", "agent_name", "action", "target_agent", "status",
        "retry_count", "sql", "model", "rows_returned", "duration_ms",
    }
    lines = read_trace(trace_dir)
    assert all(required <= line.keys() for line in lines)
    assert {line["run_id"] for line in lines} == {"run123"}


def test_round_numbers_leaves_short_numbers_and_versions():
    assert round_numbers("9 targets, 12.5 yds, v1.2.34") == "9 targets, 12.5 yds, v1.2.34"
    assert round_numbers("7.6000000000000005 points, 20.63%") == "7.6 points, 20.6%"


def test_hung_call_is_cut_off_at_the_per_call_limit(real_sample, model, monkeypatch):
    release = threading.Event()

    def hang(messages):
        release.wait(10)
        return verdict()

    monkeypatch.setattr(analyst, "CALL_TIMEOUT", 0.5)
    script(model, classify("Christian Watson", "why"))
    model_respond = model.respond
    model.respond = lambda m: hang(m) if m[0]["content"] == analyst.VERDICT_PROMPT else model_respond(m)
    started = time.perf_counter()
    result = analyze(WATSON_WHY)
    release.set()
    assert time.perf_counter() - started < 5
    assert result.verdict_by == "rule-based"


def test_repair_retry_skipped_when_the_budget_is_nearly_used(real_sample, model, monkeypatch, trace_dir):
    monkeypatch.setattr(analyst, "MIN_RETRY_SECONDS", 10_000)
    monkeypatch.setattr(analyst, "CALL_TIMEOUT", 10_000)  # a retry needs the shorter of the two
    script(model, classify("Christian Watson", "why"), answer="not json")
    assert analyze(WATSON_WHY).verdict_by == "rule-based"
    assert any(l["action"] == "model_call" and l["status"] == "skipped" for l in read_trace(trace_dir))


def test_factor_agents_get_the_premise_correction(real_sample, model):
    script(model, classify("Mike Evans", "replacement"))
    analyze(BUCS)

    for call in calls_for(model, analyst.FACTOR_PROMPT):
        assert "Premise check: Mike Evans is on SF in the data" in call[1]["content"]


def test_agents_get_the_corrected_question_and_result_keeps_the_original(real_sample, model):
    script(model, classify("Mike Evans", "replacement"))
    result = analyze(BUCS)

    for call in calls_for(model, analyst.FACTOR_PROMPT) + calls_for(model, analyst.VERDICT_PROMPT):
        assert "Question: Who becomes the 49ers' WR1 if Mike Evans is out?" in call[1]["content"]
    assert result.question == BUCS


@pytest.mark.parametrize("left, window", [
    (150, 15),  # fast queries: the usual cap
    (58, 13),   # what is left after the verdict's reserve
    (50, 10),   # slow queries: still the guaranteed minimum
    (-30, 10),  # queries ran past the whole budget
])
def test_factor_window_has_a_guaranteed_minimum(left, window):
    assert analyst._factor_window(left) == window


def test_slow_queries_still_leave_the_factor_agents_their_minimum(real_sample, model, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(analyst.time, "perf_counter", lambda: clock[0])
    real_plan = analyst._run_plan

    def slow_plan(*args, **kwargs):
        plan = real_plan(*args, **kwargs)
        clock[0] += 140  # the live queries took 140s of the 150s budget
        return plan

    windows, deadlines = [], []
    real_rate, real_verdict = analyst._rate_factors, analyst._verdict
    monkeypatch.setattr(analyst, "_run_plan", slow_plan)
    monkeypatch.setattr(analyst, "_rate_factors",
                        lambda *a, window, **k: windows.append(window) or real_rate(*a, window=window, **k))
    monkeypatch.setattr(analyst, "_verdict",
                        lambda *a, deadline, **k: deadlines.append(deadline) or real_verdict(*a, deadline=deadline, **k))
    script(model, classify("Christian Watson", "why"))
    analyze(WATSON_WHY)
    assert windows == [analyst.MIN_FACTOR_WINDOW]
    assert deadlines[0] - clock[0] >= analyst.VERDICT_RESERVE  # the verdict keeps its reserve too


COMPARE = ("I have Jameson Williams on my bench and George Pickens in my starting lineup, "
           "who should I pick?")
PAIR = ["Jameson Williams", "George Pickens"]


def classify_compare(names=PAIR):
    return json.dumps({"player_name": names[0], "player_names": names, "question_type": "compare"})


def script_compare(model, favours=None, answer=None):
    """Like script(), for compare: head-to-head factor agents reply with favours."""
    favours = favours or {}

    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classify_compare()
        if system == analyst.COMPARE_FACTOR_PROMPT:
            name = re.search(r"Factor: (.+)", messages[1]["content"]).group(1)
            reply = favours.get(name, json.dumps(
                {"favours": "George Pickens", "support": "moderate", "summary": f"{name} facts."}))
            return reply(messages) if callable(reply) else reply
        if system == analyst.VERDICT_PROMPT:
            return answer or verdict("Start George Pickens over Jameson Williams",
                                     "Pickens scores 10.9 points per game to Williams' 9.7.")
        raise AssertionError(f"unexpected prompt: {system[:60]}")

    model.respond = respond


def test_compare_question_looks_up_and_queries_both_players(real_sample, model):
    script_compare(model)
    result = analyze(COMPARE)
    assert result.question_type == "compare"
    assert [p.name for p in result.players] == PAIR
    factors = [q.factor for q in result.queries]
    assert factors == ["Player lookup", *analyst.factor_queries.COMPARE_FACTORS]
    for q in result.queries[1:]:
        assert not q.error, q.error
        names = {row[q.headers.index("player")] for row in q.rows}
        assert names == set(PAIR), q.factor
    # Every agent said Pickens; in the later weeks Williams leads (15.5 to 14.1 per game),
    # so that summary is replaced by the code's, which favours Williams.
    by_factor = {f.factor: f for f in result.factors}
    trend = by_factor.pop("Recent trend")
    assert trend.rated_by == "rule-based" and trend.favours == "Jameson Williams"
    assert "model summary replaced: it says this factor favours George Pickens" in trend.rule
    assert {f.favours for f in by_factor.values()} == {"George Pickens"}
    assert result.answer.startswith("Start George Pickens over Jameson Williams")


def test_compare_factor_agents_see_both_players_and_must_name_one(real_sample, model, trace_dir):
    script_compare(model, favours={"Recent trend": json.dumps(
        {"favours": "Mike Evans", "support": "strong", "summary": "x"})})
    result = analyze(COMPARE)
    prompts = calls_for(model, analyst.COMPARE_FACTOR_PROMPT)
    assert len(prompts) >= 5 and all("Players:" in c[1]["content"] for c in prompts)
    trend = next(f for f in result.factors if f.factor == "Recent trend")
    assert trend.rated_by == "rule-based"  # Mike Evans is not one of the two, twice
    assert trend.favours in (*PAIR, "even")
    lines = [l for l in read_trace(trace_dir) if l["action"] == "rate_factor"]
    assert all("favours" in l for l in lines)


def test_compare_in_league_scoring(real_sample, model):
    from app.agents.memory import UserContext

    script_compare(model)
    result = analyze(COMPARE, memory=UserContext(user_id="t", scoring="half"))
    usage = next(q for q in result.queries if q.factor == "Team usage share")
    assert "half_ppr_per_game" in usage.headers


def test_compare_rule_verdict_when_the_model_fails(real_sample, model):
    script_compare(model, answer=json.dumps({"nope": 1}))
    result = analyze(COMPARE)
    assert result.verdict_by == "rule-based"
    assert re.match(r"Start (Jameson Williams|George Pickens) over (Jameson Williams|George Pickens)",
                    result.answer)


def test_compare_with_one_player_found_falls_back_to_start_sit(real_sample, model):
    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return classify_compare(["George Pickens", "Nobody Atall"])
        if system == analyst.FACTOR_PROMPT:
            return rating()
        return verdict("Start him")

    model.respond = respond
    result = analyze("Should I start George Pickens or Nobody Atall?")
    assert result.question_type == "start_sit"
    assert result.player.name == "George Pickens"


# --- last names, clarification, position labels, the matchup ---

UI_QUESTION = "Who should I start Trey Mcbride or Bowers for week 7"


def script_ui(model, route=None, factor_reply=None):
    """The Planner says start_sit about McBride (as it did live); agents rate; verdict picks Bowers."""
    def respond(messages):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return route or classify("Trey McBride", "start_sit")
        if system in (analyst.FACTOR_PROMPT, analyst.COMPARE_FACTOR_PROMPT):
            reply = factor_reply(messages) if factor_reply else None
            return reply or json.dumps({"favours": "Brock Bowers", "support": "moderate", "summary": "Facts."})
        return verdict("Start Brock Bowers over Trey McBride",
                       "Bowers scores 20.6 PPR points per game to McBride's 17.2.")
    model.respond = respond


def test_last_name_is_looked_up_and_the_choice_becomes_a_compare(real_sample, model, trace_dir):
    script_ui(model)
    result = analyze(UI_QUESTION)
    assert result.question_type == "compare"
    assert [p.name for p in result.players] == ["Trey McBride", "Brock Bowers"]
    assert [q.factor for q in result.queries][:2] == ["Player lookup", "Last-name lookup"]
    assert result.name_note == "Bowers = Brock Bowers, LV TE."
    assert result.answer.startswith("Start Brock Bowers over Trey McBride. Bowers = Brock Bowers, LV TE. Bowers")
    matchup = next(q for q in result.queries if q.factor == "Next matchup")
    assert "week 7 opponent" in matchup.purpose  # the week the question names
    lines = read_trace(trace_dir)
    [names] = [l for l in lines if l["action"] == "last_names"]
    assert names["resolved"] == {"Bowers": "Brock Bowers"}
    assert any(l["action"] == "compare" and l["from_type"] == "start_sit" for l in lines)


def test_last_name_reaches_the_factor_agents_and_the_verdict(real_sample, model):
    script_ui(model)
    analyze(UI_QUESTION)
    factor = calls_for(model, analyst.COMPARE_FACTOR_PROMPT)[0][1]["content"]
    assert "Named by last name: Bowers = Brock Bowers, LV TE." in factor
    [verdict_call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert "Named by last name (from the rosters): Bowers = Brock Bowers, LV TE." in verdict_call[1]["content"]


@pytest.mark.parametrize("question, says", [
    ("Should I start Trey McBride or Zzyzx?", 'couldn\'t find a skill player called "Zzyzx"'),
    ("Who should I start, Qqq or Zzyzx?", '"Qqq"'),
])
def test_unknown_last_name_asks_which_player(real_sample, model, trace_dir, question, says):
    script_ui(model, route=classify(None, "start_sit"))
    with pytest.raises(analyst.NeedsClarification) as error:
        analyze(question)
    assert says in str(error.value) and str(error.value).endswith("Which player do you mean? Please give their full name.")
    assert not calls_for(model, analyst.VERDICT_PROMPT)  # no winner picked
    assert [l["action"] for l in read_trace(trace_dir) if l["action"] == "clarify"] == ["clarify"]


def test_wrong_position_label_in_a_factor_summary_is_retried_then_ruled(real_sample, model, trace_dir):
    bad = json.dumps({"favours": "Trey McBride", "support": "strong",
                      "summary": "Trey McBride is the Cardinals' WR1 with a 29.7% target share."})
    script_ui(model, factor_reply=lambda m: bad if "Factor: Team usage share" in m[1]["content"] else None)
    result = analyze(UI_QUESTION)
    usage = next(f for f in result.factors if f.factor == "Team usage share")
    assert usage.rated_by == "rule-based" and "WR1" not in usage.summary
    retries = [c for c in calls_for(model, analyst.COMPARE_FACTOR_PROMPT) if "Factor: Team usage share" in c[1]["content"]]
    assert len(retries) == 2 and "'WR1' is wrong for Trey McBride, who is a TE" in retries[1][-1]["content"]


def test_start_sit_rates_the_matchup_for_the_named_week(real_sample, model):
    script(model, classify("Trey McBride", "start_sit"), answer=verdict("Start Trey McBride", "He averages 17.2."))
    result = analyze("Should I start Trey McBride in week 7?")
    assert [q.factor for q in result.queries][-1] == "Next matchup"
    assert any(f.factor == "Next matchup" for f in result.factors)
    facts = calls_for(model, analyst.FACTOR_PROMPT)
    [m] = [c for c in facts if "Factor: Next matchup" in c[1]["content"]]
    assert "Trey McBride (ARI) plays DEN in week 7" in m[1]["content"]


# --- factor direction computed in code; first verdict hard rules ---


def test_factor_agents_get_the_directions_computed_in_code(real_sample, model):
    script_compare(model)
    analyze(COMPARE)
    [m] = [c for c in calls_for(model, analyst.COMPARE_FACTOR_PROMPT) if "Factor: Next matchup" in c[1]["content"]]
    assert "Directions (computed in code; your summary and rating must agree with them):" in m[1]["content"]
    assert "- Easier matchup: George Pickens (PHI allow 38.3, rank 3) over Jameson Williams (GB allow 33, rank 14)" \
        in m[1]["content"]


def test_a_reversed_matchup_summary_is_replaced_by_the_code_summary(real_sample, model, trace_dir):
    script_compare(model, favours={"Next matchup": json.dumps({
        "favours": "Jameson Williams", "support": "strong",
        "summary": "Jameson Williams faces the easier matchup: GB allow 33 to PHI's 38.3."})})
    result = analyze(COMPARE)
    matchup = next(f for f in result.factors if f.factor == "Next matchup")
    assert (matchup.rated_by, matchup.favours) == ("rule-based", "George Pickens")
    assert matchup.summary.startswith("George Pickens (DAL) plays PHI in week 7: PHI allow 38.3")
    assert "model summary replaced: it says this factor favours Jameson Williams" in matchup.rule
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "rate_factor" and l["status"] == "replaced"
              and l["agent_name"] == "factor_agent:Next matchup"]
    assert line["model_summary"].startswith("Jameson Williams")


def test_absences_raising_his_share_is_replaced(real_sample, model):
    script(model, classify("Christian Watson", "why"), factors={
        "Teammate absences": rating("strong", "Teammate absences in weeks 3-6 increased Watson's target share."),
    })
    result = analyze(WATSON_WHY)
    absences = next(f for f in result.factors if f.factor == "Teammate absences")
    assert absences.rated_by == "rule-based" and absences.summary.startswith("Week 3: Jayden Reed")
    assert "it says target share rose, but it fell in the weeks a teammate was out" in absences.rule


def test_first_verdict_gets_hard_rules_for_a_replacement(real_sample, model):
    from app.agents.memory import RosterPlayer, UserContext

    script(model, classify("Mike Evans", "replacement"), answer=verdict("Pick up George Kittle", "24.9%."))
    memory = UserContext(user_id="t", remembered=True,
                         roster=[RosterPlayer("00-0033288", "Christian McCaffrey", "SF", "RB")])
    analyze(BUCS, memory=memory)
    [call] = calls_for(model, analyst.VERDICT_PROMPT)
    prompt = call[1]["content"]
    rules = prompt[prompt.index("Hard rules (computed in code; follow every one):"):]
    assert "- Never recommend Mike Evans: the question says he is out." in rules
    assert "- Never recommend picking up Christian McCaffrey: already on the user's roster." in rules
    assert '- The verdict is "Pick up <one player>": who to add for fantasy, not a start/sit choice.' in rules
    assert "Mike Evans WR" in rules and "George Kittle TE" in rules and "Christian McCaffrey RB" in rules
    assert ('- The usage numbers back George Kittle (24.9%) among players not on the roster: recommend him '
            '("Pick up George Kittle").') in rules


def test_replacement_hard_rule_names_the_codes_pick_off_the_roster(real_sample, model):
    # Runs 6b5c3a81c4f9 and 76385bffb53c (Kittle on the roster) recommended Kittle, then Samuel,
    # and ended unresolved: the prompt never named the pick the critic wanted.
    from app.agents.memory import RosterPlayer, UserContext

    script(model, classify("Mike Evans", "replacement"), answer=verdict("Pick up Christian McCaffrey", "22.8%."))
    memory = UserContext(user_id="t", remembered=True,
                         roster=[RosterPlayer("00-0033288", "George Kittle", "SF", "TE")])
    analyze(BUCS, memory=memory)
    [call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert ('- The usage numbers back Christian McCaffrey (22.8%) among players not on the roster: recommend '
            'him ("Pick up Christian McCaffrey").') in call[1]["content"]


def test_why_verdict_hard_rule_names_the_player(real_sample, model):
    script(model, classify("Christian Watson", "why"))
    analyze(WATSON_WHY)
    [call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert ('- The verdict names its player ("Hold Christian Watson", "Start Christian Watson"), never a bare '
            '"Hold" or "Start".') in call[1]["content"]


def test_first_compare_verdict_gets_the_leaders(real_sample, model):
    script_compare(model)
    analyze(COMPARE)
    [call] = calls_for(model, analyst.VERDICT_PROMPT)
    prompt = call[1]["content"]
    assert "- PPR points per game: Jameson Williams 11.5 vs George Pickens 13.6: George Pickens leads." in prompt
    assert ("- PPR points per game in the later weeks: Jameson Williams 17.5 vs George Pickens 16.9: "
            "Jameson Williams leads.") in prompt
    assert "If one player leads on both, start him" in prompt
    assert "Positions (from the rosters): " in prompt and "George Pickens WR" in prompt


# --- smoke run fixes (25 October 2026): bye, matchup labels, wrong numbers, QB ---

ALLEN = "Should I start Josh Allen this week?"


def test_a_player_on_bye_gets_the_hard_rule_and_the_critic_blocks_a_start(real_sample, model):
    # Smoke run: "Start Josh Allen" against BAL, BUF's week 8 game; BUF has no week 7 game.
    from app.agents import critic

    script(model, classify("Josh Allen", "start_sit"), answer=verdict("Start Josh Allen", "He is the QB1."))
    result = analyze(ALLEN)
    assert [q.factor for q in result.queries if q.factor] == ["Player lookup", "Status", "Depth chart", "Next matchup"]
    [call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert "- He is on bye in week 7: Sit Josh Allen." in call[1]["content"]
    assert "Josh Allen is on bye in week 7: no game." in call[1]["content"]
    [issue] = [i for i in critic.check_answer(result) if i.check == "bye"]
    assert issue.blocking and issue.rule == "bye"
    assert issue.reason == 'Josh Allen is on bye in week 7: no game, so the verdict is "Sit Josh Allen".'


def test_a_reversed_matchup_label_in_a_factor_summary_is_replaced(real_sample, model):
    # Smoke question 9: "LA ... 31st of 32 ... the easiest matchup" was shown and approved.
    script(model, classify("Brock Bowers", "start_sit"), factors={
        "Next matchup": rating("strong", "Brock Bowers faces LA, which ranks 31st of 32 in points allowed to TEs, "
                                         "making it the easiest matchup for the position."),
    })
    result = analyze("Should I start Brock Bowers this week?")
    matchup = next(f for f in result.factors if f.factor == "Next matchup")
    assert matchup.rated_by == "rule-based" and "model summary replaced: 'easiest' does not fit" in matchup.rule
    [call] = calls_for(model, analyst.VERDICT_PROMPT)
    assert "Brock Bowers's week 7 opponent LA: rank 31 of 32, tough matchup" in call[1]["content"]


def test_a_factor_summary_with_a_number_not_in_its_rows_is_replaced(real_sample, model):
    # Smoke question 8: "100% of first-team reps" is in no row.
    script(model, classify("Josh Allen", "start_sit"), factors={
        "Depth chart": rating("strong", "Josh Allen is the undisputed QB1 with 100% of first-team reps."),
    })
    result = analyze(ALLEN)
    depth = next(f for f in result.factors if f.factor == "Depth chart")
    assert depth.rated_by == "rule-based" and "model summary replaced: 100 is not in the rows" in depth.rule
