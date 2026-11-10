"""Deterministic working-tree fingerprint.

The backtracking rule ("review touched code => tests must rerun") must not
depend on any agent's self-report. We fingerprint the tree ourselves:
sha256 over `git status --porcelain` + `git diff HEAD` + the content of
untracked files. Agents may or may not commit; this works either way.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

_IGNORED_PREFIXES = (".flow/", ".work/")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    ).stdout


def working_tree_hash() -> str:
    h = hashlib.sha256()

    status = _git("status", "--porcelain")
    status_lines = [
        line for line in status.splitlines()
        if not line[3:].startswith(_IGNORED_PREFIXES)
    ]
    h.update("\n".join(sorted(status_lines)).encode())

    h.update(_git("diff", "HEAD", "--", ".", *(f":!{p}" for p in _IGNORED_PREFIXES)).encode())
    h.update(_git("rev-parse", "HEAD").encode())

    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    for rel in sorted(untracked):
        if rel.startswith(_IGNORED_PREFIXES):
            continue
        p = Path(rel)
        h.update(rel.encode())
        try:
            h.update(p.read_bytes())
        except OSError:
            pass

    return h.hexdigest()
