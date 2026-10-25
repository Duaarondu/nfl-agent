"""The Critic's code checks and model review, run on the two saved example runs."""

import json

import pytest
from helpers import load_example, read_trace

from app.adapters import meterless
from app.agents import critic
from app.agents.analyst import Factor

WATSON = "why-is-christian-watson"
BUCS = "who-becomes-the-bucs"
FAR_OFF = 1e12  # a deadline that never runs out


def issues(result, check=None):
    return [i for i in critic.check_answer(result) if check is None or i.check == check]


def with_answer(slug, answer):
    result = load_example(slug)
    result.answer = answer
    return result


# --- a) verdict support ---


def test_samuel_verdict_is_flagged_by_target_share():
    [issue] = issues(load_example(BUCS), "verdict_support")
    assert issue.blocking and issue.claim == "Start Deebo Samuel."
    assert issue.reason.startswith(
        "Deebo Samuel Sr.'s recent target share (11.1%) trails George Kittle (TE) 24.9% "
        "and Christian McCaffrey (RB) 22.8%, and is less than half of George Kittle's."
    )


def test_verdict_backed_by_the_numbers_passes():
    assert not issues(with_answer(BUCS, "Pick up George Kittle. His 24.9% recent target share leads."), "verdict_support")
    # The depth chart may still be mentioned, as long as the pick follows the usage numbers.
    depth_noted = with_answer(BUCS, (
        "Pick up George Kittle. Deebo Samuel is next at WR on the depth chart, but Kittle (24.9%) "
        "and Christian McCaffrey (22.8%) get far more targets than his 11.1%."
    ))
    assert not issues(depth_noted, "verdict_support")


def test_replacement_answer_shape_passes_check_a():
    # The literal answer (the depth chart's next WR) first, then the pick the target share backs.
    result = with_answer(BUCS, (
        "Deebo Samuel is next at WR on the depth chart, but the target share points to George Kittle (24.9%), "
        "so for fantasy: pick up George Kittle. He has the top recent target share among his teammates."
    ))
    assert critic.verdict_sentence(result.answer) == "pick up George Kittle."
    assert not issues(result, "verdict_support") and not issues(result, "question_fit")


def test_replacement_answer_shape_still_follows_the_usage_numbers():
    result = with_answer(BUCS, (
        "Deebo Samuel is next at WR on the depth chart (11.1% recent target share), "
        "so for fantasy: pick up Deebo Samuel."
    ))
    [issue] = issues(result, "verdict_support")
    assert issue.blocking and "less than half of George Kittle's" in issue.reason


def test_todays_live_samuel_answer_is_blocked_even_though_it_names_kittle():
    # Run 5630e3d22688: the critic approved this in round 2 before check (a) was tightened.
    result = load_example(BUCS, run="5630e3d22688")
    assert result.answer.startswith("Start Deebo Samuel.") and "Kittle 24.9%" in result.answer
    [issue] = issues(result, "verdict_support")
    assert issue.blocking
    assert "and is less than half of George Kittle's. A 'Start' must follow the usage numbers" in issue.reason


@pytest.mark.parametrize("answer", [
    # Samuel is named with Kittle and McCaffrey: mentioning them no longer saves a confident action.
    "Pick up Deebo Samuel. He is next on the WR depth chart, though George Kittle (24.9%) "
    "and Christian McCaffrey (22.8%) see more targets than his 11.1%.",
    "Add Deebo Samuel. Kittle and McCaffrey see more targets.",
])
def test_confident_action_under_half_the_top_share_is_blocked(answer):
    [issue] = issues(with_answer(BUCS, answer), "verdict_support")
    assert issue.blocking and "less than half of George Kittle's" in issue.reason


