"""Answer-correctness fixes from the QA sweep of 26 October 2026.

Each test runs the real pipeline on the committed sample data with no model (the rule-based
path a judge without credentials sees) and asserts the fixed behaviour.
"""

import pytest

from app import pipeline
from app.adapters import meterless


@pytest.fixture
def no_model(real_sample, model, monkeypatch, trace_dir):
    monkeypatch.delenv("METERLESS_BASE_URL", raising=False)

    def respond(messages):
        raise meterless.MeterlessError("down")
    model.respond = respond
    return model


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    return tmp_path / "memory"


def ask(question: str, **kwargs):
    return pipeline.answer(question, model_review=False, **kwargs)


# --- injuries: most teams' week 7 report has practice rows only, no game status yet ---


@pytest.mark.parametrize("question, player", [
    ("Is Deebo Samuel playing this week?", "Deebo Samuel Sr."),   # Out week 6 (hamstring), DNP week 7
    ("Is Rashee Rice playing this week?", "Rashee Rice"),
])
def test_out_last_week_and_not_practising_is_likely_out(no_model, question, player):
    run = ask(question)
    assert run.result.answer.startswith(f"No: {player} is likely out: listed Out for week 6 and did not practice "
                                        "for week 7 (hamstring).")
    assert run.approved and ".." not in run.result.answer


def test_not_practising_without_a_game_status_is_uncertain(no_model):
    # Before: "Yes: Tyler Warren has no game status ... (Did Not Participate In Practice)".
    answer = ask("Is Tyler Warren healthy?").result.answer
    assert answer.startswith("Uncertain: Tyler Warren has no game status yet for week 7, and did not practice.")


def test_a_likely_out_player_is_sat(no_model):
    answer = ask("Should I start Breece Hall this week?").result.answer  # Out weeks 5-6, DNP week 7
    assert answer.startswith("Sit Breece Hall.") and "is likely out" in answer


def test_a_player_listed_out_is_not_a_pickup(no_model):
    # Before: "Pick up Kyle Monangai ... his are n/a% and 15", ending with a Critic note.
    run = ask("Should I pick up Kyle Monangai?")
    assert run.result.answer.startswith("Hold off on Kyle Monangai.")
    assert "is listed Out for week 7 (thumb), so he can't help you this week" in run.result.answer
    assert run.approved and "n/a" not in run.result.answer


def test_the_stand_in_skips_a_player_who_is_likely_out(no_model):
    run = ask("Who becomes the Bucs' WR1 if Mike Evans is out?")
    assert run.result.answer.startswith(
        "Deebo Samuel is next at WR on the depth chart but is likely out: listed Out last week and did not "
        "practice this week; Brandin Cooks has the most recent target share of those who can play (7.2%), "
        "so for fantasy: pick up Brandin Cooks if available.")
    assert run.approved


# --- missing values: never "n/a" in a rule line ---


@pytest.mark.parametrize("question, snap", [
    ("Why is Luther Burden III scoring so many points?", "average snap share 60.5%"),  # "Luther Burden" in snap counts
    ("Why is DK Metcalf scoring so many points?", "average snap share 95.3%"),         # "D.K. Metcalf"
])
def test_snap_share_is_found_whatever_the_name_spelling(no_model, question, snap):
    answer = ask(question).result.answer
    assert snap in answer and "n/a" not in answer


@pytest.mark.parametrize("question, line", [
    # Low-target players fell off the Team usage list (LIMIT 12): "his are n/a% and n/a".
    ("Should I drop Kaleb Johnson?", "he has 0% recent target share, 4.7 carries per game and 1.7 PPR points per game."),
    ("Should I pick up Jordan James?", "he has"),
    # A QB is judged on his points, not target share ("his is n/a%").
    ("Should I pick up Josh Allen?", "Rule: pick up a QB at 12+ PPR points per game; he has 26.9 PPR points per game."),
    ("Should I start Odell Beckham Jr.?", "he has no games for MIN this season."),
    ("Should I pick up Hunter Luepke?", "he has 2.8% recent target share and 0.6 carries per game."),
])
def test_rule_lines_quote_only_values_the_data_has(no_model, question, line):
    run = ask(question)
    assert line in run.result.answer
    assert "n/a" not in run.result.answer and run.approved


# --- stand-ins ---


def test_a_player_already_on_reserve_still_gets_a_stand_in(no_model):
    # Hurts is fourth on PHI's chart, on reserve: nobody was "below" him, so "Hold until ...".
    run = ask("Jalen Hurts is out. Who replaces him?")
    assert run.result.answer.startswith("Tanner McKee is the top QB on the PHI depth chart without Jalen Hurts, "
                                        "so for fantasy: pick up Tanner McKee if available.")
    assert run.approved


