"""flow.yaml loader - repo-clean by default.

Nothing is written into your repositories. Config and state live under your
home directory:

  ~/.config/flowpipe/flow.yaml                 the one config file
  ~/.local/share/flowpipe/checkpoints/*.sqlite one DB per repo, named by path

Config resolution, first match wins:
  1. $FLOW_CONFIG                              explicit override
  2. ./flow.yaml                               only if you deliberately put one there
  3. ~/.config/flowpipe/flow.yaml              the normal case

Within the chosen file, per-project overrides are merged over the top-level
defaults. Projects are matched against the repo root by fnmatch; the longest
(most specific) matching pattern wins:

  test_command: "pytest -x -q"          # default for every repo
  projects:
    "~/projects/my-api":
      test_command: "pytest -q tests/"
      qa_policy: never
    "~/projects/*-frontend":
      test_command: "npm test --silent"
      qa_policy: always
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .engines import EngineSpec

DEFAULT_ENGINES: dict[str, dict] = {
    "opencode": {
        "binary": "opencode",
        "invoke": "template",
        "commands_dir": "~/.config/opencode/commands",
        "cmd": ["opencode", "run", "--agent", "build", "{prompt}"],   # opencode's own default model
    },
    "claude": {
        "binary": "claude",
        "invoke": "slash",
        "slash_prefix": "/flow:",
        "extra_flag": "--append-system-prompt",
        "cmd": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"],
    },
}

DEFAULT_DETECT_ORDER = ["opencode", "claude"]

def _config_dir() -> Path:
    """Platform-native config dir - but an existing legacy ~/.config/flowpipe
    always wins, so a setup created before v3 (including on Windows) keeps
    working without migration."""
    legacy = Path.home() / ".config" / "flowpipe"
    if legacy.exists():
        return legacy
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "flowpipe"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "flowpipe"


def _state_dir() -> Path:
    legacy = Path.home() / ".local" / "share" / "flowpipe"
    if legacy.exists():
        return legacy
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "flowpipe"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "flowpipe"


GLOBAL_CONFIG = _config_dir() / "flow.yaml"
STATE_DIR = _state_dir()
CHECKPOINT_DIR = STATE_DIR / "checkpoints"


@dataclass
class FlowConfig:
    engine: str | None = None
    detect_order: list[str] = field(default_factory=lambda: list(DEFAULT_DETECT_ORDER))
    engines: dict[str, EngineSpec] = field(default_factory=dict)
    phase_engines: dict[str, str] = field(default_factory=dict)
    test_command: str = "pytest -x -q"
    max_cycles: int = 5
    max_task_chars: int = 8000
    checkpoint_db: str = ""
    qa_policy: str = "auto"
    triage_policy: str = "human"
    require_ce_review: bool = False
    source: str = ""            # config file actually used
    project_match: str = ""     # which projects: pattern matched, if any


def repo_root(start: Path | None = None) -> Path:
    """Nearest enclosing git repo root, or the cwd if there isn't one."""
    p = (start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate / ".git").exists():
            return candidate
    return p


def checkpoint_path_for(root: Path) -> Path:
    """Stable, collision-proof, human-readable DB name for a repo path."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-") or "repo"
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:10]
    return CHECKPOINT_DIR / f"{slug}-{digest}.sqlite"


def _find_config() -> Path | None:
    env = os.environ.get("FLOW_CONFIG")
    if env:
        p = Path(os.path.expanduser(env))
        if p.exists():
            return p
    local = Path("flow.yaml")
    if local.exists():
        return local
    if GLOBAL_CONFIG.exists():
        return GLOBAL_CONFIG
    return None


def _project_overrides(raw: dict, root: Path) -> tuple[dict, str]:
    projects = raw.get("projects") or {}
    if not isinstance(projects, dict):
        return {}, ""
    target = str(root)
    best_pattern, best_body = "", {}
    for pattern, body in projects.items():
        expanded = str(Path(os.path.expanduser(str(pattern))))
        if fnmatch.fnmatch(target, expanded) or fnmatch.fnmatch(target, expanded.rstrip("/") + "/*"):
            if len(expanded) > len(best_pattern):
                best_pattern, best_body = expanded, (body or {})
    return best_body, best_pattern


def _choice(settings: dict, key: str, default: str, allowed: tuple[str, ...]) -> str:
    value = str(settings.get(key, default))
    if value not in allowed:
        raise ValueError(f"flow.yaml: {key} must be one of {', '.join(allowed)} (got '{value}')")
    return value


def load_config(root: Path | None = None) -> FlowConfig:
    root = root or repo_root()
    raw: dict = {}
    source = ""
    path = _find_config()
    if path:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        source = str(path)

    overrides, matched = _project_overrides(raw, root)
    settings = {**{k: v for k, v in raw.items() if k != "projects"}, **overrides}

    merged = {n: dict(s) for n, s in DEFAULT_ENGINES.items()}
    for n, s in (settings.get("engines") or {}).items():
        merged.setdefault(n, {})
        merged[n].update(s or {})

    engines = {
        n: EngineSpec(
            name=n,
            invoke=str(s.get("invoke", "template")),
            cmd=list(s.get("cmd", [])),
            slash_prefix=str(s.get("slash_prefix", "/flow:")),
            extra_flag=str(s.get("extra_flag", "")),
            commands_dir=str(s.get("commands_dir", "")),
            model=str(s.get("model", "")),
            binary=str(s.get("binary", "")),
            timeout=int(s.get("timeout", 7200)),
            env={k: str(v) for k, v in (s.get("env") or {}).items()},
        )
        for n, s in merged.items() if s.get("cmd")
    }

    ckpt = settings.get("checkpoint_db")
    checkpoint_db = str(Path(os.path.expanduser(str(ckpt)))) if ckpt else str(checkpoint_path_for(root))

    return FlowConfig(
        engine=os.environ.get("FLOW_ENGINE") or settings.get("engine"),
        detect_order=list(settings.get("detect_order", DEFAULT_DETECT_ORDER)),
        engines=engines,
        phase_engines={k: str(v) for k, v in (settings.get("phase_engines") or {}).items()},
        test_command=str(settings.get("test_command", "pytest -x -q")),
        max_cycles=int(settings.get("max_cycles", 5)),
        max_task_chars=int(settings.get("max_task_chars", 8000)),
        checkpoint_db=checkpoint_db,
        qa_policy=str(settings.get("qa_policy", "auto")),
        triage_policy=_choice(settings, "triage_policy", "human", ("human", "auto")),
        require_ce_review=bool(settings.get("require_ce_review", False)),
        source=source,
        project_match=matched,
    )
