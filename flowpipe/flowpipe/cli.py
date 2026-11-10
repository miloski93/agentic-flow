"""CLI.

  flowpipe run <slug>                    # new run, from an approved plan to ship artifacts
  flowpipe run --engine claude <slug>    # force an engine
  flowpipe resume <thread-id>            # continue after Ctrl-C / reboot / an engine failure
  flowpipe status [thread-id]            # where a run stands
  flowpipe threads                       # list past runs

Gates (triage, stall, cycle cap, ship) are answered inline in the terminal; every answer and transition is checkpointed to SQLite, so a run can
be killed and resumed at any point.
"""
from __future__ import annotations

import argparse
import sys
import uuid

from langgraph.types import Command

from .config import load_config
from .engines import EngineError
from .graph import build_graph


def _drain(graph, payload, config) -> int:
    """Stream the graph until it finishes or interrupts; answer interrupts inline."""
    thread_id = config["configurable"]["thread_id"]
    while True:
        interrupted = None
        try:
            for event in graph.stream(payload, config=config, stream_mode="updates"):
                if "__interrupt__" in event:
                    interrupted = event["__interrupt__"][0]
                    break
                for node, update in event.items():
                    keys = ", ".join(update.keys()) if isinstance(update, dict) else ""
                    print(f"[flowpipe] node '{node}' done ({keys})")
        except EngineError as e:
            # The failed node was not checkpointed, so a resume re-runs exactly it.
            print(f"\n[flowpipe] {e}")
            print(f"\n[flowpipe] Stopped on an engine failure. Fix the cause, then: flowpipe resume {thread_id}")
            return 1

        if interrupted is None:
            state = graph.get_state(config).values
            if state.get("aborted"):
                print(f"\n[flowpipe] Stopped: {state.get('abort_reason', '')}")
                return 1
            print("\n[flowpipe] Pipeline finished.")
            return 0

        info = interrupted.value if isinstance(interrupted.value, dict) else {"output": str(interrupted.value)}
        print("\n" + "=" * 72)
        print(f"PHASE: {info.get('phase', '?').upper()} - waiting for your input")
        print("=" * 72)
        print(info.get("output", ""))
        print("-" * 72)
        print(info.get("instructions", ""))
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n[flowpipe] Detached. Resume later with: flowpipe resume {thread_id}")
            return 0
        payload = Command(resume=answer)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often default to cp1252; engine output (box chars,
    # emoji) would crash prints. Degrade gracefully instead.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(prog="flowpipe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="start a new pipeline run")
    p_run.add_argument("slug", help="feature slug (must have .work/<slug>/concept.md and plan.md)")
    p_run.add_argument("--engine", default=None, help="an engine name from flow.yaml, e.g. opencode or claude")
    p_run.add_argument("--thread", default=None, help="thread id (default: random)")

    p_res = sub.add_parser("resume", help="resume an interrupted run")
    p_res.add_argument("thread", help="thread id printed when the run started")

    sub.add_parser("threads", help="list checkpointed runs")
    sub.add_parser("where", help="show which config and checkpoint DB this directory resolves to")
    p_st = sub.add_parser("status", help="progress of a run: phase state, artifacts, pending gate")
    p_st.add_argument("thread", nargs="?", default=None, help="thread id (default: most recent)")
    p_lg = sub.add_parser("logs", help="show engine logs for this repo")
    p_lg.add_argument("-f", "--follow", action="store_true", help="follow the newest log (tail -f)")
    p_lg.add_argument("-n", type=int, default=40, help="lines of the newest log to print (default 40)")

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.cmd == "logs":
        import time
        from .config import STATE_DIR, repo_root
        d = STATE_DIR / "logs" / repo_root().name
        logs = sorted(d.glob("*.log"), key=lambda q: q.stat().st_mtime) if d.exists() else []
        if not logs:
            print(f"No logs yet under {d}")
            return 0
        for q in logs[-8:]:
            print(q)
        newest = logs[-1]
        print(f"\n--- tail of {newest.name} ---")
        lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-args.n:]:
            print(line)
        if args.follow:
            print("--- following (Ctrl-C to stop) ---")
            try:
                with open(newest, encoding="utf-8", errors="replace") as fh:
                    fh.seek(0, 2)
                    while True:
                        line = fh.readline()
                        if line:
                            print(line, end="")
                        else:
                            time.sleep(0.5)
            except KeyboardInterrupt:
                pass
        return 0

    if args.cmd == "where":
        from .config import repo_root
        print(f"repo root      : {repo_root()}")
        print(f"config file    : {cfg.source or '(none found - using built-in defaults)'}")
        if cfg.project_match:
            print(f"project match  : {cfg.project_match}")
        print(f"checkpoint db  : {cfg.checkpoint_db}")
        print(f"engine         : {cfg.engine or 'auto: ' + ', '.join(cfg.detect_order)}")
        print(f"test command   : {cfg.test_command}")
        print(f"qa policy      : {cfg.qa_policy}   triage policy: {cfg.triage_policy}   "
              f"require_ce_review: {cfg.require_ce_review}")
        print("writes into this repo: nothing (checkpoints live under your home dir)")
        return 0

    g, saver_cm = build_graph(cfg)

    with saver_cm as saver:
        graph = g.compile(checkpointer=saver)

        if args.cmd == "threads":
            seen = {}
            for cp in saver.list(None):
                tid = cp.config["configurable"]["thread_id"]
                seen.setdefault(tid, cp.checkpoint.get("ts"))
            for tid, ts in sorted(seen.items(), key=lambda kv: kv[1] or ""):
                print(f"{tid}\t{ts}")
            return 0

        if args.cmd == "status":
            from . import artifacts as art_mod
            tid = args.thread
            if not tid:
                latest = None
                for cp in saver.list(None):
                    ts = cp.checkpoint.get("ts") or ""
                    if latest is None or ts > latest[1]:
                        latest = (cp.config["configurable"]["thread_id"], ts)
                if not latest:
                    print("No runs in this repo's checkpoint DB yet.")
                    return 0
                tid = latest[0]
            snap = graph.get_state({"configurable": {"thread_id": tid}})
            if not snap or not snap.values:
                print(f"No state for thread '{tid}'.", file=sys.stderr)
                return 1
            v = snap.values
            slug = v.get("slug", "?")
            unchecked = art_mod.plan_unchecked(slug)
            cm = v.get("check_meta") or {}
            qm = v.get("qa_meta") or {}
            print(f"thread   : {tid}   slug: {slug}")
            print(f"pending  : {', '.join(snap.next) if snap.next else '(none - finished or aborted)'}")
            gates = [i for task in snap.tasks for i in getattr(task, "interrupts", ())]
            if gates:
                info = gates[0].value if isinstance(gates[0].value, dict) else {}
                print(f"WAITING ON YOU at '{info.get('phase', '?')}' - flowpipe resume {tid}")
            print(f"plan     : {'all tasks ticked' if unchecked == 0 else str(unchecked) + ' unchecked task step(s)'}")
            print(f"tests    : {'green' if v.get('tests_green') else 'red/not run'}")
            print(f"check    : {cm.get('verdict', 'not run')}"
                  + (f"  high={cm.get('high_findings')} e2e={cm.get('e2e')} ce={cm.get('ce_review')}" if cm else ""))
            if qm:
                print(f"qa       : product_bugs={qm.get('product_bugs')} unstable={qm.get('unstable')}")
            print(f"cycles   : {v.get('cycles', 0)}/{v.get('max_cycles', '?')}")
            if v.get("aborted"):
                print(f"aborted  : {v.get('abort_reason', '')}")
            for name in ("concept.md", "plan.md", "check.md", "qa.md", "fixlist.md"):
                pth = art_mod.artifact(slug, name)
                if pth.exists():
                    import datetime as _dt
                    mt = _dt.datetime.fromtimestamp(pth.stat().st_mtime).strftime("%H:%M:%S")
                    print(f"artifact : .work/{slug}/{name}  (updated {mt})")
            return 0

        if args.cmd == "run":
            thread_id = args.thread or uuid.uuid4().hex[:12]
            print(f"[flowpipe] thread: {thread_id}  (resume with: flowpipe resume {thread_id})")
            config = {"configurable": {"thread_id": thread_id}}
            initial = {
                "slug": args.slug,
                "engine": args.engine or "",
                "cycles": 0,
                "max_cycles": cfg.max_cycles,
            }
            return _drain(graph, initial, config)

        if args.cmd == "resume":
            config = {"configurable": {"thread_id": args.thread}}
            state = graph.get_state(config)
            if not state or not state.values:
                print(f"[flowpipe] No checkpoint found for thread '{args.thread}'.", file=sys.stderr)
                return 1
            return _drain(graph, None, config)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