def test_a_player_not_on_the_chart_is_not_said_to_have_players_below_him(no_model):
    answer = ask("Who replaces Odell Beckham Jr. if he's out?").result.answer
    assert answer.startswith("Justin Jefferson is the top WR on the MIN depth chart without Odell Beckham Jr.")
    assert "below Odell Beckham Jr." not in answer


@pytest.mark.parametrize("question", [
    "I dropped Deebo Samuel. Who becomes the 49ers' WR1 if Mike Evans is out?",
    "With Deebo Samuel on my bench, who replaces Mike Evans if he is out?",
    "Brandin Cooks is fine but who becomes the 49ers WR1 if Mike Evans is out?",
])
def test_the_replacement_is_for_the_player_who_is_out(no_model, question):
    # Before: the first-named player (Samuel or Cooks) was treated as the one out.
    run = ask(question)
    assert run.result.player.name == "Mike Evans"
    assert "so for fantasy: pick up Brandin Cooks if available" in run.result.answer


@pytest.mark.parametrize("question", [
    "Who becomes the 49ers' WR1 if Mike Evans and Brandin Cooks are out?",
    "Mike Evans is out and Brandin Cooks is out. Who becomes the 49ers WR1?",
])
def test_two_players_out_neither_is_the_pickup(no_model, question):
    answer = ask(question).result.answer
    assert "so for fantasy: pick up Jacob Cowing if available" in answer


# --- question reading ---


@pytest.mark.parametrize("question", [
    "Should I start Williams?",           # Kyren Williams (RB1); Savion Williams is a WR
    "Should I start Johnson this week?",
    "Aaron Jones is out. Who replaces him?",
    "Gunnar Helm is out. Who replaces him?",  # David Martin-Robinson (TE3), not Wan'Dale Robinson
])
def test_a_shared_surname_is_not_a_wrong_position_label(no_model, question):
    run = ask(question)
    assert run.approved and "Critic note" not in run.result.answer


@pytest.mark.parametrize("question", [
    "Should I start Malik Washington?", "Should I pick up DeeJay Dallas?", "Should I start KC Concepcion?",
    "Dallas Goedert is out, who replaces him?", "Darnell Washington or Dallas Goedert?",
])
def test_team_words_inside_a_name_are_not_a_premise(no_model, question):
    # Before: "not WAS" and the agents answered "Should I start Malik Dolphins?".
    run = ask(question)
    assert run.result.premise_correction is None and run.result.asked == question


def test_a_wrong_team_written_as_owner_is_corrected_even_if_it_is_the_opponent(no_model):
    run = ask("Should I start the Packers' Jahmyr Gibbs this week?")  # Gibbs is DET; GB is his week 7 opponent
    assert run.result.premise_correction == "Jahmyr Gibbs is on DET in the data (rosters, week 7), not GB."
    assert ask("Should I start Jahmyr Gibbs against the Packers?").result.premise_correction is None


@pytest.mark.parametrize("question", [
    "Is Jahmyr Gibbs a good play this week?", "Is Jahmyr Gibbs a smash play?", "Is Jared Goff worth playing in week 7?",
])
def test_a_good_play_is_a_start_question(no_model, question):
    assert ask(question).result.answer.startswith("Start ")


@pytest.mark.parametrize("question, start", [
    ("I have Jared Goff, Puka Nacua and Jahmyr Gibbs. Should I start Puka Nacua?", "Start Puka Nacua."),
    ("I have Jared Goff, Puka Nacua and Jahmyr Gibbs. Should I start Jared Goff?", "Start Jared Goff."),
    ("Jared Goff, Puka Nacua and Jahmyr Gibbs are on my team. Is Puka Nacua playing?", "Yes: Puka Nacua"),
])
def test_a_roster_list_is_not_a_choice(no_model, question, start):
    # Before: "Start Jahmyr Gibbs over Jared Goff and Puka Nacua".
    assert ask(question).result.answer.startswith(start)


def test_bare_surnames_share_the_position_of_the_unique_one(no_model):
    # The README's own example; before, "Williams" was Kyren Williams, an RB.
    assert ask("Williams or Pickens?").result.answer.startswith("Start George Pickens over Jameson Williams.")


# --- the server ---


