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


NOT_A_WR = ("George Kittle is not a WR below Mike Evans on the SF depth chart who can play; "
            "the stand-ins are Deebo Samuel, Brandin Cooks, Jacob Cowing.")


def with_depth_status(result, statuses):
    """Give the depth chart rows roster and injury-report columns: {name: (roster_status, report_status)}."""
    [depth] = [q for q in result.queries if q.factor == "Depth chart"]
    at = depth.headers.index("player_name")
    depth.headers = depth.headers + ["roster_status", "report_status"]
    depth.rows = [row + list(statuses.get(row[at], ("ACT", None))) for row in depth.rows]
    return result


def test_saved_samuel_verdict_passes_the_stand_in_check():
    # Samuel is a WR, next below Evans on the depth chart, and leads the WRs below him (11.1%).
    assert not issues(load_example(BUCS), "verdict_support")


def test_a_pick_who_is_not_a_wr_below_evans_is_blocked():
    # QA run, 26 Oct: Kittle (TE) was picked to replace Evans (WR) on target share.
    for answer in ("Pick up George Kittle. His 24.9% recent target share leads.",
                   "Pick up Christian McCaffrey. He has 22.8%."):
        [issue] = issues(with_answer(BUCS, answer), "verdict_support")
        assert issue.blocking and issue.rule == "pick"
        assert issue.reason == NOT_A_WR.replace("George Kittle", answer.split(".")[0].removeprefix("Pick up "))


@pytest.mark.parametrize("status, why", [(("RES", None), "reserve"), (("ACT", "Out"), "Out")])
def test_a_wr_who_cannot_play_is_not_a_stand_in(status, why):
    result = with_depth_status(with_answer(BUCS, "Start Deebo Samuel. The depth chart ranks him second."),
                               {"Deebo Samuel": status})
    [issue] = issues(result, "verdict_support")
    assert issue.blocking, why
    assert issue.reason == ("Deebo Samuel is not a WR below Mike Evans on the SF depth chart who can play; "
                            "the stand-ins are Brandin Cooks, Jacob Cowing, Jordan Watkins.")


def test_verdict_backed_by_the_numbers_passes():
    for answer in ("Pick up Deebo Samuel. His 11.1% recent target share leads the WRs below Evans.",
                   "Start Deebo Samuel. The depth chart ranks him second.",
                   # Other teammates may still be mentioned, as long as the pick is a WR below Evans.
                   "Pick up Deebo Samuel. George Kittle (24.9%) and Christian McCaffrey (22.8%) see more targets, "
                   "but neither plays WR."):
        assert not issues(with_answer(BUCS, answer), "verdict_support"), answer


def test_replacement_answer_shape_passes_check_a():
    # The literal answer (the depth chart's next WR) first, then the fantasy advice.
    result = with_answer(BUCS, (
        "Deebo Samuel is next at WR on the depth chart (11.1% recent target share), "
        "so for fantasy: pick up Deebo Samuel. The depth chart ranks him second."
    ))
    assert critic.verdict_sentence(result.answer) == "pick up Deebo Samuel."
    assert not issues(result, "verdict_support") and not issues(result, "question_fit")


def test_replacement_answer_shape_still_needs_a_stand_in():
    result = with_answer(BUCS, (
        "Deebo Samuel is next at WR on the depth chart, "
        "so for fantasy: pick up George Kittle."
    ))
    [issue] = issues(result, "verdict_support")
    assert issue.blocking and issue.reason == NOT_A_WR


def test_todays_live_samuel_answer_passes_the_stand_in_check():
    # Run 5630e3d22688 was blocked for trailing Kittle's target share; Kittle is a TE, so Samuel stands.
    result = load_example(BUCS, run="5630e3d22688")
    assert result.answer.startswith("Start Deebo Samuel.") and "Kittle 24.9%" in result.answer
    assert not issues(result, "verdict_support")


@pytest.mark.parametrize("answer", [
    "Pick up Jacob Cowing. He is a WR below Evans with a 3.7% recent target share.",
    "Add Jacob Cowing. He is a WR.",
])
def test_confident_action_under_half_the_top_share_is_blocked(answer):
    [issue] = issues(with_answer(BUCS, answer), "verdict_support")
    assert issue.blocking and issue.rule == "pick"
    assert issue.reason == ("Deebo Samuel has the most recent target share among the WRs below Mike Evans (11.1%), "
                            "against Jacob Cowing's 3.7%: recommend Deebo Samuel.")


def test_a_weaker_action_passes():
    assert not issues(with_answer(BUCS, "Stash Jacob Cowing. He is a WR."), "verdict_support")


