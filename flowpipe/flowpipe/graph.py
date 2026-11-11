"""Graph wiring.

  preflight ──► size_gate? ──► baseline ──► baseline_gate?
                                  │green (records tree fingerprint)
                                  ▼
                                build ──► test ──red──► fix ──► test ...
                            │green
                            ▼ (check stale?)
                          check ──BLOCKED / bugs──► triage ──► fix ──► test ...
                            │CLEAR                      │ /waive
                            ▼ (ui? qa policy)           ▼
                           qa ──bugs──► triage      ship_gate ──► ship ⇄ (feedback)
                            │clean                        ▲
                            └────────────────────────────►┘

Staleness is decided by working-tree hash, never by any agent's claim:
- tests are valid iff tree hash == last_green_hash
- check is valid iff tree hash == checked_hash and verdict CLEAR
- qa    is valid iff tree hash == qa_hash and product_bugs == 0
Anything that changes the tree (fix, qa writing specs, a reviewer touching a
file) automatically invalidates everything downstream of that fact.

Not drawn above: every engine node (build, fix, check, qa) routes to
stall_gate when its run produced no result, and stall_gate routes back to the
same node with the operator's answer attached.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from . import artifacts as art
from .config import FlowConfig
from .engines import EngineError, detect_engine
from .models import load_profile
from .nodes import make_nodes
from .render import render
from .state import FlowState
from .tree import working_tree_hash


def build_graph(cfg: FlowConfig):
    def resolve_engine(phase: str, state: FlowState):
        """The engine for one phase. A model profile, when one applies, decides
        the engine and the session model, and is rendered here so the subagents
        on disk always match the plugin source and the profile."""
        name = cfg.phase_profiles.get(phase) or state.get("profile") or (
            None if state.get("engine") else cfg.profile)
        if not name:
            preferred = cfg.phase_engines.get(phase) or state.get("engine") or cfg.engine
            return detect_engine(cfg.engines, preferred, cfg.detect_order)
        try:
            profile = load_profile(name)
            rendered = render(profile)
        except ValueError as e:
            raise EngineError(str(e))
        spec = detect_engine(cfg.engines, profile.engine, [])
        return replace(
            spec,
            model=profile.session or spec.model,
            commands_dir=rendered.commands_dir or spec.commands_dir,
            extra_args=rendered.extra_args,
        )

    nodes = make_nodes(cfg, resolve_engine)
    g = StateGraph(FlowState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    # ---- helpers over state ----
    def tests_valid(s: FlowState) -> bool:
        return bool(s.get("tests_green")) and working_tree_hash() == s.get("last_green_hash")

    def check_valid(s: FlowState) -> bool:
        m = s.get("check_meta") or {}
        if not m.get("present") and not m.get("waived"):
            return False
        if m.get("verdict") != "CLEAR":
            return False
        if cfg.require_ce_review and m.get("ce_review") == "SKIPPED" and not m.get("waived"):
            return False
        return s.get("checked_hash") is not None and working_tree_hash() == s.get("checked_hash")

    def qa_needed(s: FlowState) -> bool:
        if cfg.qa_policy == "never":
            return False
        m = s.get("check_meta") or {}
        if cfg.qa_policy == "always" or (cfg.qa_policy == "auto" and m.get("ui_touched")):
            q = s.get("qa_meta") or {}
            valid = (q.get("present") or q.get("waived")) and q.get("product_bugs", 0) == 0 \
                and s.get("qa_hash") is not None and working_tree_hash() == s.get("qa_hash")
            return not valid
        return False

    def capped(s: FlowState) -> bool:
        return s.get("cycles", 0) >= cfg.max_cycles

    # ---- edges ----
    g.add_edge(START, "preflight")

    def entry_target(s: FlowState) -> str:
        return "test" if art.plan_unchecked(s["slug"]) == 0 else "build"

    def after_preflight(s: FlowState) -> str:
        if s.get("aborted"):
            return "end"
        return "size_gate" if s.get("oversized") else "baseline"
    g.add_conditional_edges("preflight", after_preflight,
                            {"end": END, "size_gate": "size_gate", "baseline": "baseline"})

    def after_size_gate(s: FlowState) -> str:
        if s.get("aborted"):
            return "end"
        return "size_gate" if s.get("oversized") else "baseline"
    g.add_conditional_edges("size_gate", after_size_gate,
                            {"end": END, "size_gate": "size_gate", "baseline": "baseline"})

    def after_baseline(s: FlowState) -> str:
        return entry_target(s) if s.get("tests_green") else "baseline_gate"
    g.add_conditional_edges("baseline", after_baseline,
                            {"baseline_gate": "baseline_gate", "test": "test", "build": "build"})

    def after_baseline_gate(s: FlowState) -> str:
        if s.get("aborted"):
            return "end"
        return entry_target(s)
    g.add_conditional_edges("baseline_gate", after_baseline_gate,
                            {"end": END, "test": "test", "build": "build"})

    def after_build(s: FlowState) -> str:
        if s.get("stalled"):
            return "stall_gate"
        if art.plan_unchecked(s["slug"]) > 0:            # progress, but the plan is not finished
            return "cycle_guard" if capped(s) else "build"
        return "test"
    g.add_conditional_edges("build", after_build, {"build": "build", "test": "test",
                                                   "cycle_guard": "cycle_guard", "stall_gate": "stall_gate"})

    def after_stall_gate(s: FlowState) -> str:
        return "end" if s.get("aborted") else s["stalled"]     # back to the phase that stalled
    g.add_conditional_edges("stall_gate", after_stall_gate,
                            {"end": END, "build": "build", "fix": "fix", "check": "check", "qa": "qa"})

    def after_test(s: FlowState) -> str:
        if not s.get("tests_green"):
            return "cycle_guard" if capped(s) else "fix"  # fixlist.md was written by the test node
        if check_valid(s):
            return "qa" if qa_needed(s) else "ship_gate"
        return "check"
    g.add_conditional_edges("test", after_test,
                            {"fix": "fix", "check": "check", "qa": "qa",
                             "ship_gate": "ship_gate", "cycle_guard": "cycle_guard"})

    def after_check(s: FlowState) -> str:
        if s.get("stalled"):
            return "stall_gate"
        if working_tree_hash() != s.get("last_green_hash"):
            return "test"                                  # something touched code during check
        m = s.get("check_meta") or {}
        if (not m.get("present")) or m.get("verdict") != "CLEAR" \
           or (cfg.require_ce_review and m.get("ce_review") == "SKIPPED"):
            return "cycle_guard" if capped(s) else "triage"
        return "qa" if qa_needed(s) else "ship_gate"
    g.add_conditional_edges("check", after_check,
                            {"test": "test", "triage": "triage", "qa": "qa", "stall_gate": "stall_gate",
                             "ship_gate": "ship_gate", "cycle_guard": "cycle_guard"})

    def after_qa(s: FlowState) -> str:
        if s.get("stalled"):
            return "stall_gate"
        if working_tree_hash() != s.get("last_green_hash"):
            return "test"                                  # qa wrote specs -> re-run the suite
        if (s.get("qa_meta") or {}).get("product_bugs", 0) > 0:
            return "triage"
        return "ship_gate"
    g.add_conditional_edges("qa", after_qa, {"test": "test", "triage": "triage",
                                             "ship_gate": "ship_gate", "stall_gate": "stall_gate"})

    def after_triage(s: FlowState) -> str:
        if s.get("aborted"):
            return "end"
        if s.get("fixlist"):
            return "fix"
        if s.get("checked_hash") is None:                 # /recheck
            return "check"
        return "qa" if qa_needed(s) else "ship_gate"      # /waive: waiving check findings does not waive QA
    g.add_conditional_edges("triage", after_triage,
                            {"end": END, "fix": "fix", "check": "check", "qa": "qa", "ship_gate": "ship_gate"})

    def after_fix(s: FlowState) -> str:
        return "stall_gate" if s.get("stalled") else "test"   # a fix re-enters through the suite; hash does the rest
    g.add_conditional_edges("fix", after_fix, {"stall_gate": "stall_gate", "test": "test"})

    def after_ship_gate(s: FlowState) -> str:
        if s.get("aborted"):
            return "end"
        return "check" if s.get("ship_feedback") == "__RECHECK__" else "ship"
    g.add_conditional_edges("ship_gate", after_ship_gate, {"end": END, "check": "check", "ship": "ship"})

    g.add_edge("ship", "ship_review")

    def after_ship_review(s: FlowState) -> str:
        return "ship" if s.get("ship_feedback") else "end"   # feedback -> regenerate artifacts
    g.add_conditional_edges("ship_review", after_ship_review, {"ship": "ship", "end": END})

    def after_guard(s: FlowState) -> str:
        if s.get("aborted"):
            return "end"
        if art.plan_unchecked(s["slug"]) > 0:
            return "build"
        return "test"
    g.add_conditional_edges("cycle_guard", after_guard, {"end": END, "build": "build", "test": "test"})

    Path(cfg.checkpoint_db).parent.mkdir(parents=True, exist_ok=True)
    return g, SqliteSaver.from_conn_string(cfg.checkpoint_db)
