"""Model profiles and the per-platform renderer, run against the real plugin files."""
import json
import re

import pytest
import yaml

from flowpipe import config
from flowpipe.models import load_profile
from flowpipe.render import render

MODELS = {
    "agents": {"flow-impl": "standard", "flow-sec": "strong"},
    "profiles": {
        "cc": {"platform": "claude", "session": "opus",
               "tiers": {"fast": "haiku", "standard": "sonnet", "strong": "opus"}},
        "oc": {"platform": "opencode", "session": "acme/big",
               "tiers": {"fast": "acme/small", "strong": "acme/big"},
               "agents": {"flow-critic": "strong"}},
        "cx": {"platform": "codex", "engine": "my-codex",
               "tiers": {"fast": "gpt-small", "standard": "gpt-mid", "strong": "gpt-big"}},
    },
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    models = tmp_path / "models.yaml"
    models.write_text(yaml.safe_dump(MODELS), encoding="utf-8")
    monkeypatch.setenv("FLOW_MODELS", str(models))
    monkeypatch.setenv("OPENCODE_ROOT", str(tmp_path / "opencode"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.delenv("FLOW_PLUGIN_DIR", raising=False)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    return tmp_path


def frontmatter(path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(re.match(r"---\n(.*?)\n---\n", text, re.DOTALL).group(1))


# ---------------- profiles ----------------

def test_profile_maps_each_agent_to_its_tier_model(env):
    p = load_profile("oc")

    assert (p.platform, p.engine, p.session) == ("opencode", "opencode", "acme/big")
    assert p.model_for("flow-sec") == "acme/big"         # shared agents map
    assert p.model_for("flow-critic") == "acme/big"      # the profile's own addition
    assert p.model_for("flow-future") == ""              # unlisted: inherits the session model


def test_tier_a_profile_does_not_define_inherits_the_session_model(env):
    assert load_profile("oc").model_for("flow-impl") == ""   # standard is not in oc's tiers


def test_profile_can_name_a_differently_named_engine(env):
    assert load_profile("cx").engine == "my-codex"


def test_bare_platform_name_is_a_profile_without_models(env, monkeypatch):
    monkeypatch.setenv("FLOW_MODELS", str(env / "absent.yaml"))
    p = load_profile("opencode")

    assert (p.platform, p.session, p.tiers) == ("opencode", "", {})


def test_unknown_profile_names_the_ones_that_exist(env):
    with pytest.raises(ValueError, match="cc, cx, oc"):
        load_profile("nope")


def test_unknown_tier_is_rejected_not_ignored(env):
    raw = {**MODELS, "agents": {"flow-impl": "turbo"}}
    (env / "models.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="turbo"):
        load_profile("cc")


# ---------------- opencode ----------------

def test_opencode_agents_carry_their_model_and_permissions(env):
    out = render(load_profile("oc"))
    agents = env / "opencode" / "agents"

    sec = frontmatter(agents / "flow-sec.md")
    assert sec["model"] == "acme/big"
    assert sec["mode"] == "subagent"
    assert sec["permission"] == {"edit": "deny", "bash": "allow"}
    assert "model" not in frontmatter(agents / "flow-future.md")
    assert frontmatter(agents / "flow-impl.md")["permission"] == {"edit": "allow", "bash": "allow"}
    assert out.commands_dir == str(env / "opencode" / "commands")


def test_opencode_gets_one_pinned_implementer_per_tier(env):
    render(load_profile("oc"))
    agents = env / "opencode" / "agents"

    assert frontmatter(agents / "flow-impl-fast.md")["model"] == "acme/small"
    assert frontmatter(agents / "flow-impl-strong.md")["model"] == "acme/big"
    assert "model" not in frontmatter(agents / "flow-impl-standard.md")   # tier not defined
    body = (agents / "flow-impl-fast.md").read_text(encoding="utf-8")
    assert "You implement exactly one task." in body


def test_opencode_commands_use_opencode_syntax(env):
    render(load_profile("oc"))
    commands = env / "opencode" / "commands"

    assert len(list(commands.glob("flow-*.md"))) == 8
    build = commands / "flow-build.md"
    assert frontmatter(build)["agent"] == "build"
    for f in [*commands.glob("flow-*.md"), *(env / "opencode" / "agents").glob("flow-*.md")]:
        assert "/flow:" not in f.read_text(encoding="utf-8"), f.name
    assert "/flow-check $ARGUMENTS" in build.read_text(encoding="utf-8")
    assert "AGENTS.md or CLAUDE.md" in (commands / "flow-plan.md").read_text(encoding="utf-8")


def test_rendering_again_replaces_flow_files_and_leaves_others_alone(env):
    agents = env / "opencode" / "agents"
    agents.mkdir(parents=True)
    (agents / "flow-retired.md").write_text("old", encoding="utf-8")
    (agents / "mine.md").write_text("keep", encoding="utf-8")
    render(load_profile("oc"))

    assert not (agents / "flow-retired.md").exists()
    assert (agents / "mine.md").read_text(encoding="utf-8") == "keep"


# ---------------- claude ----------------

def test_claude_gets_a_loadable_plugin_copy_with_models(env):
    out = render(load_profile("cc"))
    root = env / "state" / "rendered" / "cc"
    plugin = root / "flow"

    assert out.extra_args == ["--plugin-dir", str(plugin)]
    assert json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"] == "flow"
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert market["plugins"][0]["source"] == "./flow"
    assert (plugin / "skills" / "flow-rules" / "SKILL.md").exists()
    assert (plugin / "commands" / "build.md").read_text(encoding="utf-8").count("/flow:check") == 1

    sec = frontmatter(plugin / "agents" / "flow-sec.md")
    assert (sec["name"], sec["model"], sec["tools"]) == ("flow-sec", "opus", "Read, Grep, Glob, Bash")
    assert "model" not in frontmatter(plugin / "agents" / "flow-future.md")
    fast = frontmatter(plugin / "agents" / "flow-impl-fast.md")
    assert (fast["name"], fast["model"]) == ("flow-impl-fast", "haiku")


def test_claude_render_never_touches_the_plugin_source(env):
    from flowpipe.render import plugin_dir
    before = {p: p.read_bytes() for p in plugin_dir().rglob("*") if p.is_file()}
    render(load_profile("cc"))

    assert {p: p.read_bytes() for p in plugin_dir().rglob("*") if p.is_file()} == before


# ---------------- codex ----------------

def test_codex_gets_one_toml_agent_per_subagent(env):
    out = render(load_profile("cx"))
    agents = env / "codex" / "agents"
    text = (agents / "flow-sec.toml").read_text(encoding="utf-8")

    assert 'name = "flow-sec"' in text
    assert 'model = "gpt-big"' in text
    assert re.search(r'^description = "Hostile security review', text, re.M)
    instructions = json.loads(re.search(r"^developer_instructions = (.*)$", text, re.M).group(1))
    assert "You review a diff as a hostile senior security engineer" in instructions
    assert "model =" not in (agents / "flow-future.toml").read_text(encoding="utf-8")
    assert 'model = "gpt-small"' in (agents / "flow-impl-fast.toml").read_text(encoding="utf-8")
    assert (env / "state" / "rendered" / "cx" / "commands" / "flow-build.md").exists()
    assert out.commands_dir == str(env / "state" / "rendered" / "cx" / "commands")
