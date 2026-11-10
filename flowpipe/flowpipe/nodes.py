"""Graph nodes. Every prompt comes from the flow plugin's own command files;
this module only sequences them and enforces the gates.

Two rules shape every node:

- Code before an interrupt() re-executes on resume, so a gate node contains
  the interrupt and nothing expensive. Engine calls live in their own nodes.
- An engine exiting 0 proves nothing. Each engine node measures the result it
  was dispatched for (plan boxes ticked, fix items ticked, a report rewritten)
  and sets `stalled` when there is none, which routes to the stall gate.
"""
from __future__ import annotations

import subprocess

from langgraph.types import interrupt

from . import artifacts as art
from .config import FlowConfig
from .engines import run_flow_command
from .state import FlowState
from .tree import working_tree_hash

HEADLESS_NOTE = (
    "You are running headless inside an automated pipeline: nobody can answer a question or "
    "approve a permission prompt during this run. Work only inside the repository directory and "
    "never write to a temp directory or anywhere else outside it. If you cannot complete the "
    "command, say exactly why and stop."
)
TAIL = 3000


def make_nodes(cfg: FlowConfig, resolve_engine):

    def dispatch(state: FlowState, command: str, *notes: str) -> str:
        """Run one flow command, carrying the headless note, any phase notes,
        and the operator's answer from the stall gate."""
        extra = "\n\n".join(n for n in (HEADLESS_NOTE, *notes, state.get("operator_note", "")) if n)
        return run_flow_command(resolve_engine(command, state), command, state["slug"], extra=extra)

    # ---------------- preflight: cheap checks only, no suite, no interrupt --
    def preflight(state: FlowState) -> dict:
        slug = state["slug"]
        problems: list[str] = []
        if not art.artifact(slug, "concept.md").exists():
            problems.append(f"missing .work/{slug}/concept.md - run /flow:shape first")
        unchecked = art.plan_unchecked(slug)
        if unchecked < 0:
            problems.append(f"missing .work/{slug}/plan.md - run /flow:plan first")
        try:
            resolve_engine("build", state)
        except Exception as e:  # engine resolution failure is a hard stop
            problems.append(str(e))
        if problems:
            return {"aborted": True, "abort_reason": "; ".join(problems)}
        # Oversized task blocks are the known engine killer (empty subagent
        # responses); surface them before paying for the baseline suite.
        return {"aborted": False, "oversized": art.oversized_tasks(slug, cfg.max_task_chars)}

    # ---------------- size_gate (HITL) ----------------
    def size_gate(state: FlowState) -> dict:
        answer = interrupt({
            "phase": "size_gate",
            "output": f"plan.md has unfinished task blocks over max_task_chars ({cfg.max_task_chars}):\n  "
                      + "\n  ".join(state.get("oversized", []))
                      + "\n\nBlocks this size have made engine subagents return empty results.",
            "instructions": ("Split the listed tasks in plan.md (each split task keeps its own tests and "
                             "commit step), then '/recheck'. Or '/continue' to run them anyway, '/stop' to end."),
        })
        low = str(answer).strip().lower()
        if low in ("/stop", "stop"):
            return {"aborted": True, "abort_reason": "oversized task blocks, stopped by operator"}
        if low in ("/recheck", "recheck"):
            return {"oversized": art.oversized_tasks(state["slug"], cfg.max_task_chars)}
        return {"oversized": []}

    # ---------------- baseline: the one full-suite run before autonomous work
    def baseline(state: FlowState) -> dict:
        proc = subprocess.run(cfg.test_command, shell=True, capture_output=True, text=True, timeout=3600)
        if proc.returncode == 0:
            return {"tests_green": True, "last_green_hash": working_tree_hash(), "baseline_output": ""}
        out = (proc.stdout + proc.stderr)[-2500:] or f"(no output; exit code {proc.returncode})"
        return {"tests_green": False, "baseline_output": out}

    # ---------------- baseline_gate (HITL) ----------------
    def baseline_gate(state: FlowState) -> dict:
        answer = interrupt({
            "phase": "baseline_gate",
            "output": "Baseline test suite is RED before any autonomous work:\n"
                      + state.get("baseline_output", ""),
            "instructions": "Reply '/continue' to proceed anyway (pre-existing failures stay out of scope), or '/stop'.",
        })
        if str(answer).strip().lower() not in ("/continue", "continue"):
            return {"aborted": True, "abort_reason": "red baseline, stopped by operator"}
        return {}

    # ---------------- build ----------------
    def build(state: FlowState) -> dict:
        if state.get("baseline_output"):
            note = ("The orchestrator already ran the full baseline suite: it was RED and the "
                    "operator chose to continue anyway. Skip STEP 2 (baseline); treat the "
                    "pre-existing failures as out of scope unless a task explicitly touches them.")
        else:
            note = ("The orchestrator verified the baseline suite green at the start of this run "
                    "and runs the full suite again after the plan completes. Skip STEP 2 "
                    "(baseline); per-task verification is enough here.")
        slug = state["slug"]
        before = art.plan_unchecked(slug)
        out = dispatch(state, "build", note)
        after = art.plan_unchecked(slug)
        return {
            "cycles": state.get("cycles", 0) + 1,
            "stalled": "build" if 0 < after >= before else "",
            "engine_tail": out[-TAIL:],
            "operator_note": "",
        }

    # ---------------- test (no LLM) ----------------
    def test(state: FlowState) -> dict:
        # A green run stays valid while the tree fingerprint (which includes
        # HEAD) is unchanged - a >15-min suite re-run would prove nothing new.
        if state.get("tests_green") and working_tree_hash() == state.get("last_green_hash"):
            return {}
        proc = subprocess.run(cfg.test_command, shell=True, capture_output=True, text=True, timeout=3600)
        green = proc.returncode == 0
        out = (proc.stdout + "\n" + proc.stderr)[-8000:]
        upd: dict = {"tests_green": green, "test_output": out}
        if green:
            upd["last_green_hash"] = working_tree_hash()
        else:
            upd["cycles"] = state.get("cycles", 0) + 1
            # failing suite becomes the fix list - /flow:fix handles it with TDD discipline
            art.write_fixlist(state["slug"], f"- [ ] Project test suite is red. Failure output:\n{out[-3000:]}",
                              source="orchestrator test run")
        return upd

    # ---------------- check ----------------
    def check(state: FlowState) -> dict:
        report = art.artifact(state["slug"], "check.md")
        before = art.stamp(report)
        out = dispatch(state, "check")
        # Only a report written by THIS run counts. A check.md left by an
        # earlier run describes a different tree.
        fresh = art.stamp(report) not in (None, before)
        return {
            "check_meta": art.check_verdict(state["slug"]) if fresh else {"present": False, "verdict": "UNKNOWN"},
            "checked_hash": working_tree_hash(),
            "cycles": state.get("cycles", 0) + 1,
            "stalled": "" if fresh else "check",
            "engine_tail": out[-TAIL:],
            "operator_note": "",
        }

    # ---------------- qa ----------------
    def qa(state: FlowState) -> dict:
        report = art.artifact(state["slug"], "qa.md")
        before = art.stamp(report)
        out = dispatch(state, "qa")
        fresh = art.stamp(report) not in (None, before)
        return {
            "qa_meta": art.qa_verdict(state["slug"]) if fresh else {"present": False},
            "qa_hash": working_tree_hash(),
            "stalled": "" if fresh else "qa",
            "engine_tail": out[-TAIL:],
            "operator_note": "",
        }

    # ---------------- triage (HITL unless triage_policy: auto) ----------------
    def triage(state: FlowState) -> dict:
        slug = state["slug"]
        meta = state.get("check_meta", {})
        qam = state.get("qa_meta", {})
        blocked = meta.get("verdict") == "BLOCKED"
        bugs = qam.get("product_bugs", 0) > 0

        # auto: accept every blocking finding without asking. Anything a fix
        # list cannot resolve (a skipped review, an unreadable report) still
        # falls through to the operator.
        if cfg.triage_policy == "auto" and (blocked or bugs):
            items = []
            if blocked:
                items.append("Every unresolved High severity finding in check.md")
            if bugs:
                items.append("Every product bug listed in qa.md")
            accepted = "\n".join(items)
            art.write_fixlist(slug, accepted, source="triage_policy: auto, accepted without human review")
            return {"fixlist": accepted}

        parts = []
        if blocked or not meta.get("present", True):
            parts.append("CHECK REPORT (tail):\n" + art.report_excerpt(slug, "check.md"))
        if bugs:
            parts.append("QA REPORT (tail):\n" + art.report_excerpt(slug, "qa.md"))
        if cfg.require_ce_review and meta.get("ce_review") == "SKIPPED":
            parts.append("NOTE: check ran WITHOUT ce-code-review (required by config).")

        answer = interrupt({
            "phase": "triage",
            "output": "\n\n".join(parts) or "(no report excerpts)",
            "instructions": (
                "List the findings to fix, one per line (they become fixlist.md for /flow:fix).\n"
                "Or: '/waive' to accept the state and move toward ship, '/recheck' to re-run check, '/stop' to end."
            ),
        })
        a = str(answer).strip()
        low = a.lower()
        if low in ("/stop", "stop"):
            return {"aborted": True, "abort_reason": "stopped at triage"}
        if low in ("/waive", "waive"):
            upd: dict = {"fixlist": "", "check_meta": {**meta, "verdict": "CLEAR", "waived": True}}
            if bugs:
                upd["qa_meta"] = {**qam, "product_bugs": 0, "waived": True}
            return upd
        if low in ("/recheck", "recheck"):
            return {"fixlist": "", "checked_hash": None}
        art.write_fixlist(slug, a, source="human triage of check.md / qa.md findings")
        return {"fixlist": a}

    # ---------------- fix ----------------
    def fix(state: FlowState) -> dict:
        slug = state["slug"]
        before, tree_before = art.fixlist_unchecked(slug), working_tree_hash()
        out = dispatch(state, "fix")
        after = art.fixlist_unchecked(slug)
        # Code that changed without a ticked box still deserves the suite's
        # verdict; only a run that changed nothing at all is a stall.
        idle = 0 < after >= before and working_tree_hash() == tree_before
        return {
            "cycles": state.get("cycles", 0) + 1,
            "stalled": "fix" if idle else "",
            "engine_tail": out[-TAIL:],
            "operator_note": "",
        }

    # ---------------- stall gate (HITL) ----------------
    def stall_gate(state: FlowState) -> dict:
        phase = state.get("stalled", "?")
        answer = interrupt({
            "phase": "stall_gate",
            "output": f"/flow:{phase} ended without producing its result "
                      f"(no plan or fix-list progress, or no new report). It may have asked a "
                      f"question, hit a rejected permission, or given up.\n\n"
                      f"Engine output (tail):\n{state.get('engine_tail', '')}",
            "instructions": (f"Reply with guidance for the engine - it is passed along and {phase} is re-run.\n"
                             "Or: '/retry' to re-run it unchanged, '/stop' to end."),
        })
        a = str(answer).strip()
        if a.lower() in ("/stop", "stop"):
            return {"aborted": True, "abort_reason": f"stopped at stall gate ({phase})"}
        return {"operator_note": "" if a.lower() in ("/retry", "retry") else a}

    # ---------------- ship gate (HITL) ----------------
    def ship_gate(state: FlowState) -> dict:
        slug = state["slug"]
        meta = state.get("check_meta", {})
        qam = state.get("qa_meta", {})
        summary = (
            f"check: {meta.get('verdict')}  high={meta.get('high_findings')}  e2e={meta.get('e2e')}  "
            f"ce_review={meta.get('ce_review')}{'  (waived)' if meta.get('waived') else ''}\n"
            f"qa: {'product_bugs=' + str(qam.get('product_bugs')) + ' unstable=' + str(qam.get('unstable')) if qam.get('present') else 'not run'}"
            f"{'  (waived)' if qam.get('waived') else ''}\n"
            f"tests: {'green' if state.get('tests_green') else 'RED'}  tree unchanged since last green: "
            f"{working_tree_hash() == state.get('last_green_hash')}"
        )
        answer = interrupt({
            "phase": "ship_gate",
            "output": f"Ready to prepare ship artifacts for '{slug}'.\n\n{summary}",
            "instructions": "'/approve' to run /flow:ship, '/recheck' to re-run check first, '/stop' to end.",
        })
        low = str(answer).strip().lower()
        if low in ("/approve", "approve", "ok", "lgtm"):
            return {"ship_feedback": ""}
        if low in ("/recheck", "recheck"):
            return {"checked_hash": None, "ship_feedback": "__RECHECK__"}
        return {"aborted": True, "abort_reason": "stopped at ship gate"}

    # ---------------- ship: engine call only; the review gate is ship_review -
    def ship(state: FlowState) -> dict:
        feedback = state.get("ship_feedback", "")
        note = (f"The human reviewed a previous version of these artifacts and said:\n{feedback}\n"
                "Revise accordingly.") if feedback else ""
        meta = state.get("check_meta", {})
        green_here = state.get("tests_green") and working_tree_hash() == state.get("last_green_hash")
        # The ship session may be unable to run the suite itself; it must not
        # then describe the change as untested. These facts were measured here.
        verified = (
            "Facts verified by the orchestrator, to use under 'How it was verified':\n"
            + (f"- The full project suite (`{cfg.test_command}`) passed on exactly this working tree.\n"
               if green_here else
               f"- The full project suite (`{cfg.test_command}`) has NOT passed on this exact tree.\n")
            + f"- check verdict: {meta.get('verdict')}{' (findings waived by the operator)' if meta.get('waived') else ''}, "
              f"e2e: {meta.get('e2e')}"
        )
        out = dispatch(state, "ship", verified, note)
        return {"ship_output": out[-6000:], "ship_feedback": ""}

    # ---------------- ship_review (HITL) ----------------
    def ship_review(state: FlowState) -> dict:
        answer = interrupt({
            "phase": "ship_review",
            "output": "SHIP ARTIFACTS (commit message / changelog / MR description):\n\n"
                      + state.get("ship_output", "(no output captured)"),
            "instructions": "'/approve' to finish, or reply with feedback to regenerate them.",
        })
        a = str(answer).strip()
        if a.lower() in ("/approve", "approve", "ok", "lgtm"):
            return {"ship_feedback": ""}
        return {"ship_feedback": a}

    # ---------------- cycle guard (HITL) ----------------
    def cycle_guard(state: FlowState) -> dict:
        answer = interrupt({
            "phase": "cycle_guard",
            "output": f"Cycle cap reached ({state.get('cycles', 0)}/{cfg.max_cycles}).\n"
                      f"tests_green={state.get('tests_green')}  "
                      f"check={state.get('check_meta', {}).get('verdict')}\n"
                      f"Last test output tail:\n{state.get('test_output', '')[-1500:]}",
            "instructions": "'/continue' for another round of cycles, '/stop' to end.",
        })
        if str(answer).strip().lower() in ("/continue", "continue"):
            return {"cycles": 0}
        return {"aborted": True, "abort_reason": "stopped at cycle guard"}

    return {
        "preflight": preflight, "size_gate": size_gate, "baseline": baseline,
        "baseline_gate": baseline_gate,
        "build": build, "test": test, "check": check,
        "qa": qa, "triage": triage, "fix": fix, "stall_gate": stall_gate,
        "ship_gate": ship_gate, "ship": ship, "ship_review": ship_review, "cycle_guard": cycle_guard,
    }
