"""End-to-end pipeline behaviour, driven through the CLI with a scripted engine."""
from flowpipe.engines import EngineSpec, build_argv

CLEAR = {"do": "check", "verdict": "CLEAR"}
BLOCKED = {"do": "check", "verdict": "BLOCKED"}
APPROVE_SHIP = ["/approve", "/approve"]        # ship_gate, then ship_review


def test_happy_path_runs_build_check_ship(pipe):
    pipe.script(build=[{"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run(APPROVE_SHIP)

    assert pipe.commands_run() == ["build", "check", "ship"]
    assert pipe.gates == ["SHIP_GATE", "SHIP_REVIEW"]
    assert "COMMIT MESSAGE: feat: something" in pipe.output
    assert "Pipeline finished" in pipe.output


def test_ship_is_told_the_suite_result_flowpipe_verified(pipe):
    # Seen live: the ship session could not run the suite itself and wrote
    # "the tests have never been run" for an MR, although flowpipe had run them green.
    pipe.script(build=[{"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run(APPROVE_SHIP)

    ship = [c for c in pipe.calls if c["command"] == "ship"][0]
    assert "passed on exactly this working tree" in ship["prompt"]
    assert "check verdict: CLEAR" in ship["prompt"]


def test_build_that_makes_partial_progress_is_dispatched_again(pipe):
    pipe.script(build=[{"do": "tick_one"}, {"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run(APPROVE_SHIP)

    assert pipe.commands_run() == ["build", "build", "check", "ship"]
    assert pipe.gates == ["SHIP_GATE", "SHIP_REVIEW"]


def test_build_that_ends_with_a_question_stops_for_the_operator(pipe):
    # Seen in real runs: the engine exits 0 after asking "How would you like to
    # proceed?" with no plan progress. Re-dispatching it blindly burns cycles.
    pipe.script(build=[{"do": "ask"}, {"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run(["take option B", *APPROVE_SHIP])

    assert pipe.gates == ["STALL_GATE", "SHIP_GATE", "SHIP_REVIEW"]
    assert "How would you like to proceed?" in pipe.output      # the operator sees the question
    builds = [c for c in pipe.calls if c["command"] == "build"]
    assert len(builds) == 2
    assert "take option B" in builds[1]["prompt"]                # and the answer reaches the engine


def test_check_that_writes_no_report_is_not_read_from_a_stale_one(pipe):
    # A check.md left by an earlier run must never stand in for this run's check.
    (pipe.work / "check.md").write_text("---\nverdict: CLEAR\nce_review: RUN\n---\n", encoding="utf-8")
    pipe.script(build=[{"do": "tick"}], check=[{"do": "ask"}])
    pipe.run([])

    assert pipe.gates == ["STALL_GATE"]
    assert "check" in pipe.output.split("PHASE: STALL_GATE")[1]


def test_qa_that_writes_no_report_does_not_count_as_passed(pipe):
    pipe.script(build=[{"do": "tick"}], check=[{**CLEAR, "ui": True}], qa=[{"do": "ask"}])
    pipe.run([])

    assert pipe.commands_run() == ["build", "check", "qa"]
    assert pipe.gates == ["STALL_GATE"]


def test_human_triage_sends_accepted_findings_through_fix_and_recheck(pipe):
    pipe.script(build=[{"do": "tick"}], check=[BLOCKED, CLEAR], fix=[{"do": "fixall"}], ship=[{"do": "ship"}])
    pipe.run(["fix the injection in app.py", *APPROVE_SHIP])

    assert pipe.gates == ["TRIAGE", "SHIP_GATE", "SHIP_REVIEW"]
    assert pipe.commands_run() == ["build", "check", "fix", "check", "ship"]
    assert "fix the injection in app.py" in (pipe.work / "fixlist.md").read_text(encoding="utf-8")


def test_fix_that_resolves_nothing_stops_for_the_operator(pipe):
    pipe.script(build=[{"do": "tick"}], check=[BLOCKED], fix=[{"do": "ask"}])
    pipe.run(["fix the injection in app.py"])

    assert pipe.gates == ["TRIAGE", "STALL_GATE"]
    assert pipe.commands_run() == ["build", "check", "fix"]


def test_auto_triage_fixes_blocking_findings_without_asking(pipe):
    pipe.configure(triage_policy="auto")
    pipe.script(build=[{"do": "tick"}], check=[BLOCKED, CLEAR], fix=[{"do": "fixall"}], ship=[{"do": "ship"}])
    pipe.run(APPROVE_SHIP)

    assert pipe.gates == ["SHIP_GATE", "SHIP_REVIEW"]
    assert pipe.commands_run() == ["build", "check", "fix", "check", "ship"]


def test_auto_triage_still_asks_when_the_required_review_was_skipped(pipe):
    # Nothing in a fix list can make a skipped review have happened.
    pipe.configure(triage_policy="auto", require_ce_review=True)
    pipe.script(build=[{"do": "tick"}], check=[{**CLEAR, "ce": "SKIPPED"}])
    pipe.run([])

    assert pipe.gates == ["TRIAGE"]


def test_waiving_check_findings_does_not_skip_qa(pipe):
    pipe.script(build=[{"do": "tick"}], check=[{**BLOCKED, "ui": True}], qa=[{"do": "qa"}], ship=[{"do": "ship"}])
    pipe.run(["/waive", *APPROVE_SHIP])

    assert pipe.commands_run() == ["build", "check", "qa", "ship"]
    assert pipe.gates == ["TRIAGE", "SHIP_GATE", "SHIP_REVIEW"]


def test_engine_failure_ends_cleanly_with_a_resume_hint(pipe):
    pipe.script(build=[{"do": "fail"}])
    pipe.run([])

    assert pipe.exit_code == 1
    assert "engine exploded" in pipe.output
    assert "flowpipe resume t1" in pipe.output


def test_resume_after_engine_failure_reruns_the_failed_phase(pipe):
    pipe.script(build=[{"do": "fail"}, {"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run([])
    pipe.resume(APPROVE_SHIP)

    assert pipe.exit_code == 0
    assert pipe.commands_run() == ["build", "build", "check", "ship"]


def test_resume_returns_to_the_gate_that_was_waiting(pipe):
    pipe.script(build=[{"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run([])                                   # detach at the ship gate
    assert pipe.gates == ["SHIP_GATE"]
    pipe.resume(APPROVE_SHIP)

    assert pipe.gates == ["SHIP_GATE", "SHIP_REVIEW"]
    assert pipe.commands_run() == ["build", "check", "ship"]   # nothing ran twice


def test_engine_that_hangs_is_killed_at_its_timeout(pipe):
    pipe.configure_engine(timeout=2)
    pipe.script(build=[{"do": "hang"}])
    pipe.run([])

    assert pipe.exit_code == 1
    assert "timed out after 2s" in pipe.output


def test_stopping_at_a_gate_ends_the_run_as_stopped(pipe):
    pipe.script(build=[{"do": "tick"}], check=[BLOCKED])
    pipe.run(["/stop"])

    assert pipe.exit_code == 1
    assert "Stopped: stopped at triage" in pipe.output


def test_red_suite_after_build_goes_to_fix_without_asking(pipe):
    pipe.script(build=[{"do": "tick_and_break"}], fix=[{"do": "fixall"}], check=[CLEAR], ship=[{"do": "ship"}])
    pipe.run(APPROVE_SHIP)

    assert pipe.commands_run() == ["build", "fix", "check", "ship"]
    assert pipe.gates == ["SHIP_GATE", "SHIP_REVIEW"]


def test_answers_piped_to_flowpipe_reach_the_gates_not_the_engine(pipe, tmp_path):
    # Seen in a live run: `claude -p` inherited flowpipe's stdin and swallowed
    # the piped gate answers, so the ship gate read EOF and detached.
    import os
    import subprocess
    import sys

    pipe.script(build=[{"do": "tick"}], check=[CLEAR], ship=[{"do": "ship"}])
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "USERPROFILE": str(home), "HOME": str(home),
           "LOCALAPPDATA": str(home), "XDG_DATA_HOME": str(home), "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "flowpipe.cli", "run", "demo", "--thread", "t1"],
        input="/approve\n/approve\n", capture_output=True, text=True, env=env, timeout=120,
    )

    assert "Pipeline finished" in proc.stdout, proc.stdout[-2000:]
    assert [c["stdin"] for c in pipe.calls] == ["", "", ""]


def test_slash_engine_keeps_the_slug_clean_when_a_note_is_attached():
    # Claude Code substitutes everything after the command name into $ARGUMENTS,
    # so a note appended to the prompt would become part of the slug.
    spec = EngineSpec(name="claude", invoke="slash", cmd=["claude", "-p", "{prompt}"],
                      extra_flag="--append-system-prompt")
    argv = build_argv(spec, "build", "demo", extra="skip the baseline")

    assert argv[:3] == ["claude", "-p", "/flow:build demo"]
    assert argv[3] == "--append-system-prompt"
    assert "skip the baseline" in argv[4]
