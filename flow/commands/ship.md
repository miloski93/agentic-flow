---
description: Prepare the branch for review - commit message, changelog, MR description.
argument-hint: <slug>
---

Slug: $ARGUMENTS

Load the flow-rules skill before you begin.

You prepare. You do not commit, push, merge, rebase, tag, or open anything.
Every artifact in this command is shown to me for approval first.

STEP 1 - GATE
Read .work/$ARGUMENTS/check.md. If its verdict is BLOCKED, stop and print the
unresolved High findings. If check.md does not exist, stop and tell me to run
/flow:check first.
If the diff touches user-facing surfaces and .work/$ARGUMENTS/qa.md does not
exist, say so and ask whether to continue anyway.

STEP 2 - STATE
Print three lines: the current branch, its upstream if any, and the merge base
the review will compare against. If the current branch is an integration
branch, stop - this work is on the wrong branch.

STEP 3 - COMMIT MESSAGE
Read the last twenty commit subjects and match their convention exactly.
If the repo uses Conventional Commits, the type is bare and must be one the
repo already uses, with an optional scope in parentheses. One line. No body
unless the repo's own history has bodies. No trailers of any kind, and no
attribution to any tool, model, or agent.
Propose the message. Do not run git commit.

STEP 4 - CHANGELOG
If the repo has a changelog it actually maintains, draft the entry in that
file's existing format and show it as a diff. One entry, user-facing language,
no internal task ids. If the change is not user-facing, say so and skip it
rather than padding the file.

STEP 5 - MR DESCRIPTION
Draft it from concept.md and check.md, not from the diff:
  - What this changes and why, in three sentences, for a reviewer who has not
    read the concept.
  - What is deliberately out of scope, from Non-goals.
  - Trade-offs consciously accepted, from Rejected trade-offs.
  - How it was verified: the E2E result, the QA suite path and its result, and
    the exact test command a reviewer can run.
  - The one or two places a reviewer should look hardest.
Never name an agent, a subagent, a slash command, a plugin, a model, or a
.work/ path in this description. Reference tracked paths only - the .work/
directory does not exist for anyone else.

STEP 6 - STOP
Print the commit message, the changelog diff, and the MR description.
Print the exact commands I would run to commit and push, but do not run them.
End your turn.
