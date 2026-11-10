---
description: Apply human-accepted findings or failing-test fixes with build-grade discipline.
argument-hint: <slug>
---

Slug: $ARGUMENTS

Load the flow-rules skill before you begin and obey it for the whole command.

STEP 1 - READ THE FIX LIST
Read .work/$ARGUMENTS/fixlist.md. It lists the items a human accepted for
fixing, referencing findings in check.md or qa.md, or containing failing-test
output directly. If it does not exist or has no unresolved "- [ ]" item, stop
and say there is nothing to fix.
Read the referenced sections of .work/$ARGUMENTS/check.md and qa.md so each
item's full finding text is in front of you.
Read the "## Global Constraints" section of .work/$ARGUMENTS/plan.md.

STEP 2 - ONE ITEM AT A TIME
For each unresolved item, in list order:
  a. Dispatch a FRESH flow-impl subagent. Give it ONLY: the Global Constraints,
     the single item with its full finding text, and the files it names.
     Not the whole report. Not the previous item's transcript.
  b. A fix follows the same TDD rule as a task: first a failing test that
     reproduces the defect, run it, observe the failure, then the minimum
     change that passes. If a finding genuinely cannot be reproduced by a test
     (a naming issue, a comment, dead code), say so in one line and fix it
     directly.
  c. Verify the subagent's claim YOURSELF by running the tests the item
     touches. Do not take its word for it.
  d. On pass: tick the item to "- [x]" in fixlist.md and commit, one commit
     per item, subject referencing the finding.
  e. On a SECOND consecutive failure of the same item: stop everything and
     bring me the failure. Never tick a failing item. Never skip ahead to
     hide a failure.

STEP 3 - NEVER DO THESE
  - Do not fix an item that is not on the list. Findings nobody accepted are
    recorded trade-offs, not work.
  - Do not refactor beyond what the item requires.
  - Do not weaken an assertion, modify an unrelated test, add a sleep, or
    raise a timeout to make a finding disappear.

STEP 4 - SUITE
Run the full project test suite. Paste the tail of the output.

STEP 5 - STOP
Print exactly:
  Fixes applied: <n>/<n>  (.work/$ARGUMENTS/fixlist.md)
  The previous check report is now stale.
  Next: run /clear, then /flow:check $ARGUMENTS
End your turn.