def test_weaker_action_or_closer_share_only_needs_the_teammates_named():
    # Stash is not a confident action; McCaffrey's 22.8% is more than half of Kittle's 24.9%.
    for answer in (
        "Stash Deebo Samuel. Kittle (24.9%) and McCaffrey (22.8%) get more targets; he is next on the depth chart.",
        "Pick up Christian McCaffrey. Kittle's 24.9% is close to his 22.8%.",
    ):
        assert not issues(with_answer(BUCS, answer), "verdict_support"), answer
    [issue] = issues(with_answer(BUCS, "Pick up Christian McCaffrey. He has 22.8%."), "verdict_support")
    assert "trails George Kittle (TE) 24.9%. The answer must explain why" in issue.reason


def test_why_verdict_about_the_player_himself_is_not_compared():
    assert not issues(load_example(WATSON), "verdict_support")


# --- b) numbers ---


def test_saved_answers_use_only_numbers_from_the_data():
    for slug in (WATSON, BUCS):
        assert not [i for i in issues(load_example(slug), "numbers") if i.where == "answer"], slug


def test_a_number_not_in_the_data_blocks():
    result = load_example(WATSON)
    result.answer = result.answer.replace("average target share 22.2%", "average target share 22.7%")
    [issue] = [i for i in issues(result, "numbers") if i.where == "answer"]
    assert issue.blocking and issue.reason.startswith("22.7 is not in the cited rows")


def test_a_bad_number_in_a_model_factor_summary_is_recorded_without_blocking():
    result = load_example(WATSON)
    result.factors.append(Factor("Big plays", "strong", "He averaged 12.6 yards per target.", [], rated_by="model"))
    [issue] = issues(result, "numbers")
    assert issue.where == "factor:Big plays" and not issue.blocking


# --- c) artifacts ---


def test_leaked_labels_block_and_decimal_counts_in_summaries_are_recorded():
    found = issues(load_example(BUCS), "artifacts")
    assert [(i.claim, i.where, i.blocking) for i in found] == [
        ("[strong]", "answer", True),
        ("[not supported]", "answer", True),
        ("0.0 games", "factor:Games without the player", False),
    ]


def test_decimal_count_in_the_answer_blocks():
    found = issues(with_answer(BUCS, "Pick up George Kittle. Mike Evans has missed 0.0 games."), "artifacts")
    [issue] = [i for i in found if i.where == "answer"]
    assert issue.blocking and issue.reason == "'0.0 games' is a count written with a decimal."


# --- d) question fit ---


def test_why_answer_that_opens_with_the_action_is_flagged():
    [issue] = issues(load_example(WATSON), "question_fit")
    assert issue.blocking and "needs the explanation first" in issue.reason


def test_why_answer_with_the_explanation_first_passes():
    result = with_answer(WATSON, "His 22.2% target share and 6 touchdowns explain it. Verdict: hold Christian Watson.")
    assert not issues(result, "question_fit")


@pytest.mark.parametrize("question_type, answer", [
    # Live CLI run 93e85a819afd (2026-10-25): the model wrote the action with no player.
    ("why", "He averages 22.2% target share and 19.8 PPR points per game. Verdict: start."),
    ("why", "His 6 touchdowns explain it. Verdict: Hold"),
    ("start_sit", "Start. He averages 19.8 PPR points per game."),
    ("waiver", "Pick up. His target share is 22.2%."),
])
def test_verdict_must_name_a_player(question_type, answer):
    result = with_answer(WATSON, answer)
    result.question_type = question_type
    [issue] = issues(result, "question_fit")
    assert issue.blocking and "names no player" in issue.reason


C2 = "Should I pick up a 49ers receiver if Evans misses time?"


@pytest.mark.parametrize("question_type", ["waiver", "start_sit", "replacement"])
@pytest.mark.parametrize("verdict", ["Pick up Mike Evans", "Start Mike Evans"])
def test_verdict_never_picks_up_or_starts_the_player_who_is_out(question_type, verdict):
    # Run 994c234341e5 answered the c2 question with "Pick up Mike Evans" and was approved.
    result = with_answer(BUCS, f"{verdict}. Mike Evans leads 49ers targets at 27.1%.")
    result.question, result.question_type = C2, question_type
    [issue] = issues(result, "question_fit")
    assert issue.blocking and "Mike Evans, the player who is out" in issue.reason


