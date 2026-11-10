---
description: Turn an approved concept into an executable, test-first task plan.
argument-hint: <slug>
---

Slug: $ARGUMENTS

Load the flow-rules skill before you begin and obey it for the whole command.

STEP 0 - BRANCH
Apply the branch rule from flow-rules before you write anything.

STEP 1 - READ EXACTLY ONE THING
Read .work/$ARGUMENTS/concept.md, and the project CLAUDE.md if one exists.
Read nothing else yet.
If concept.md does not exist, stop and tell me to run /flow:shape first.

STEP 2 - TARGETED EXPLORATION ONLY
Explore the codebase only to answer questions the plan needs: where similar
things live, what test framework and runner is in use, what conventions exist.
Cap this at fifteen file reads. Summarise findings in ten lines or fewer.

STEP 3 - REUSE SURVEY
Separately from step 2, and before you write a single task, search for what
this feature can be built out of rather than alongside. For each capability
the concept needs, grep the codebase under two or three different names, then
record one line:
  <capability> -> REUSE <path>   or   NEW, searched <terms>, nearest <path>, unfit because <why>
This survey is the raw material for the Reuse lines in step 4. A plan written
without it will invent code that already exists.

STEP 4 - WRITE THE PLAN WITH writing-plans
Load the "writing-plans" skill. That skill owns the plan format: the document
header, Global Constraints, the File Structure pass, task right-sizing, the
Files / Interfaces blocks, bite-sized checkbox steps carrying real test code
and exact commands, and the No Placeholders rules. Follow it exactly.

Apply these three flow overrides, and nothing else:

  OVERRIDE 1 - LOCATION. Ignore the skill's default plan location. Write the
  plan to .work/$ARGUMENTS/plan.md and nowhere else. That is the pipeline
  artifact /flow:build reads.

  OVERRIDE 2 - SPEC. The header's "Spec:" field is .work/$ARGUMENTS/concept.md.
  Populate "Global Constraints" from the concept's Non-goals and Risks plus the
  project conventions you found in step 2.

  OVERRIDE 3 - HANDOFF. Do not offer the skill's two execution options and do
  not dispatch anything. Execution in this pipeline is /flow:build. Stop where
  step 6 below tells you to.

In addition, every task block carries one extra line directly under **Files:**

  **Reuse:** <the existing module, helper, fixture, component, type, or
  dependency this task extends, with its path> - or - none: searched <terms>,
  nearest is <path>, does not fit because <reason>

A Reuse line saying "none" without naming the terms searched is an incomplete
task. Write the terms.

Design rules, applied to every task before you write it down:
  - Does this need to exist at all? If not, drop the task.
  - Does something in this codebase already do it? Extend that instead.
  - Does the standard library or an already-installed dependency do it?
  - Only then write new code, and plan the least that works.
  - No new dependency without naming it and justifying it in one line.
  - No abstraction for a second use case that does not yet exist.
  - No task whose only deliverable is scaffolding. Fold setup into the task
    whose deliverable needs it.

Size rule, checked for every task before you write the next one:
  - One deliverable per task, at most 10 checkbox steps, and the whole block
    (heading to last step) under 120 lines / 8,000 characters of plan text.
  - A task that does not fit gets split into consecutive tasks, each with its
    own tests and its own commit step, before it goes into the plan.
  - This is a hard gate: the orchestrator refuses to start on a plan whose
    unfinished task blocks exceed its max_task_chars (default 8000).

STEP 5 - SELF-CHECK
The skill's own Self-Review section is mandatory here, not optional. Run it.
Then add these three flow checks and write the answers down:
  - Ordering: does any task consume an interface a later task produces?
  - Collisions: two tasks touching the same file must be adjacent and ordered.
  - Reuse: list every task whose Reuse line says "none". If that is more than a
    third of the tasks, the survey in step 3 was too shallow. Go back and redo it.
  - Size: name any task block near or over the size rule and split it now.

STEP 6 - APPROVAL
Present the task list as a compact table:
  # | title | files | reuse | test command
Wait for my explicit approval. If I ask for changes, revise plan.md and present
again.

STEP 7 - STOP
Print exactly:
  Plan ready: .work/$ARGUMENTS/plan.md  (<n> tasks)
  Next: run /clear, then /flow:build $ARGUMENTS
End your turn. Do not begin implementing.
