"""Test harness: a throwaway git repo, a scripted fake engine, scripted answers.

Every test drives the real CLI entry point (`flowpipe run <slug>`), so the
graph, the checkpointer, the engine subprocess and the gates are all exercised
the way an operator would exercise them.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from flowpipe import cli, config

SLUG = "demo"
FAKE_ENGINE = Path(__file__).with_name("fake_engine.py")
TEST_COMMAND = (
    f'"{sys.executable}" -c "import pathlib,sys; p=pathlib.Path(\'.work/_fake/test_exit\'); '
    'sys.exit(int(p.read_text()) if p.exists() else 0)"'
)


class Pipe:
    def __init__(self, repo: Path, cfg_path: Path, monkeypatch, capsys):
        self.repo, self.cfg_path = repo, cfg_path
        self._monkeypatch, self._capsys = monkeypatch, capsys
        self.work = repo / ".work" / SLUG
        self.fake = repo / ".work" / "_fake"
        self.output = ""
        self.exit_code = None

    def configure(self, **settings) -> None:
        raw = yaml.safe_load(self.cfg_path.read_text(encoding="utf-8"))
        raw.update(settings)
        self.cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    def script(self, **actions) -> None:
        """script(build=[{"do": "tick"}], check=[...]): actions per command, in order."""
        (self.fake / "script.json").write_text(json.dumps(actions), encoding="utf-8")

    def configure_engine(self, **settings) -> None:
        raw = yaml.safe_load(self.cfg_path.read_text(encoding="utf-8"))
        raw["engines"]["fake"].update(settings)
        self.cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    def run(self, answers: list[str]) -> None:
        """Run the pipeline, answering each gate from `answers`; detach when they run out."""
        self._main(["run", SLUG, "--thread", "t1"], answers)

    def resume(self, answers: list[str]) -> None:
        self._main(["resume", "t1"], answers)

    def _main(self, argv: list[str], answers: list[str]) -> None:
        pending = iter(answers)

        def fake_input(_prompt=""):
            try:
                return next(pending)
            except StopIteration:
                raise EOFError

        self._monkeypatch.setattr("builtins.input", fake_input)
        self.exit_code = cli.main(argv)
        self.output = self._capsys.readouterr().out

    @property
    def gates(self) -> list[str]:
        return re.findall(r"^PHASE: (\w+)", self.output, re.M)

    @property
    def calls(self) -> list[dict]:
        path = self.fake / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def commands_run(self) -> list[str]:
        return [c["command"] for c in self.calls]


@pytest.fixture
def pipe(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    def git(*args):
        subprocess.run(["git", *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (repo / "src.txt").write_text("original\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".work/\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")

    work = repo / ".work" / SLUG
    work.mkdir(parents=True)
    (repo / ".work" / "_fake").mkdir()
    (work / "concept.md").write_text("## Problem\n", encoding="utf-8")
    (work / "plan.md").write_text(
        "## Global Constraints\n\n### Task 1: a\n- [ ] step\n- [ ] step\n\n### Task 2: b\n- [ ] step\n",
        encoding="utf-8",
    )

    commands = tmp_path / "commands"
    commands.mkdir()
    for name in ("build", "check", "qa", "fix", "ship"):
        (commands / f"flow-{name}.md").write_text(
            f"---\ndescription: fake\n---\nFAKE {name} $ARGUMENTS\n", encoding="utf-8"
        )

    cfg_path = tmp_path / "flow.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "engine": "fake",
        "test_command": TEST_COMMAND,
        "require_ce_review": False,
        "qa_policy": "auto",
        "max_cycles": 5,
        "checkpoint_db": str(tmp_path / "checkpoints.sqlite"),
        "engines": {"fake": {
            "binary": sys.executable,
            "invoke": "template",
            "commands_dir": str(commands),
            "cmd": [sys.executable, str(FAKE_ENGINE), "{prompt}"],
        }},
    }), encoding="utf-8")
    monkeypatch.setenv("FLOW_CONFIG", str(cfg_path))
    monkeypatch.setenv("FLOWPIPE_QUIET", "1")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")

    p = Pipe(repo, cfg_path, monkeypatch, capsys)
    p.script()
    return p
