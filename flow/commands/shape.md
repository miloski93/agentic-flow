---
description: Shape a rough idea into a stress-tested concept document.
argument-hint: <short description of the feature>
---

Feature request: $ARGUMENTS

Load the flow-rules skill before you begin and obey it for the whole command.

Follow these steps in order. Do not skip a step. Do not merge steps. Write no
production code in this command.

STEP 0 - BRANCH
Apply the branch rule from flow-rules before you create any file. If the
current branch is an integration branch, resolve that first.

STEP 1 - SLUG
Derive a short kebab-case slug from the request. Create .work/<slug>/.
State the slug in one line.

STEP 2 - INTERROGATE
Load the "brainstorming" skill if it is available and follow it.
If it is not available, follow this fallback:
  Ask me questions in batches of no more than four. Cover, at minimum:
  what problem this actually solves and for whom; what is explicitly out of scope;
  what already exists in this codebase that could be reused instead; what the
  smallest version that still solves the real problem looks like; what happens on
  the failure path; what data this touches and who is allowed to see it.
  Keep asking until you have no material uncertainty left. Do not guess on my
  behalf. Do not propose an implementation until I have answered.

STEP 3 - WRITE THE CONCEPT
Write .work/<slug>/concept.md with this exact structure:

  ---
  slug: <slug>
  domains: [<one or more of: backend-api, database, frontend, data-eng, infra>]
  ---
  ## Problem
  ## Non-goals
  ## Approach
  ## Existing code this builds on
  ## Alternatives considered
  ## Risks
  ## Open questions

"Existing code this builds on" is not optional and may not be empty. Name the
modules, services, components, or fixtures this feature will extend, with their
paths. If you genuinely found nothing to build on, write down the terms you
searched for and why the nearest match does not fit.

The domains list routes the expert review in the next step. Choose it based on
what the feature actually touches.

STEP 4 - CRITIQUE
Dispatch subagents IN PARALLEL in a single message:
  - one flow-critic subagent given the full text of concept.md
  - one flow-critic subagent per entry in the domains list, given the full text
    of concept.md and told: "Review this as a senior <domain> engineer with ten
    years of production experience. Judge it against best practice in your field."
If parallel dispatch fails or returns malformed output, retry the same subagents
sequentially. Do not continue with partial results.

STEP 5 - TRIAGE
Merge every finding into one numbered table sorted by severity:
  # | severity | source | claim | proposed change
Present it. Act on none of it. Ask me to accept or reject each row.

STEP 6 - RECORD
Append to concept.md:
  ## Rejected trade-offs
  For each rejection: the finding, and the reason I gave.
The security review reads this later. Record it faithfully. Do not editorialise.

STEP 7 - STOP
Print exactly:
  Concept ready: .work/<slug>/concept.md
  Next: run /clear, then /flow:plan <slug>
End your turn. Do not begin planning.
