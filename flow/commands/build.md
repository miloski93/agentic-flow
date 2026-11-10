---
description: Execute the plan with one test-driven subagent per task.
argument-hint: <slug>
---

Slug: $ARGUMENTS

Load the flow-rules skill before you begin and obey it for the whole command.

STEP 1 - READ EXACTLY ONE THING
Read .work/$ARGUMENTS/plan.md. Do not read concept.md. Do not re-plan.
The plan is in writing-plans format: a "## Global Constraints" section, then
"### Task N" blocks, each carrying **Files:**, **Reuse:**, **Interfaces:**, and
checkbox steps that contain the actual test code and the exact commands.
If a task has no checkbox step that runs a test, stop and tell me to fix the plan.

STEP 2 - BASELINE
If the dispatch prompt carries a note from the pipeline operator that the
baseline suite was already run, skip this step - say so in one line and obey
the note.
If any task in plan.md is already checked "- [x]", also skip the full suite -
that tree was verified per task when those boxes were ticked; say so in one
line.
Otherwise run the project test suite and record the result in one line.
If it is already red before you start, stop and tell me.

STEP 3 - RESUME
A task whose steps are all "- [x]" is already done. Skip it and say so in one
line. Start at the first task with an unchecked step. Re-running this command
must never redo finished work.

STEP 4 - EXECUTE, ONE TASK AT A TIME
For each remaining task, in plan order:

  a. Pick the implementer from the task's optional **Model:** line:
       - no **Model:** line -> flow-impl (inherits the session model)
       - sonnet -> flow-impl, dispatched on the sonnet model
       - opus -> flow-impl, dispatched on the opus model
     Any other value: stop and tell me; never substitute a different model.
     Dispatch a FRESH subagent of that kind. Give it ONLY:
       - the "## Global Constraints" section
       - the full text of that single task block
       - the **Interfaces:** blocks of the earlier tasks this one consumes from
     Not the whole plan. Not the previous task's transcript.

  b. When it returns, verify its claim YOURSELF by running the exact commands
     in that task's steps. Do not take its word for it.

  c. On pass: tick that task's checkboxes to "- [x]" in plan.md, commit as the
     task's own commit step specifies, and report one line:
       Task N done | <implementer> | <files touched> | reused: <what> | <tests passing>

  d. On fail: dispatch one fresh subagent of the SAME kind with the failure
     output appended. If it fails a SECOND time, stop everything and bring me the
     failure. Never tick a checkbox on a failing verification. Never move on
     to hide a failure.

STEP 5 - NEVER DO THESE
  - Do not batch multiple tasks into one subagent.
  - Do not write implementation code yourself. You orchestrate; subagents implement.
  - Do not modify a test to make it pass. If a test seems wrong, stop and ask me.
  - Do not add anything the task did not ask for.
  - Do not accept a task that ignored its Reuse line. If the plan said extend
    an existing module and the subagent wrote a parallel one, send it back once
    with that stated plainly.

STEP 6 - STOP
Print the completed task table and exactly:
  Build complete: <n>/<n> tasks
  Next: run /clear, then /flow:check $ARGUMENTS
End your turn.
