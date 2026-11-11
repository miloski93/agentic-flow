"""Model profiles: which model each flow subagent runs on, per platform.

The plugin files never name a model. They name a TIER (fast, standard, strong)
and a profile says which model each tier means on one platform:

  ~/.config/flowpipe/models.yaml        ($FLOW_MODELS overrides the path)

    agents:                  # shared by every profile: subagent -> tier
      flow-impl: standard
      flow-sec: strong
    profiles:
      claude:
        platform: claude     # claude | opencode | codex
        session: opus        # model of the phase session itself (optional)
        tiers: {fast: haiku, standard: sonnet, strong: opus}
        agents: {flow-critic: strong}    # optional additions for this profile

A subagent that is not listed, or whose tier the profile does not define,
carries no model and inherits the session model. A bare platform name
("opencode") is always a valid profile with no models at all.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TIERS = ("fast", "standard", "strong")
PLATFORMS = ("claude", "opencode", "codex")


@dataclass
class Profile:
    name: str
    platform: str
    engine: str                                   # engine name in flow.yaml
    session: str = ""
    tiers: dict[str, str] = field(default_factory=dict)     # tier -> model
    agents: dict[str, str] = field(default_factory=dict)    # subagent -> tier

    def model_for(self, agent: str) -> str:
        return self.tiers.get(self.agents.get(agent, ""), "")


def models_path() -> Path:
    from . import config  # local import avoids a cycle
    env = os.environ.get("FLOW_MODELS")
    return Path(os.path.expanduser(env)) if env else config.GLOBAL_CONFIG.with_name("models.yaml")


def _tier_map(raw, what: str, values_are_tiers: bool) -> dict[str, str]:
    out = {str(k): str(v) for k, v in (raw or {}).items()}
    for key, value in out.items():
        tier = value if values_are_tiers else key
        if tier not in TIERS:
            raise ValueError(f"models.yaml: {what}: unknown tier '{tier}' (tiers are {', '.join(TIERS)})")
    return out


def load_profile(name: str) -> Profile:
    path = models_path()
    raw = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}
    profiles = raw.get("profiles") or {}
    if name not in profiles:
        if name in PLATFORMS:
            return Profile(name=name, platform=name, engine=name)
        raise ValueError(
            f"Unknown model profile '{name}'. Profiles in {path}: {', '.join(sorted(profiles)) or '(none)'}. "
            f"A bare platform name ({', '.join(PLATFORMS)}) also works."
        )
    body = profiles[name] or {}
    platform = str(body.get("platform", ""))
    if platform not in PLATFORMS:
        raise ValueError(f"models.yaml: profile '{name}': platform must be one of {', '.join(PLATFORMS)} "
                         f"(got '{platform}')")
    return Profile(
        name=name,
        platform=platform,
        engine=str(body.get("engine") or platform),
        session=str(body.get("session") or ""),
        tiers=_tier_map(body.get("tiers"), f"profile '{name}' tiers", values_are_tiers=False),
        agents={
            **_tier_map(raw.get("agents"), "agents", values_are_tiers=True),
            **_tier_map(body.get("agents"), f"profile '{name}' agents", values_are_tiers=True),
        },
    )
