"""Scripted stand-in for an agent CLI, used by the test suite.

Invoked as `python fake_engine.py "<prompt>"` from the repo root. The prompt's
first line is "FAKE <command> <slug>" (rendered from the test command
templates). Each call pops the next action for that command from
.work/_fake/script.json and performs it; with no action left it does nothing,
like an engine that ended its session without doing the work.
"""
import json
import pathlib
import re
import sys

prompt = sys.argv[1]
command, slug = re.match(r"FAKE (\w+) (\S+)", prompt).groups()
fake = pathlib.Path(".work/_fake")
work = pathlib.Path(".work") / slug
# Like `claude -p`, read whatever stdin carries. An engine must never get the
# operator's terminal input.
stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()

with open(fake / "calls.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"command": command, "prompt": prompt, "stdin": stdin, "argv": sys.argv[2:]}) + "\n")

script_path = fake / "script.json"
script = json.loads(script_path.read_text(encoding="utf-8"))
queue = script.get(command, [])
action = queue.pop(0) if queue else {"do": "ask"}
script_path.write_text(json.dumps(script), encoding="utf-8")


def tick(path: pathlib.Path, count: int = -1) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace("- [ ]", "- [x]", count), encoding="utf-8")


do = action["do"]
if do == "ask":
    print("I hit a problem. How would you like to proceed?")
elif do == "hang":
    import time
    print("thinking...", flush=True)
    time.sleep(120)
elif do == "fail":
    print("engine exploded")
    sys.exit(action.get("code", 3))
elif do == "tick":
    tick(work / "plan.md")
    print("Build complete")
elif do == "tick_and_break":
    tick(work / "plan.md")
    with open("src.txt", "a", encoding="utf-8") as fh:
        fh.write("broken\n")
    (fake / "test_exit").write_text("1", encoding="utf-8")
    print("Build complete")
elif do == "tick_one":
    tick(work / "plan.md", 1)
    print("One step done")
elif do == "check":
    (work / "check.md").write_text(
        "---\n"
        f"slug: {slug}\n"
        f"verdict: {action['verdict']}\n"
        f"high_findings: {1 if action['verdict'] == 'BLOCKED' else 0}\n"
        "e2e: PASS\n"
        f"ui_touched: {'true' if action.get('ui') else 'false'}\n"
        f"ce_review: {action.get('ce', 'RUN')}\n"
        "---\n# Check report\n## Security findings\nHigh | app.py:1 | injection\n",
        encoding="utf-8",
    )
    print("check written")
elif do == "qa":
    (work / "qa.md").write_text(
        f"---\nslug: {slug}\nproduct_bugs: {action.get('bugs', 0)}\nunstable: 0\n---\n# QA report\n",
        encoding="utf-8",
    )
    print("qa written")
elif do == "fixall":
    tick(work / "fixlist.md")
    (fake / "test_exit").unlink(missing_ok=True)
    with open("src.txt", "a", encoding="utf-8") as fh:  # a real change to the tree
        fh.write("fixed\n")
    print("Fixes applied")
elif do == "ship":
    print("COMMIT MESSAGE: feat: something")
else:
    raise SystemExit(f"unknown fake action {do!r}")