def test_out_check_needs_the_question_to_say_he_is_out():
    result = with_answer(BUCS, "Pick up Mike Evans. He leads 49ers targets at 27.1%.")
    result.question, result.question_type = "Should I pick up Mike Evans?", "waiver"
    assert not issues(result, "question_fit")


def test_named_verdicts_pass_the_name_check():
    for answer in ("His 6 touchdowns explain it. Verdict: start Christian Watson.",
                   "His 6 touchdowns explain it. Verdict: hold Watson."):
        assert not issues(with_answer(WATSON, answer), "question_fit")


@pytest.mark.parametrize("answer, problem", [
    ("Hold Mike Evans. He is only questionable.", "the player who is out"),
    ("Hold until SF's next depth chart. No data.", "names no player"),
])
def test_replacement_answer_must_name_a_stand_in(answer, problem):
    [issue] = issues(with_answer(BUCS, answer), "question_fit")
    assert problem in issue.reason


def test_start_sit_answer_must_open_with_start_or_sit():
    result = with_answer(WATSON, "Pick up Christian Watson. He has a 22.2% target share.")
    result.question_type = "start_sit"
    [issue] = issues(result, "question_fit")
    assert "Start, Sit, Bench" in issue.reason


# --- e) timing ---


def test_change_claimed_after_an_injury_must_start_that_week():
    # Jayden Reed was out in week 3; Watson's target share was higher before that (20.0, 37.9).
    result = with_answer(WATSON, "His target share rose after Jayden Reed went out. Verdict: hold Christian Watson.")
    [issue] = issues(result, "timing")
    assert issue.blocking
    assert issue.reason.startswith("His target share averaged 28.9% before week 3 and 18.9% from week 3 on") and "so it did not rise after Jayden Reed was first out in week 3" in issue.reason


def test_change_that_was_already_there_before_the_event_is_flagged():
    # Chris Brooks was out from week 5; Watson's yards per target was already 15.7 in week 4.
    result = with_answer(WATSON, "His yards per target jumped after Brooks went out. Verdict: hold Christian Watson.")
    [issue] = issues(result, "timing")
    assert issue.reason.startswith("The rise in his yards per target started before Brooks was first out in week 5")


def test_rising_claim_in_another_clause_is_not_read_against_a_fall():
    # Run c86443db3074, round 1: "fell ... starting in week 4" in the Opportunity clause made the
    # whole sentence a fall, tested on yards per target, which the Big plays clause says
    # (correctly) was rising: "averaged 10.6 before week 4 and 13.9 from week 4 on".
    result = load_example(WATSON, run="c86443db3074")
    result.answer = (
        "Most supported by the data: Opportunity (strong): Christian Watson's 80.3% average snap share and "
        "22.2% average target share over 6 games yield 19.8 PPR points per game, with 23.1 PPR in weeks 1-3 "
        "vs 16.5 in weeks 4-6, but snap share fell from 82% to 78.7% and target share from 25.8% to 18.6% "
        "starting in week 4; Big plays (strong): Christian Watson's 10 20+-yard plays, 32.4% air yards share, "
        "and yards per target rising from 10.6 to 13.9 strongly drive his fantasy production; Touchdowns and "
        "red zone (strong): Christian Watson's 6 touchdowns produce 36 of 118.8 PPR points (30.3%), and 7 of "
        "35 team red-zone targets (20%) go to him without red-zone carries. Not supported: Teammate absences. "
        "Verdict: hold Christian Watson."
    )
    assert not issues(result, "timing")