@pytest.mark.parametrize("answer", [
    "Pick up Jacob Cowing. Deebo Samuel sees more targets.",  # naming the leader no longer excuses it
    "Pick up Brandin Cooks. He is a WR.",  # 7.2% trails Samuel's 11.1% by more than 0.5
])
def test_a_confident_pick_behind_the_leader_is_blocked(answer):
    [issue] = issues(with_answer(BUCS, answer), "verdict_support")
    assert issue.blocking and issue.reason.endswith("recommend Deebo Samuel.")


def _samuel_listed(status):
    result = with_answer(BUCS, "Pick up Jacob Cowing. Deebo Samuel is questionable for week 7 (hamstring).")
    depth = next(q for q in result.queries if q.factor == "Depth chart")
    depth.headers = [*depth.headers, "roster_status", "report_status"]
    depth.rows = [[*r, "ACT", status if "Samuel" in str(r) else None] for r in depth.rows]
    return result


def test_a_questionable_leader_said_so_excuses_the_pick():
    assert not issues(_samuel_listed("Questionable"), "verdict_support")
    # Not listed: the answer's claim does not excuse it.
    assert issues(_samuel_listed(None), "verdict_support")


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
    result.factors.append(Factor("Big plays", "strong", "He averaged 17.7 yards per target.", [], rated_by="model"))
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
    # Run 9e9b7541276e: both revisions ended "Verdict: hold." and the run was unresolved.
    ("why", "His 6 TDs account for 30.3% of PPR points, making Hold the recommended action. Verdict: hold."),
])
def test_verdict_must_name_a_player(question_type, answer):
    result = with_answer(WATSON, answer)
    result.question_type = question_type
    [issue] = [i for i in issues(result, "artifacts") if "names no player" in i.reason]
    assert issue.blocking and issue.rule == "named"
    action = critic._action(critic.verdict_sentence(answer))
    assert issue.reason.endswith(f'("{action.capitalize()} Christian Watson").')
    assert critic.as_rule(issue) == issue.reason  # the rule says what to write, not "Do not write 'hold.'"


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
    assert {i.check for i in found.blocking} == {"artifacts"}  # the saved answer's copied labels
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


# --- the ellipsis artifact, directions in the answer, and the review's facts and retry ---


def test_an_ellipsis_in_the_verdict_blocks():
    result = with_answer(BUCS, "Pick up George Kittle. ... His 24.9% recent target share leads.")
    [issue] = [i for i in issues(result, "artifacts") if i.where == "answer"]
    assert issue.blocking and issue.claim == "..." and "ellipsis" in issue.reason


def test_a_reversed_matchup_in_the_answer_blocks(compare_result):
    compare_result.answer = ("Start George Pickens over Jameson Williams. Pickens scores 13.6 PPR points per game "
                             "to Williams's 11.5, though Jameson Williams has the easier matchup against GB.")
    [issue] = issues(compare_result, "direction")
    assert issue.blocking and "it gives Jameson Williams the easier matchup" in issue.reason


def test_a_difference_of_two_cited_numbers_is_allowed(compare_result):
    compare_result.answer = ("Start George Pickens over Jameson Williams. Pickens scores 13.6 PPR points per game "
                             "to Williams's 11.5, a 2.1-point edge.")
    assert not issues(compare_result, "numbers")
    compare_result.answer = compare_result.answer.replace("2.1-point", "2.4-point")
    [issue] = issues(compare_result, "numbers")
    assert issue.reason.startswith("2.4 is not in the cited rows")


def test_review_gets_the_premise_as_applied_and_the_depth_chart_order(model):
    seen = []
    model.respond = lambda messages: seen.append(messages) or json.dumps({"issues": []})
    critic.critique(load_example(BUCS), 1, FAR_OFF)
    [messages] = seen
    assert "do not object that the data is for a different team" in messages[0]["content"]
    user = messages[1]["content"]
    assert "Premise check (already applied; the answer uses the team in the data, so this is not an issue): " \
           "Mike Evans is on SF in the data" in user
    assert "Depth chart: Mike Evans is WR1; if he is out, Deebo Samuel (WR2) is next at WR." in user


def test_a_review_with_no_json_is_retried_fresh_with_a_reminder(model, trace_dir):
    replies = ["The answer looks fine to me.", json.dumps({"issues": []})]
    model.respond = lambda messages: replies.pop(0)
    found = critic.critique(with_answer(WATSON, "His 22.2% target share explains it. Verdict: hold Christian Watson."),
                            1, FAR_OFF)
    assert found.reviewed_by == "model"
    first, retry = model.calls
    assert [m["role"] for m in retry] == ["system", "user"]  # the bad reply is not shown again
    assert retry[1]["content"] == first[1]["content"] + "\n\nReply with only the JSON object."
    [line] = [l for l in read_trace(trace_dir) if l["action"] == "parse_reply"]
    assert line["reply_head"] == "The answer looks fine to me."


