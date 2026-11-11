"""Renders the flow plugin for one platform, with a profile's models baked in.

The files under flow/ are the single source of truth and never name a model.
Each platform loads subagents from its own place in its own format, so a
profile is rendered into that place:

  claude    a complete plugin copy under <state-dir>/rendered/<profile>/,
            loadable with `claude --plugin-dir` or as a local marketplace
  opencode  flow-*.md under $OPENCODE_ROOT/{commands,agents}
            (default ~/.config/opencode)
  codex     flow-*.toml under $CODEX_HOME/agents (default ~/.codex), plus the
            command templates flowpipe prompts with

Besides the plugin's own subagents every platform gets one pinned implementer
per tier (flow-impl-fast, flow-impl-standard, flow-impl-strong), which is what
/flow:build routes a task's **Model:** line to.

A render owns every flow-* file in its target: they are deleted and rewritten
on each run. Nothing else there is touched.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .models import TIERS, Profile


@dataclass
class Rendered:
    written: list[str]                                   # directories written, for the operator
    commands_dir: str = ""                               # where flow-<cmd>.md landed, if anywhere
    extra_args: list[str] = field(default_factory=list)  # CLI arguments that load this render


@dataclass
class _Agent:
    name: str
    model: str
    meta: dict[str, str]                                 # the source frontmatter, in order
    body: str


def plugin_dir() -> Path:
    env = os.environ.get("FLOW_PLUGIN_DIR")
    path = Path(os.path.expanduser(env)) if env else Path(__file__).resolve().parents[2] / "flow"
    if not (path / "agents").is_dir() or not (path / "commands").is_dir():
        raise ValueError(f"flow plugin not found at {path}. Set FLOW_PLUGIN_DIR to the plugin's flow/ directory.")
    return path


def _split(path: Path) -> tuple[dict[str, str], str]:
    """A plugin file's frontmatter (simple `key: value` lines) and its body."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path}: no frontmatter")
    meta = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    return meta, match.group(2)


def _agents(plugin: Path, profile: Profile) -> list[_Agent]:
    agents = []
    for path in sorted((plugin / "agents").glob("*.md")):
        meta, body = _split(path)
        agents.append(_Agent(path.stem, profile.model_for(path.stem), meta, body))
        if path.stem == "flow-impl":
            for tier in TIERS:
                model = profile.tiers.get(tier, "")
                note = f" Pinned to the {tier} tier" + (f" ({model})." if model else ".")
                agents.append(_Agent(f"flow-impl-{tier}", model,
                                     {**meta, "description": meta["description"] + note}, body))
    return agents


def _commands(plugin: Path) -> list[tuple[str, dict[str, str], str]]:
    return [(p.stem, *_split(p)) for p in sorted((plugin / "commands").glob("*.md"))]


def _clean(directory: Path, pattern: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob(pattern):
        old.unlink()


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _state_dir(profile: Profile) -> Path:
    from . import config  # local import avoids a cycle
    return config.STATE_DIR / "rendered" / profile.name


# ---------------- opencode ----------------

def _opencode_text(text: str) -> str:
    return text.replace("/flow:", "/flow-").replace("CLAUDE.md", "AGENTS.md or CLAUDE.md")


def _render_opencode(profile: Profile, plugin: Path) -> Rendered:
    root = Path(os.path.expanduser(os.environ.get("OPENCODE_ROOT") or "~/.config/opencode"))
    commands, agents = root / "commands", root / "agents"
    _clean(commands, "flow-*.md")
    _clean(agents, "flow-*.md")
    for name, meta, body in _commands(plugin):
        _write(commands / f"flow-{name}.md",
               _opencode_text(f"---\ndescription: {meta['description']}\nagent: build\n---\n{body}"))
    for a in _agents(plugin, profile):
        tools = a.meta.get("tools", "")
        edit = "allow" if "Write" in tools or "Edit" in tools else "deny"
        bash = "allow" if "Bash" in tools else "deny"
        head = f"description: {a.meta['description']}\nmode: subagent\n"
        if a.model:
            head += f"model: {a.model}\n"
        head += f"permission:\n  edit: {edit}\n  bash: {bash}\n"
        _write(agents / f"{a.name}.md", _opencode_text(f"---\n{head}---\n{a.body}"))
    return Rendered(written=[str(commands), str(agents)], commands_dir=str(commands))


# ---------------- claude ----------------

def _render_claude(profile: Profile, plugin: Path) -> Rendered:
    root = _state_dir(profile)
    out = root / "flow"
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(plugin, out, ignore=shutil.ignore_patterns("__pycache__"))
    _clean(out / "agents", "*.md")
    for a in _agents(plugin, profile):
        meta = {**a.meta, "name": a.name}
        if a.model:
            meta["model"] = a.model
        head = "".join(f"{k}: {v}\n" for k, v in meta.items())
        _write(out / "agents" / f"{a.name}.md", f"---\n{head}---\n{a.body}")
    manifest = json.loads((out / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    (root / ".claude-plugin").mkdir()
    _write(root / ".claude-plugin" / "marketplace.json", json.dumps({
        "name": f"flow-{profile.name}",
        "description": f"flow rendered for the '{profile.name}' model profile. Generated, do not edit.",
        "owner": manifest.get("author", {"name": "flow"}),
        "plugins": [{"name": "flow", "source": "./flow", "description": manifest.get("description", "")}],
    }, indent=2) + "\n")
    return Rendered(written=[str(root)], extra_args=["--plugin-dir", str(out)])


# ---------------- codex ----------------

def _render_codex(profile: Profile, plugin: Path) -> Rendered:
    home = Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex"))
    agents, commands = home / "agents", _state_dir(profile) / "commands"
    _clean(agents, "flow-*.toml")
    _clean(commands, "flow-*.md")
    for a in _agents(plugin, profile):
        # json.dumps emits a valid TOML basic string, whatever the text contains.
        lines = [f"name = {json.dumps(a.name)}",
                 f"description = {json.dumps(a.meta['description'], ensure_ascii=False)}"]
        if a.model:
            lines.append(f"model = {json.dumps(a.model)}")
        instructions = a.body.replace("CLAUDE.md", "AGENTS.md").strip()
        lines.append(f"developer_instructions = {json.dumps(instructions, ensure_ascii=False)}")
        _write(agents / f"{a.name}.toml", "\n".join(lines) + "\n")
    for name, meta, body in _commands(plugin):
        _write(commands / f"flow-{name}.md",
               f"---\ndescription: {meta['description']}\n---\n{body.replace('CLAUDE.md', 'AGENTS.md')}")
    return Rendered(written=[str(agents), str(commands)], commands_dir=str(commands))


_ADAPTERS = {"claude": _render_claude, "opencode": _render_opencode, "codex": _render_codex}


def render(profile: Profile) -> Rendered:
    return _ADAPTERS[profile.platform](profile, plugin_dir())