@pytest.mark.parametrize("claim, problem", [
    # Same live run, but these claims contradict the rows, so they still block.
    ("His yards per target started falling from week 4.", "so it did not fall after week 4"),
    ("His target share was rising starting in week 4.", "so it did not rise after week 4"),
])
def test_wrong_direction_still_blocks_with_the_new_verb_forms(claim, problem):
    result = load_example(WATSON, run="c86443db3074")
    result.answer = f"{claim} Verdict: hold Christian Watson."
    [issue] = issues(result, "timing")
    assert issue.blocking and problem in issue.reason


@pytest.mark.parametrize("claim", [
    "His target share fell after Jayden Reed went out.",  # 28.9 before week 3, 18.9 from week 3 on
    "His PPR points rose since week 5.",  # 19.3 before, 20.9 from week 5 (week 4 was 7.7)
])
def test_timing_that_holds_up_passes(claim):
    assert not issues(with_answer(WATSON, f"{claim} Verdict: hold Christian Watson."), "timing")


def test_injury_the_data_does_not_show_is_flagged():
    result = with_answer(WATSON, "His targets rose after Romeo Doubs got hurt. Verdict: hold Christian Watson.")
    [issue] = issues(result, "timing")
    assert issue.reason == "The injury reports in the data have no Out or Doubtful entry for Romeo Doubs."


# --- the model review and the critique ---


@pytest.fixture
def review(model):
    """Script the critic's review call: set review.reply to text or an Exception."""
    class Review:
        reply = json.dumps({"issues": []})

    def respond(messages):
        assert messages[0]["content"] == critic.REVIEW_PROMPT
        return Review.reply

    model.respond = respond
    return Review


def test_approved_answer_traces_approved(review, trace_dir):
    result = with_answer(WATSON, "His 22.2% target share explains it. Verdict: hold Christian Watson.")
    found = critic.critique(result, 1, FAR_OFF)
    assert (found.status, found.reviewed_by, found.blocking) == ("approved", "model", [])
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "critique"]
    assert (line["agent_name"], line["status"], line["round"], line["target_agent"]) == ("critic", "approved", 1, None)


def test_model_issue_blocks_only_when_it_quotes_the_answer(review, trace_dir):
    result = with_answer(WATSON, "His 22.2% target share explains it. Verdict: hold Christian Watson.")
    review.reply = json.dumps({"issues": [
        {"claim": "His 22.2% target share explains it", "reason": "Target share fell to 18.6% in weeks 4-6."},
        {"claim": "words that are not in the answer", "reason": "x"},
    ]})
    found = critic.critique(result, 1, FAR_OFF)
    assert [(i.check, i.blocking) for i in found.issues] == [("model_review", True), ("model_review", False)]
    assert found.status == "needs_revision"
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "critique"]
    assert (line["status"], line["target_agent"], line["blocking"]) == ("needs_revision", "analyst", 1)


def test_model_issues_block_only_in_round_one_but_code_checks_block_in_every_round(review):
    review.reply = json.dumps({"issues": [
        {"claim": "His 22.2% target share explains it", "reason": "Target share fell to 18.6% in weeks 4-6."},
    ]})
    result = with_answer(WATSON, "His 22.2% target share explains it. Verdict: hold Christian Watson.")
    assert critic.critique(result, 1, FAR_OFF).status == "needs_revision"
    later = critic.critique(result, 2, FAR_OFF)
    assert later.status == "approved" and [(i.check, i.blocking) for i in later.issues] == [("model_review", False)]

    result.answer = "His 22.2% target share and 99.9 yards explain it. Verdict: hold Christian Watson."
    third = critic.critique(result, 3, FAR_OFF)
    assert third.status == "needs_revision" and [i.check for i in third.blocking] == ["numbers"]


