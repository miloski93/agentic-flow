---
description: Build and run an exhaustive Playwright suite for the feature.
argument-hint: <slug>
---

Slug: $ARGUMENTS

Load the flow-rules skill before you begin and obey it for the whole command.

This phase produces a real, committed, re-runnable Playwright suite. It does
not produce opinions, and it does not produce tests that are thrown away after
the merge. The suite lives with the project's other end-to-end tests and runs
in CI with them.

STEP 1 - SCOPE
Read .work/$ARGUMENTS/plan.md for the task titles and their Files blocks, and
the Problem and Non-goals sections of .work/$ARGUMENTS/concept.md. Capture the
diff against the merge base.
List every user-facing surface the diff touches: routes, pages, dialogs, forms,
tables, empty states, toasts, navigation.
If there are none, print "No user-facing surfaces in this diff - QA not
applicable." and stop.

STEP 2 - REUSE THE EXISTING HARNESS
Look for these, in order, and report what you found in at most five lines:
  - playwright.config.* at the repo root or under e2e/, tests/, test/
  - its testDir, and every spec and helper already living there
  - shared fixtures, page objects, auth or session seeding, network mocking
  - the package script that runs the suite (test:e2e or similar)
  - the data-testid conventions already used by the components in the diff

You extend this harness. You do not build a parallel one.
  - Reuse the existing config. Never add a second config file.
  - Reuse the existing fixtures, session seeding, and request mocking. If the
    current specs mock the API one way, mock yours the same way.
  - Add a new Playwright project or baseURL only if the feature genuinely
    cannot run under the existing one, and say why in one line.

Only if the project has NO Playwright setup at all: scaffold the minimum that
runs - one config, one fixtures file, one package script - and say plainly that
you are introducing Playwright to this repo. Nothing beyond that minimum.

STEP 3 - SCENARIO MATRIX
Before writing a single spec, write the matrix into .work/$ARGUMENTS/qa.md
under "## Matrix". One row per scenario:
  surface | scenario | precondition | expected observable outcome

Cover every one of these per surface. Mark a row N/A with a reason rather than
dropping it:
  - Happy path, at realistic data volume, not three sample rows.
  - First run: no data at all.
  - Empty result from a filter or search that legitimately matches nothing.
  - Loading state, asserted before the data resolves.
  - Server error: 500 on the primary request.
  - Client error: 400 or 422 carrying a field-level message.
  - Network failure: the request never resolves.
  - Partial failure: one of several parallel requests fails.
  - Validation: required, boundary, and over-long input.
  - Permissions: every role that sees this surface differently, including the
    role that must not see it at all.
  - Deep link straight to the surface, then reload, then browser back.
  - Destructive action: confirmation appears, cancel really cancels, confirm
    really applies.
  - Keyboard only: tab order reaches every control, focus is visible, dialogs
    trap focus and restore it on close.
  - Viewports 375, 768, 1440: nothing overflows, clips, or becomes unreachable.
  - Long text: a name or description far longer than the design assumed.
  - Page health, applied to every row above: no uncaught exception, no console
    error this change introduced, no failed or duplicated request the scenario
    did not intend.

Present the matrix. It is the contract for what gets written next.
If more than a quarter of the rows are marked N/A, you are excusing yourself
from work rather than scoping it. Justify each N/A out loud or write the test.

STEP 4 - WRITE THE SUITE
Dispatch the flow-qa subagent. Give it the matrix, the harness summary from
step 2, the diff, and the exact file paths it may create or modify.
It writes specs. It does not touch application code.

STEP 5 - RUN IT FOR REAL
Run the project's own end-to-end command yourself and paste the raw output.
A suite that was written but not run is reported NOT RUN, never PASS.
If the run cannot start, report exactly why and stop. Do not substitute the
Playwright MCP browser for a real suite run.

STEP 6 - TRIAGE EVERY FAILURE
For each failing spec, decide out loud which it is:
  PRODUCT BUG - the application is wrong. Keep the failing test, record it as a
                finding, and do not fix application code in this phase.
  TEST DEFECT - the spec is wrong: bad selector, wrong expectation, real race.
                Fix the spec and re-run.
