"""Reading and writing the .work/<slug>/ artifacts the flow plugin uses.

The artifacts ARE the interface between the plugin's commands and this
orchestrator - no conversation state crosses the boundary.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml


def work_dir(slug: str) -> Path:
    return Path(".work") / slug


def artifact(slug: str, name: str) -> Path:
    return work_dir(slug) / name


def read_frontmatter(path: Path) -> dict:
    """Parse the leading YAML frontmatter of an artifact. {} if absent/invalid."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"\s*---\s*\n(.*?)\n\s*---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def stamp(path: Path) -> tuple[int, int] | None:
    """Identity of a file's current content (mtime, size); None if missing.
    Used to tell a report written by this run from one left by an earlier run."""
    if not path.exists():
        return None
    st = path.stat()
    return (st.st_mtime_ns, st.st_size)


def fixlist_unchecked(slug: str) -> int:
    """Count of unresolved '- [ ]' items in fixlist.md. -1 if it is missing."""
    p = artifact(slug, "fixlist.md")
    if not p.exists():
        return -1
    return len(re.findall(r"^\s*-\s\[ \]", p.read_text(encoding="utf-8", errors="replace"), re.M))


def plan_unchecked(slug: str) -> int:
    """Count of unchecked '- [ ]' steps in plan.md. -1 if the plan is missing."""
    p = artifact(slug, "plan.md")
    if not p.exists():
        return -1
    return len(re.findall(r"^\s*-\s\[ \]", p.read_text(encoding="utf-8", errors="replace"), re.M))


def oversized_tasks(slug: str, cap: int) -> list[str]:
    """Unfinished '### Task' blocks in plan.md larger than cap characters.

    Blocks that size have produced empty engine-subagent responses; preflight
    surfaces them before any expensive work starts. Blocks with no unchecked
    step are already done and are ignored."""
    p = artifact(slug, "plan.md")
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    out: list[str] = []
    for block in re.split(r"(?=^### Task )", text, flags=re.M):
        if not block.startswith("### Task "):
            continue
        if len(block) > cap and re.search(r"^\s*-\s\[ \]", block, re.M):
            title = block.splitlines()[0].removeprefix("### ").strip()
            out.append(f"{title}  ({len(block)} chars, cap {cap})")
    return out


def check_verdict(slug: str) -> dict:
    """Normalized view of check.md frontmatter."""
    fm = read_frontmatter(artifact(slug, "check.md"))
    verdict = str(fm.get("verdict", "")).strip().upper()
    return {
        "present": bool(fm),
        "verdict": "CLEAR" if verdict.startswith("CLEAR") else ("BLOCKED" if verdict == "BLOCKED" else "UNKNOWN"),
        "high_findings": int(fm.get("high_findings", 0) or 0),
        "e2e": str(fm.get("e2e", "NOT_RUN")).strip().upper(),
        "ui_touched": str(fm.get("ui_touched", "false")).strip().lower() in ("true", "yes", "1"),
        "ce_review": str(fm.get("ce_review", "SKIPPED")).strip().upper(),
    }


def qa_verdict(slug: str) -> dict:
    fm = read_frontmatter(artifact(slug, "qa.md"))
    return {
        "present": bool(fm),
        "product_bugs": int(fm.get("product_bugs", 0) or 0),
        "unstable": int(fm.get("unstable", 0) or 0),
    }


def write_fixlist(slug: str, content: str, source: str) -> Path:
    """Write .work/<slug>/fixlist.md for /flow:fix. Items are unchecked boxes."""
    p = artifact(slug, "fixlist.md")
    lines = [
        f"# Fix list - {slug}",
        f"Source: {source}. Each item below was accepted by the human (or is a",
        "failing-test report). Full finding text lives in the referenced report.",
        "",
    ]
    for item in [l.strip() for l in content.splitlines() if l.strip()]:
        lines.append(item if item.startswith("- [") else f"- [ ] {item}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def report_excerpt(slug: str, name: str, limit: int = 3500) -> str:
    p = artifact(slug, name)
    if not p.exists():
        return f"({name} not found)"
    return p.read_text(encoding="utf-8", errors="replace")[-limit:]
