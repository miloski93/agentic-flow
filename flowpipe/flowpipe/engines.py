"""Engine adapters.

An engine invokes one of the flow plugin's OWN commands headlessly. Two
invocation styles:

  slash     the CLI executes slash commands natively in headless mode
            (Claude Code: `claude -p "/flow:build <slug>"`)
  template  the orchestrator renders the command's markdown itself -
            read <commands_dir>/flow-<cmd>.md, strip frontmatter, substitute
            $ARGUMENTS - and passes the result as the prompt
            (opencode: `opencode run --agent build "<rendered>"`)

The prompts therefore always come from the plugin files: this orchestrator
contains no phase prompts of its own.
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

NOTE_HEADING = "Additional context from the pipeline operator:"


@dataclass
class EngineSpec:
    name: str
    invoke: str                          # "slash" | "template"
    cmd: list[str]                       # template with {prompt} / {model}
    slash_prefix: str = "/flow:"         # slash style: "/flow:" or "/flow-"
    extra_flag: str = ""                 # slash style: CLI flag that carries the operator note
    commands_dir: str = ""               # template style: where flow-<cmd>.md lives
    model: str = ""
    model_args: list[str] = field(default_factory=list)   # appended when model is set and cmd has no {model}
    extra_args: list[str] = field(default_factory=list)   # appended always; a model profile's render sets them
    binary: str = ""
    timeout: int = 7200
    env: dict[str, str] = field(default_factory=dict)

    def available(self) -> bool:
        return shutil.which(self.binary or self.cmd[0]) is not None


class EngineError(RuntimeError):
    pass


def _render_template(spec: EngineSpec, command: str, slug: str) -> str:
    base = Path(os.path.expanduser(spec.commands_dir or "~/.config/opencode/commands"))
    path = base / f"flow-{command}.md"
    if not path.exists():
        raise EngineError(
            f"Engine '{spec.name}': command template {path} not found. "
            f"Run `flowpipe render <profile-or-platform>` so flow-{command}.md exists."
        )
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\A\s*---.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)  # strip frontmatter
    return text.replace("$ARGUMENTS", slug)


def build_argv(spec: EngineSpec, command: str, slug: str, extra: str = "") -> list[str]:
    """The exact command line for one phase.

    A slash engine substitutes everything after the command name into
    $ARGUMENTS, so the operator note must never ride along in the prompt - it
    would become part of the slug. It goes behind `extra_flag` instead."""
    note = f"{NOTE_HEADING}\n{extra}" if extra else ""
    tail: list[str] = []
    if spec.invoke == "slash":
        prompt = f"{spec.slash_prefix}{command} {slug}"
        if note and spec.extra_flag:
            tail = [spec.extra_flag, note]
        elif note:
            raise EngineError(
                f"Engine '{spec.name}' uses invoke: slash but has no extra_flag, so the operator "
                f"note cannot be passed without corrupting the slug. Set extra_flag in flow.yaml."
            )
    else:
        prompt = _render_template(spec, command, slug)
        if note:
            prompt += f"\n\n{note}"
    argv = [p.replace("{model}", spec.model).replace("{prompt}", prompt) for p in spec.cmd]
    if spec.model and not any("{model}" in p for p in spec.cmd):
        argv += [p.replace("{model}", spec.model) for p in spec.model_args]
    return argv + spec.extra_args + tail


def _log_path(command: str, slug: str) -> Path:
    from . import config  # local import avoids a cycle
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = config.STATE_DIR / "logs" / config.repo_root().name
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slug}-{command}-{stamp}.log"


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the engine AND its children. Agent CLIs spawn subprocesses that
    keep the output pipe open; killing only the parent would hang the reader."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_flow_command(spec: EngineSpec, command: str, slug: str, extra: str = "") -> str:
    """Run the engine, STREAMING its output live to the console (prefixed) and
    to a log file under <state-dir>/logs/<repo>/, so a long build or check is
    observable while it happens. Set FLOWPIPE_QUIET=1 to log-only.
    Returns the full combined output."""
    argv = build_argv(spec, command, slug, extra)
    quiet = os.environ.get("FLOWPIPE_QUIET", "") == "1"
    log = _log_path(command, slug)
    prefix = f"  [{spec.name}:{command}] "
    chunks: list[str] = []

    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,              # gate answers are the operator's, never the engine's
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env={**os.environ, **spec.env},
            start_new_session=(os.name != "nt"),   # own process group, so _kill_tree reaches children
        )
    except FileNotFoundError:
        raise EngineError(f"Engine '{spec.name}': '{argv[0]}' not found on PATH.")

    print(f"{prefix}started - live log: {log}", flush=True)
    timed_out = threading.Event()

    def on_timeout() -> None:
        timed_out.set()
        _kill_tree(proc)

    timer = threading.Timer(spec.timeout, on_timeout)
    timer.start()
    try:
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(f"# flow:{command} {slug} - engine {spec.name} - {datetime.datetime.now().isoformat()}\n")
            assert proc.stdout is not None
            for line in proc.stdout:
                chunks.append(line)
                fh.write(line)
                fh.flush()
                if not quiet:
                    sys.stdout.write(prefix + line if line.strip() else line)
                    sys.stdout.flush()
        proc.wait()
    finally:
        timer.cancel()
    out = "".join(chunks)
    if proc.returncode != 0:
        reason = f"timed out after {spec.timeout}s" if timed_out.is_set() else f"exited {proc.returncode}"
        raise EngineError(
            f"Engine '{spec.name}' {reason} on flow:{command}. Full log: {log}\n"
            f"--- output tail ---\n{out[-2000:]}"
        )
    return out


def detect_engine(engines: dict[str, EngineSpec], preferred: str | None, order: list[str]) -> EngineSpec:
    if preferred:
        if preferred not in engines:
            raise EngineError(f"Unknown engine '{preferred}'. Known: {', '.join(engines)}")
        spec = engines[preferred]
        if not spec.available():
            raise EngineError(f"Engine '{preferred}': '{spec.binary or spec.cmd[0]}' not on PATH.")
        return spec
    for name in order:
        spec = engines.get(name)
        if spec and spec.available():
            return spec
    raise EngineError("No engine available. Install opencode or claude, or set `engine:` in flow.yaml.")