@pytest.mark.parametrize("failure", [meterless.MeterlessError("down"), "not json"])
def test_failed_review_falls_back_to_the_code_checks(review, trace_dir, failure):
    review.reply = failure
    found = critic.critique(load_example(BUCS), 1, FAR_OFF)
    assert found.reviewed_by == "rule-based"
    assert {i.check for i in found.blocking} == {"verdict_support", "artifacts"}
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "review"]
    assert (line["agent_name"], line["status"], line["reviewed_by"]) == ("critic", "fallback", "rule-based")


def test_review_is_skipped_when_the_time_is_up(review):
    found = critic.critique(load_example(BUCS), 1, deadline=0)
    assert found.reviewed_by == "rule-based" and found.status == "needs_revision"


def test_review_can_be_turned_off(model):
    found = critic.critique(load_example(WATSON), 1, FAR_OFF, model_review=False)
    assert found.reviewed_by == "rule-based" and not model.calls


# --- g) compare: start exactly one of the two, as the head-to-head numbers say ---

COMPARE = ("I have Jameson Williams on my bench and George Pickens in my starting lineup, "
           "who should I pick?")


@pytest.fixture
def compare_result(real_sample, monkeypatch):
    """The compare question answered on the sample slice, with every model call failing (rule-based)."""
    from app.agents import analyst

    def down(*args, **kwargs):
        raise meterless.MeterlessError("off")

    monkeypatch.setattr(analyst.meterless, "chat", down)
    return analyst.analyze(COMPARE)


def test_rule_based_compare_answer_passes_every_check(compare_result):
    assert compare_result.answer.startswith("Start George Pickens over Jameson Williams")
    assert not [i for i in critic.check_answer(compare_result) if i.blocking]


@pytest.mark.parametrize("answer", [
    "Start both. Pickens has 13.6 PPR points per game and Williams 11.5.",
    "Start Mike Evans over George Pickens. Pickens has 13.6 and Williams 11.5 PPR points per game.",
    "Sit Jameson Williams. Pickens has 13.6 and Williams 11.5 PPR points per game.",
    "Start George Pickens and start Williams too. Pickens has 13.6 and Williams 11.5 PPR points per game.",
])
def test_compare_verdict_must_start_exactly_one_of_the_two(compare_result, answer):
    compare_result.answer = answer
    assert [i for i in issues(compare_result, "compare") if i.blocking]


def test_compare_pick_behind_on_points_needs_the_trend_explained(compare_result):
    compare_result.answer = ("Start Jameson Williams over George Pickens. Williams scores 11.5 PPR points "
                             "per game to Pickens' 13.6.")
    [issue] = issues(compare_result, "compare")
    assert "say why Jameson Williams anyway" in issue.reason and "17.5 to 16.9" in issue.reason
    compare_result.answer = ("Start Jameson Williams over George Pickens. Pickens has more points per game "
                             "(13.6 to 11.5), but from week 4 on Williams scores 17.5 to Pickens' 16.9, "
                             "so the recent trend favours Williams.")
    assert not issues(compare_result, "compare")


def test_compare_pick_behind_on_points_and_trend_is_blocked(compare_result):
    trend = next(q for q in compare_result.queries if q.factor == "Recent trend")
    col, who = trend.headers.index("late_ppr_per_game"), trend.headers.index("player")
    for row in trend.rows:
        if row[who] == "Jameson Williams":
            row[col] = 12.0
    compare_result.answer = ("Start Jameson Williams over George Pickens. Williams' recent trend: 12 "
                             "points per game to Pickens' 13.6.")
    [issue] = issues(compare_result, "compare")
    assert issue.reason.startswith("The head-to-head numbers favour George Pickens")


def test_compare_answer_quotes_numbers_for_both_players(compare_result):
    compare_result.answer = "Start George Pickens over Jameson Williams. Pickens scores 13.6 PPR points per game."
    [issue] = issues(compare_result, "compare")
    assert "Quote a number for Jameson Williams" in issue.reason


