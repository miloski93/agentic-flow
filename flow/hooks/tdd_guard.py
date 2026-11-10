#!/usr/bin/env python3
"""
OPTIONAL, NOT ACTIVE.

PreToolUse hook that blocks writing implementation before a failing test exists.
To enable, create hooks/hooks.json in this plugin:

{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/tdd_guard.py"
          }
        ]
      }
    ]
  }
}

Then run /reload-plugins. Adjust SRC_DIRS and TEST_DIR to your project layout,
or better, gate it on an env var so it only fires where you want it.
"""
import json
import os
import pathlib
import sys

SRC_DIRS = {"src", "app", "api"}
TEST_DIR = "tests"

if os.environ.get("FLOW_TDD_GUARD", "0") != "1":
    sys.exit(0)

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

raw = event.get("tool_input", {}).get("file_path", "")
if not raw:
    sys.exit(0)

path = pathlib.Path(raw)
if path.suffix != ".py" or not (SRC_DIRS & set(path.parts)):
    sys.exit(0)

test_root = pathlib.Path(TEST_DIR)
if not test_root.is_dir():
    sys.exit(0)

if not list(test_root.rglob(f"*{path.stem}*")):
    print(
        f"RED gate: no test found matching '{path.stem}' under {TEST_DIR}/. "
        f"Write the failing test first, run it, and observe the failure "
        f"before editing {path}.",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