def test_a_single_issue_object_is_read_as_one_issue(review):
    review.reply = json.dumps({"claim": "His 22.2% target share explains it", "reason": "It fell to 18.6%."})
    found = critic.critique(with_answer(WATSON, "His 22.2% target share explains it. Verdict: hold Christian Watson."),
                            1, FAR_OFF)
    assert found.reviewed_by == "model" and [i.check for i in found.blocking] == ["model_review"]


@pytest.mark.parametrize("reason, blocks", [
    # Reasons the reviewer gave in the 25 October runs, for claims it agreed with.
    ("The facts confirm the numbers: snap share 82% in weeks 1-3 vs 78.7% in weeks 4-6. The decline in "
     "opportunity and PPR points per game is correctly stated and well-supported.", False),  # 9e9b7541276e
    ("The facts state the depth chart has Mike Evans as WR1 and Deebo Samuel as WR2. Saying Deebo Samuel "
     "moves up to WR1 is correct based on depth chart order.", False),  # 3217c41a5e3f
    ("Saying Deebo Samuel moves up to WR1 is correct based on depth chart order. The 11.1% target share "
     "is not needed to validate the depth chart succession claim.", False),  # 6b5c3a81c4f9
    # Real objections, even with "accurate" in them.
    ("The claim is not well-supported because PPR points per game declined from 23.1 to 16.5. Touchdown "
     "efficiency is accurate.", True),  # 9e9b7541276e
    ("If Mike Evans is out, the next at WR is Deebo Samuel, not George Kittle.", True),
])
def test_a_review_issue_that_calls_the_claim_correct_is_a_note(review, reason, blocks):
    answer = "His 22.2% target share explains it. Verdict: hold Christian Watson."
    review.reply = json.dumps({"issues": [{"claim": "His 22.2% target share explains it", "reason": reason}]})
    [issue] = critic.critique(with_answer(WATSON, answer), 1, FAR_OFF).issues
    assert issue.check == "model_review" and issue.blocking is blocks


def test_hard_rule_tags_and_the_fallback_reason():
    result = with_answer(BUCS, "Start George Kittle. His 24.9% recent target share leads.")
    [issue] = issues(result, "verdict_support")
    assert issue.rule == "pick"
    roster = critic.Issue("user_context", "answer", "pick up George Kittle.",
                          "George Kittle is already on the user's roster; recommend a player who is not.")
    roster.rule = critic._hard_rule(roster)
    label = critic.Issue("artifacts", "answer", "[strong]", "'[strong]' is a support label copied from the prompt.")
    label.rule = critic._hard_rule(label)
    assert (roster.rule, label.rule) == ("rostered", None)  # a copied label is not a hard rule
    one = critic.Critique(1, "", [roster], "rule-based")
    two = critic.Critique(2, "", [roster, label], "rule-based")
    assert critic.fallback_reason([one, two]) == "the model recommended a player already on the user's roster twice"
    assert critic.fallback_reason([critic.Critique(1, "", [label], "rule-based"), two]) == \
        "the model recommended a player already on the user's roster after a revision"
    assert critic.fallback_reason([one, critic.Critique(2, "", [label], "rule-based")]) is None


def test_issues_become_rules_without_the_old_answer():
    label = critic.Issue("artifacts", "answer", "[strong]", "'[strong]' is a support label copied from the prompt.")
    assert critic.as_rule(label) == "Do not write '[strong]': a support label copied from the prompt."
    support = critic.Issue("verdict_support", "answer", "Start Deebo Samuel.", "Samuel trails Kittle.")
    assert critic.as_rule(support) == "Samuel trails Kittle."


def test_a_why_answer_may_put_its_numbers_in_the_second_sentence():
    # Smoke question 4 was unresolved after 3 rounds on this opening.
    result = with_answer(WATSON, "Watson's scoring is driven by big plays and touchdowns. His 22.2% target share "
                                 "and 6 touchdowns explain it. Verdict: hold Christian Watson.")
    assert not issues(result, "question_fit")
    late = with_answer(WATSON, "Watson's scoring is driven by big plays. Touchdowns help too. His 22.2% share. "
                               "Verdict: hold Christian Watson.")
    assert "open with the explanation and its numbers" in issues(late, "question_fit")[0].reason


@pytest.mark.parametrize("verdict, name", [
    # Smoke run: both blocked as "Deebo Samuel Sr. Deebo Samuel Sr has no recent target share".
    ("Hold Deebo Samuel Sr. Deebo Samuel Sr. faces ATL in week 7.", "Deebo Samuel Sr"),
    ("Hold off on Deebo Samuel Sr. Most supported by the data: Depth chart (strong).", "Deebo Samuel Sr"),
    ("Start Brock Bowers over Trey McBride.", "Brock Bowers"),
    ("Start Marvin Harrison Jr.", "Marvin Harrison Jr"),
])
def test_a_suffix_ends_the_recommended_name(verdict, name):
    assert critic.recommended_name(verdict) == name