def test_compare_skips_the_single_player_verdict_support_check(compare_result):
    compare_result.answer = ("Start Jameson Williams over George Pickens. Pickens has more points per game "
                             "(13.6 to 11.5), but recently Williams scores 17.5 to 16.9.")
    assert not issues(compare_result, "verdict_support")
    assert not issues(compare_result, "question_fit")


# --- percentages need their % sign ---


@pytest.mark.parametrize("text, flagged", [
    ("He has a 13.8 target share.", True),
    ("His 13.8 recent target share leads.", True),
    ("His target share of 13.8 leads.", True),
    ("A snap share at 84 is high.", True),
    ("He has a 13.8% target share.", False),
    ("His target share of 13.8% leads.", False),
    ("His 13.8 percent target share leads.", False),
    ("His target share rose in week 4.", False),
])
def test_percentages_without_a_percent_sign_are_artifacts(text, flagged):
    found = [what for _, what in critic._artifacts(text)]
    assert ("a percentage without its % sign" in found) is flagged


# --- h) no recommendation without data; i) position labels ---

UI_QUESTION = "Who should I start Trey Mcbride or Bowers for week 7"


@pytest.fixture
def mcbride_start_sit(real_sample, monkeypatch):
    """McBride alone, as the live UI run answered it (Bowers never looked up)."""
    from app.agents import analyst

    def respond(messages, **kwargs):
        system = messages[0]["content"]
        if system == analyst.CLASSIFY_PROMPT:
            return {"choices": [{"message": {"content": '{"player_name": "Trey McBride", "question_type": "start_sit"}'}}]}
        raise meterless.MeterlessError("off")

    monkeypatch.setattr(analyst.meterless, "chat", respond)
    return analyst.analyze("Should I start Trey McBride this week?")


def test_a_verdict_naming_a_player_with_no_rows_is_blocked(mcbride_start_sit):
    mcbride_start_sit.answer = "Start Trey McBride over Bowers. McBride has a 24.1% target share."
    [issue] = issues(mcbride_start_sit, "no_data")
    assert issue.blocking and issue.reason.startswith("Bowers has no rows in the data")
    assert "say Bowers couldn't be found instead of picking a winner" in issue.reason


def test_players_with_rows_pass_the_no_data_check(mcbride_start_sit, compare_result):
    mcbride_start_sit.answer = "Start Trey McBride. He has a 24.1% target share."
    assert not issues(mcbride_start_sit, "no_data")
    assert not issues(compare_result, "no_data")  # Pickens and Williams both have rows


def test_wrong_position_label_in_the_answer_blocks(mcbride_start_sit):
    mcbride_start_sit.answer = "Start Trey McBride. He is the Cardinals' clear WR1 with a 24.1% target share."
    assert not issues(mcbride_start_sit, "position_label")  # "He": no name to pin the label on
    mcbride_start_sit.answer = "Start Trey McBride. McBride is the Cardinals' WR1 with a 24.1% target share."
    [issue] = issues(mcbride_start_sit, "position_label")
    assert issue.blocking and issue.reason == "'WR1' is wrong for Trey McBride, who is a TE."
    mcbride_start_sit.answer = "Start Trey McBride. McBride is the Cardinals' TE1 with a 24.1% target share."
    assert not issues(mcbride_start_sit, "position_label")


def test_wrong_position_label_in_a_model_factor_summary_is_recorded(mcbride_start_sit):
    mcbride_start_sit.factors.append(Factor("Depth chart", "strong", "Trey McBride is the WR1.", [], rated_by="model"))
    [issue] = issues(mcbride_start_sit, "position_label")
    assert not issue.blocking and issue.where == "factor:Depth chart"


def test_saved_examples_pass_the_new_checks():
    for slug in (WATSON, BUCS, "i-have-jameson-williams", "12-team-half-ppr", "should-i-pick-up"):
        result = load_example(slug)
        assert not [i for i in critic.check_answer(result) if i.check in ("no_data", "position_label") and i.blocking], slug