def test_a_lone_surrogate_gets_a_reply(no_model):
    import threading
    import urllib.request

    import run as app_run
    srv = app_run.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for extra in ("", ', "user_id": "qa"'):
            body = ('{"question": "\\ud800 Should I start Jared Goff?"' + extra + "}").encode()
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/run", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:  # before: no reply, or a 500
                assert resp.status == 200 and "Jared Goff" in resp.read().decode()
    finally:
        srv.shutdown()
        srv.server_close()


def test_ui_port_flag_is_an_allowed_origin(monkeypatch):
    import run as app_run
    monkeypatch.delenv("UI_ORIGINS", raising=False)
    monkeypatch.delenv("UI_PORT", raising=False)
    monkeypatch.setattr(app_run, "SERVED_UI_PORT", 8380)  # what serve() sets from --ui-port
    assert "http://localhost:8380" in app_run.ui_origins()


# --- league memory ---


def test_parallel_runs_for_one_user_keep_every_fact(no_model, memory_dir):
    import threading

    questions = ["I have Jared Goff.", "I have Puka Nacua.", "I have Jahmyr Gibbs.", "I have Bijan Robinson."]
    threads = [threading.Thread(target=ask, args=(q,), kwargs={"user_id": "race"}) for q in questions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ctx = ask("Should I start Jared Goff?", user_id="race").result.user_context
    assert set(ctx.roster_names) == {"Jared Goff", "Puka Nacua", "Jahmyr Gibbs", "Bijan Robinson"}


def test_the_whole_roster_and_the_scoring_survive_a_long_memory(no_model, memory_dir):
    from app.agents import memory

    memory.store("long", "12-team half-PPR league.", "qa", miner_fn=None)
    names = ["Puka Nacua", "Jahmyr Gibbs", "Bijan Robinson", "Josh Allen", "George Kittle", "Davante Adams",
             "Brock Bowers", "Trey McBride", "Chris Olave", "Zay Flowers", "George Pickens", "Jameson Williams",
             "Jonathan Taylor", "Kyren Williams", "Sam LaPorta", "Christian Watson", "Bucky Irving", "Jared Goff"]
    memory.store("long", "I have " + ", ".join(names[:-1]) + " and " + names[-1] + ".", "qa", miner_fn=None)
    ctx = ask("Should I start Chris Olave?", user_id="long").result.user_context
    assert ctx.scoring == "half" and ctx.teams == 12
    assert len(ctx.roster) == len(names)  # before: the top 15 records only


# --- web UI (checked in a headless browser on 26 October; these pin the fixes) ---


def test_ui_script_handles_failures_and_sample_mode():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "app" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "Analyst could not answer" in js          # not "Analyst answer ready · undefined queries"
    assert "unreachable(run)" in js                  # the card no longer says RUNNING forever
    assert 'modelConfigured || c.status !== "error"' in js  # no wall of "error" timings without a model
    assert '"Sample data query"' in js               # sample mode does not claim Zetaris


# --- "why" factors ---


def test_a_qb_is_rated_on_his_passing(no_model):
    # Before: "0 targets ... average target share 0%" and "Not supported: Opportunity, Big plays".
    answer = ask("Why is Bryce Young scoring so many points?").result.answer
    assert "Opportunity (strong): 5 games, 40.2 pass attempts per game" in answer
    assert "1549 passing yards on 201 attempts (7.7 yards per attempt)" in answer
    assert "target share 0%" not in answer and "0 targets" not in answer


def test_matchups_rank_opponents_without_the_players_own_points(real_sample):
    from app.adapters.zetaris import run_sql
    from app.agents import factor_queries as fq

    question = "Jaxon Smith-Njigba"
    [jsn] = fq.parse_players(run_sql(fq.lookup_sql(fq.name_candidates(question), 2026))["data"], question)
    [q] = [q for q in fq.why_bundle(jsn, 2026) if q.factor == "Matchups"]
    result = run_sql(q.sql)
    t = fq._Rows(result["headers"], result["data"])
    ranks = dict(zip(t.text("opponent_team"), t.col("allowed_rank")))
    assert ranks["ARI"] > 10 and ranks["WAS"] > 10  # 10 and 8 with his 42.5 and 35.4 points counted


def test_an_absence_that_did_not_raise_his_usage_is_weak(no_model):
    answer = ask("Why is Isaiah Likely scoring so much?").result.answer
    assert "Teammate absences (strong)" not in answer


def test_counts_of_one_are_singular(no_model):
    answer = ask("Why is Christian Watson scoring so many fantasy points this season?").result.answer
    assert "(1 games)" not in answer and "1 losses" not in answer