You may not weaken an assertion, loosen a matcher, add a fixed sleep, raise a
timeout, or skip a spec to reach green. If a spec is genuinely non-deterministic,
say so and leave it failing.
Use the Playwright MCP browser only here, and only to see what the page really
renders while diagnosing. It is a debugger, not the test runner.

STEP 7 - PROVE THE TESTS CAN FAIL
A test written against working code has never been observed to fail, so it may
be asserting nothing at all. Verify the suite against the code as it was before
this feature existed. Do this only once the suite is green or its failures are
known product bugs.

  a. Sweep first. Run `git worktree prune`, then `git worktree list`. If an
     earlier interrupted run left a flow-qa worktree behind, remove it now.
  b. Resolve the base: `git merge-base HEAD <the integration branch>`.
  c. Create a detached throwaway worktree at that commit, under the system
     temp directory - never inside the repository, where it would pollute
     git status and the runner's test discovery:
       git worktree add --detach <tmpdir>/flow-qa-<slug> <base-sha>
     Decide the cleanup command in step g NOW, before you run anything else.
  d. Give it what it needs to run. Prefer linking or copying the already
     installed dependencies from the primary checkout over reinstalling them.
     If the dependency lockfile differs between the base commit and HEAD, that
     shortcut is invalid - run the project's own install command in the
     worktree instead.
  e. Copy ONLY the new spec files, plus any shared fixture changes they depend
     on, into the worktree's test directory. Nothing else from the branch.
  f. Run the new specs there, and confirm from the output that the runner
     started its OWN server. If a server from step 5 is still listening on the
     configured port and the config reuses an existing one, this run silently
     tests the NEW application, every spec passes, and this entire check
     becomes a lie. Stop that server first and verify a fresh one booted.
  g. Delete the worktree. Always:
       git worktree remove <tmpdir>/flow-qa-<slug> --force
       git worktree prune
     Run this whether the check passed, failed, errored, or you are stopping
     early - and before you report anything. Then prove it with
     `git worktree list` and paste the output. The primary checkout must be
     untouched: confirm with `git status --short`.

Expected result: every new spec FAILS against the base. That is the proof it
tests something real.
  - A spec that PASSES against the base asserts nothing about this feature.
    Rewrite it so it fails, or delete it. Name it in the report either way.
  - A spec that errors because the route, component, or column did not exist
    yet counts as failing for the right reason. Say which reason applied.

STEP 8 - FLAKE CHECK
A spec that passes sometimes is a spec nobody trusts in six months. In the
primary checkout, re-run the new specs only:
  - three times over, using the runner's repeat flag
  - once with parallelism forced to a single worker
  - once at the config's default parallelism
Anything not green in every one of those runs is unstable. Fix the actual race
by waiting on the state you care about rather than on a timer. You may not
stabilise a spec by adding a sleep, raising a timeout, loosening a matcher,
pinning the worker count, or marking it skipped. A spec that only passes
serially has an order or shared-state dependency, and that is a defect in the
spec, not a reason to change the config.
Report anything you cannot honestly make deterministic, and leave it failing.

STEP 9 - REPORT
Finish .work/$ARGUMENTS/qa.md. It MUST begin with exactly this YAML
frontmatter, values filled in - an orchestrator parses it:

  ---
  slug: <slug>
  product_bugs: <count of rows in Product bugs found>
  unstable: <count of specs in Unstable>
  ---
  # QA report - <slug>
  ## Harness
  <what was reused; what, if anything, was added and why>
  ## Matrix
  <the step 3 table, with a result column: PASS | FAIL | NOT RUN | N/A>
  ## Suite
  <exact spec paths, and the command that runs them>
  ## Run output
  <pasted raw output of the real run>
  ## Baseline check
  <base sha; per spec, FAILED-as-expected or PASSED-and-was-rewritten>
  <pasted `git worktree list` and `git status --short` proving cleanup>
  ## Flake check
  <the runs performed, and any spec that was not green in all of them>
  ## Product bugs found
  severity | surface | what is wrong | the spec that proves it
  ## Unstable
  <any spec that could not honestly be made deterministic>

STEP 10 - STOP
Print PASS / FAIL / NOT RUN counts, the spec paths, and the run command.
Confirm in one line that no worktree was left behind.
Do not fix application code. Ask me which product bugs to address.
