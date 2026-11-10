from __future__ import annotations
from typing import Optional, TypedDict


class FlowState(TypedDict, total=False):
    slug: str
    engine: str                    # forced engine name or ""

    aborted: bool
    abort_reason: str

    oversized: list                    # plan task blocks over max_task_chars, if any
    baseline_output: str               # red-baseline tail; "" when the baseline was green

    tests_green: bool
    test_output: str
    last_green_hash: Optional[str]     # tree hash when project suite last passed

    check_meta: dict                   # parsed check.md frontmatter
    checked_hash: Optional[str]        # tree hash the current check.md describes
    qa_meta: dict                      # parsed qa.md frontmatter
    qa_hash: Optional[str]

    fixlist: str                       # triage outcome, written to fixlist.md
    ship_feedback: str                 # feedback on ship artifacts, if any
    ship_output: str                   # ship artifacts awaiting approval

    stalled: str                       # phase whose engine run produced no result, or ""
    engine_tail: str                   # tail of that run's output, shown at the stall gate
    operator_note: str                 # the operator's answer, passed to the re-run

    cycles: int
    max_cycles: int
