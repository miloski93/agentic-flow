---
description: End-to-end verification plus hostile security, future-proofing and complexity review.
argument-hint: <slug>
---

Slug: $ARGUMENTS

Load the flow-rules skill before you begin and obey it for the whole command.

STEP 1 - SCOPE
Read .work/$ARGUMENTS/plan.md and the "Rejected trade-offs" section of
.work/$ARGUMENTS/concept.md. Capture the diff against the integration branch
this feature was branched from - dev or develop when the repo has one,
otherwise main or master. State which one you used:
  git diff $(git merge-base HEAD <integration branch>)...HEAD --stat
Then the full diff. If it is very large, work file by file rather than
truncating silently.

STEP 2 - END TO END, FOR REAL
Dispatch the flow-e2e subagent. It must exercise the real local stack, not unit
tests: start the services, hit the actual entrypoints, observe actual responses
and side effects. Paste its raw command output as evidence.
If the stack cannot be started, say so plainly and mark E2E as NOT RUN.
Never report a pass without pasted evidence.

STEP 3 - FRONTEND GATE
Check whether the diff touches any UI files (.tsx .jsx .vue .svelte .css .scss
.html, or anything under components/ pages/ app/ ui/).
  - If yes: print "UI changes detected - run /flow:qa $ARGUMENTS before merging."
  - If no: print "No UI changes - QA phase skipped."
Continue either way.

STEP 4 - HOSTILE REVIEW
Dispatch IN PARALLEL, in a single message:
  - flow-sec subagent, given the diff and the Rejected trade-offs section
  - flow-future subagent, given the diff
  - flow-simplify subagent, given the diff and the Reuse lines from plan.md
If a "ponytail-review" skill or /ponytail-review command is available, run it
too and fold its findings into the Complexity section alongside flow-simplify's,
deduplicated.
If a "ce-code-review" command or skill is available (compound-engineering),
run it on the same diff IN ADDITION to the subagents above. Fold its findings
into the matching report sections, deduplicated, each row marked [ce]. Record
whether it ran; the frontmatter in step 5 requires the answer.
If parallel dispatch misbehaves, rerun sequentially rather than dropping one.

STEP 5 - REPORT
Write .work/$ARGUMENTS/check.md. It MUST begin with exactly this YAML
frontmatter, values filled in - an orchestrator parses it, so no prose
before it and no renamed keys:

  ---
  slug: <slug>
  verdict: BLOCKED | CLEAR
  high_findings: <count of unresolved High severity findings>
  e2e: PASS | FAIL | NOT_RUN
  ui_touched: true | false     # the step 3 frontend gate result
  ce_review: RUN | SKIPPED
  ---
  # Check report - <slug>
  ## E2E
  <PASS | FAIL | NOT RUN> plus pasted evidence
  ## Security findings
  ## Future-proofing findings
  ## Complexity findings
  ## Verdict
  BLOCKED if any High severity finding is unresolved, else CLEAR. The
  frontmatter verdict and this section must agree.

STEP 6 - STOP
Print the verdict and the path to check.md. Do not start fixing anything.
Ask me which findings I want addressed, and only then act.
