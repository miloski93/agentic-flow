---
name: flow-rules
description: Operating rules for the flow development pipeline. Load at the start of any flow pipeline command, and whenever working inside a .work/<slug>/ feature directory.
---

# Flow pipeline rules

These override default behaviour for the duration of a flow command.

## Branch

Shaping and planning happen on a feature branch, never on an integration
branch. Before the shape or plan phase writes anything, check the current
branch. If it is main, master, dev, develop, or staging, ask exactly one
question - "Branch out from where?" - defaulting to dev when it exists and main
otherwise. Create `feat/<slug>`, or `fix/<slug>` for a bug-fix flow, from the
answer, then continue. Do not create or read the phase artifact before the
branch exists. The only exception is the user saying to stay where they are.

## Context

- Phase artifacts live in `.work/<slug>/` and are the handoff between phases.
  The conversation is disposable; the artifact is not. Write the artifact
  before ending a phase.
- Each command reads only the artifacts it is told to read. Do not pull in the
  previous phase's reasoning "for context". Starting narrow is the point.
- At the end of a phase, tell the user to clear the context before the next one.

## Evidence

- Never report a verification as passing without pasted command output.
- Never mark a task done on a failing test.
- "It should work" is not a result. Run it.

## Tests

- Test first, always: write the failing test, run it, observe the failure,
  then write the minimum code that passes.
- Never modify an existing test so that new code passes. Raise it with the user.
- Never weaken an assertion, loosen a matcher, add a sleep, raise a timeout, or
  skip a test to turn red into green. A red test is either a real defect or a
  wrong test. Decide which, out loud, and say so.

## Worktrees

A worktree a flow phase creates is scratch, and you own its removal.

- Create it detached, under the system temp directory, never inside the
  repository.
- Decide the removal command before you create it, not after.
- Remove it on every exit path: success, failure, error, or the user stopping
  you early. Cleanup happens before you report, never after.
- Prove it: `git worktree remove <path> --force`, then `git worktree prune`,
  then paste `git worktree list`. Confirm the primary checkout is unchanged
  with `git status --short`.
- Sweep before you create: `git worktree prune` and remove any flow worktree an
  interrupted earlier run left behind.
- Never create a worktree from a dirty primary checkout without saying so, and
  never stash, reset, or check out over the user's working tree as a substitute
  for a worktree.

## Reuse before writing

Reuse is a search obligation, not a good intention. Before writing a new
function, component, type, fixture, or file, actually search:

1. Grep the codebase for the concept under two or three different names.
2. Read the neighbours of the directory the change belongs in.
3. Check what is already in the dependency manifest.

Then state one of these out loud, in one line:

    REUSING <path> - extending it with <what>
    NEW <path> - searched <terms>, nearest is <path>, unfit because <why>

"NEW" with no search terms is not an answer. Logic that duplicates something
already in the repo is a defect even when its tests pass.

## Simplicity

Before writing code, stop at the first rung that holds:

1. Does this need to exist at all?
2. Does something already in this codebase do it?
3. Does the standard library do it?
4. Does a native platform feature do it?
5. Does an already-installed dependency do it?
6. Does it fit in one line?
7. Otherwise: the minimum that works.

No new dependency without asking. No abstraction for a second use case that
does not exist yet. No configuration, flags, or error handling nobody
requested. No wrapper that only forwards. No interface with one implementation.
No parameter nobody passes. Prefer three clear lines inline over a helper with
one call site.

## Scope

- Touch only the files the current task names.
- If you believe the task is wrong, stop and say so. Do not silently improve it.
