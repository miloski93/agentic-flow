# flow

A test-driven development pipeline for Claude Code and opencode. Each phase
reads one artifact, does one job, writes one artifact, and stops. You clear the
context between phases, so every phase starts near-empty and nothing is lost.

    /flow:shape <idea>    ->  .work/<slug>/concept.md   interrogation + hostile domain critique
    /flow:plan  <slug>    ->  .work/<slug>/plan.md      test-first tasks, superpowers writing-plans format
    /flow:build <slug>    ->  commits                   one TDD subagent per task
    /flow:check <slug>    ->  .work/<slug>/check.md     E2E + security + future + complexity review
    /flow:qa    <slug>    ->  tests/e2e/<slug>.spec.ts  exhaustive Playwright suite, run for real
                              .work/<slug>/qa.md
    /flow:fix   <slug>    ->  commits                   applies the findings you accepted
    /flow:ship  <slug>    ->  commit msg + changelog + MR description (prepared, never executed)
    /flow:next  [slug]    ->  tells you where you are

In opencode the same commands are `/flow-shape`, `/flow-plan`, and so on.

## Requirements

- Claude Code 2.1.275 or later, or opencode.
- git. Every phase works on a feature branch and diffs against the integration
  branch it was cut from.
- Optional, used automatically when present:
  - [superpowers](https://github.com/obra/superpowers): `brainstorming`,
    `writing-plans` and `test-driven-development` skills. `writing-plans` is
    what gives `/flow:plan` its best output.
  - ponytail: `/ponytail-review` is folded into `/flow:check`.
  - compound-engineering: `ce-code-review` is folded into `/flow:check`.
  - a Playwright MCP server: used by `/flow:qa` as a debugger while triaging
    failures, never as the test runner.

## Install

### Claude Code

From GitHub:

    /plugin install flow --marketplace miloski93/agentic-flow

From a local clone:

    /plugin marketplace add /path/to/this/repo
    /plugin install flow@flow-local

Confirm: typing `/flow:` autocompletes eight commands, and `/agents` lists seven
`flow-*` agents.

### opencode

opencode reads plain files, so clone the repo and render them:

    bash scripts/render-opencode.sh

This writes `flow-*.md` into `~/.config/opencode/commands` and
`~/.config/opencode/agents`. Then add the skills directory to `skills.paths` in
`~/.config/opencode/opencode.json` so the shared `flow-rules` skill loads:

    "skills": { "paths": ["/path/to/this/repo/flow/skills"] }

Restart opencode and type `/flow-` to confirm.

### Per project

The `.work/` artifacts are local scratch. In each repository you use flow in:

    echo '.work/' >> .git/info/exclude

## How to use it

Start with an idea, on any branch:

    /flow:shape let users export their invoices as CSV

flow asks where to branch from if you are on an integration branch, creates
`feat/<slug>`, questions you until nothing material is unclear, writes
`concept.md`, and has hostile critics attack it. You accept or reject each
finding. It then prints the next command and stops.

From there the loop is always the same: run `/clear`, then the command the
previous phase printed.

    /clear
    /flow:plan invoice-csv-export       # review the task table, approve it
    /clear
    /flow:build invoice-csv-export      # one commit per task, resumable
    /clear
    /flow:check invoice-csv-export      # verdict: CLEAR or BLOCKED
    /clear
    /flow:qa invoice-csv-export         # only when the diff touches UI
    /clear
    /flow:ship invoice-csv-export

Lost track? `/flow:next <slug>` reads the artifacts and tells you which command
comes next. `/flow:next` with no argument lists every feature in `.work/`.

### When check or qa finds something

Neither phase fixes anything. They report and ask which findings you want
addressed. Write the ones you accept into `.work/<slug>/fixlist.md` as
unchecked boxes, then:

    /clear
    /flow:fix <slug>
    /clear
    /flow:check <slug>

Findings you did not put on the list are treated as recorded trade-offs, not
work.

## Phases

**shape** interrogates the idea, writes a concept, then attacks it with one
generic critic plus one senior-engineer critic per domain it touches. Rejected
findings are recorded so the security review can see what was consciously
traded away.

**plan** delegates the plan format to the superpowers `writing-plans` skill -
real test code in every step, exact commands, Files and Interfaces blocks, no
placeholders - with three overrides: the plan is written to
`.work/<slug>/plan.md`, the spec is `concept.md`, and execution is
`/flow:build`. Every task also carries a `**Reuse:**` line naming the existing
code it extends, and must stay under 10 steps and 8,000 characters.

**build** dispatches one fresh TDD subagent per task, verifies each claim by
re-running the task's own commands, ticks the plan's checkboxes, and commits.
Re-running it resumes rather than redoing.

**check** runs the real stack end to end, then reviews the diff in parallel for
security, six-month cost, and over-engineering. The verdict is BLOCKED while
any High finding is unresolved.

**qa** enumerates an exhaustive scenario matrix, extends the project's existing
Playwright harness rather than building a parallel one, writes the specs, runs
them for real, and triages every failure as a product bug or a test defect. It
then proves the suite is worth having: each new spec is re-run against the
merge base in a throwaway worktree and must fail there. Finally it re-runs the
specs repeatedly, serially and in parallel, to catch flake. The suite is
committed and runs in CI from then on.

**fix** applies the items in `fixlist.md` one at a time, each with a failing
test first, one commit per item.

**ship** prepares a commit message, a changelog entry, and an MR description.
It never commits, pushes, or opens anything.

## Artifacts

Everything lives in `.work/<slug>/`:

| File          | Written by   | Read by                    |
|---------------|--------------|----------------------------|
| `concept.md`  | shape        | plan, check, qa, ship      |
| `plan.md`     | plan         | build, check, qa, fix      |
| `check.md`    | check        | fix, ship, next            |
| `qa.md`       | qa           | fix, ship, next            |
| `fixlist.md`  | you          | fix                        |

`check.md` and `qa.md` begin with YAML frontmatter (`verdict`, `high_findings`,
`e2e`, `ui_touched`, `product_bugs`, ...) so a script can drive the pipeline
without parsing prose.

## Agents

    flow-critic     hostile design reviewer, also plays domain expert
    flow-impl       single-task TDD implementer, reuse-first
    flow-e2e        real-stack end-to-end verifier
    flow-sec        15-point hostile security review
    flow-future     six-months-from-now cost review
    flow-simplify   over-engineering, duplication and missed-reuse review
    flow-qa         Playwright suite author, deterministic or it says so

## Per-task model routing

By default every implementer runs on the session model. To pin a task, add a
`**Model:**` line to its block in `plan.md`:

    **Model:** sonnet

Claude Code dispatches `flow-impl` on that model (`sonnet` or `opus`). opencode
cannot pick a model per dispatch, so the render script generates pinned
`flow-impl-sonnet` and `flow-impl-opus` agents and the build command routes to
them. Choose which provider models they map to when rendering:

    OPENCODE_IMPL_MODELS="sonnet=github-copilot/claude-sonnet-5.5 opus=github-copilot/claude-opus-5.5" \
      bash scripts/render-opencode.sh

In opencode the `**Model:**` line may also carry the full provider model id. An
unknown value stops the build rather than silently substituting a model.

## Rules every phase obeys

The `flow-rules` skill is loaded at the start of each command:

- **Branch**: never shape or plan on main, master, dev, develop or staging.
- **Evidence**: no pass without pasted command output.
- **Tests**: test first; never weaken, skip, or edit a test to reach green.
- **Reuse**: search before writing, then declare `REUSING <path>` or
  `NEW <path>, searched <terms>`.
- **Simplicity**: no new dependency without asking, no abstraction for a use
  case that does not exist yet.
- **Scope**: touch only the files the task names.
- **Worktrees**: scratch worktrees live in the temp directory and are removed
  on every exit path.

Reuse is enforced in three places so it survives a fresh context: the rules
above, a required `**Reuse:**` line per task in `/flow:plan`, and the
`flow-simplify` review, which treats an ignored Reuse line as a High finding.

## Optional TDD guard hook

`flow/hooks/tdd_guard.py` is a PreToolUse hook that blocks writing a Python
source file before a matching test exists. It ships inactive. To enable it,
follow the instructions at the top of the file and set `FLOW_TDD_GUARD=1`.

## Changing flow

The files under `flow/` are the source of truth. Edit them directly.

- Claude Code reads a local-path marketplace from disk; run `/reload-plugins`
  or restart to pick up an edit. For a GitHub install, bump `version` in
  `flow/.claude-plugin/plugin.json`, push, and run
  `/plugin marketplace update flow-local`.
- opencode: re-run `bash scripts/render-opencode.sh` after every edit. It
  deletes and rewrites every `flow-*.md` it owns, so never edit those by hand.
- Check the manifests with `claude plugin validate ./flow` and
  `claude plugin validate .`.

Keep command and agent text engine-neutral: write `/flow:<cmd>` and
`CLAUDE.md`, and the render script translates both for opencode.

## Uninstall

    /plugin uninstall flow@flow-local
    /plugin marketplace remove flow-local
    rm -f ~/.config/opencode/commands/flow-*.md ~/.config/opencode/agents/flow-*.md
