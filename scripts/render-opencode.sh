#!/usr/bin/env bash
#
# render-opencode.sh
#
# Renders the opencode copies of the flow plugin from the plugin files in
# ../flow, which are the single source of truth. Run it again after every edit
# to a command or agent. Never edit the rendered files by hand.
#
# Mechanical transform only:
#   commands  frontmatter -> description + "agent: build";  /flow:x -> /flow-x
#   agents    frontmatter -> description + mode + permission derived from tools
#   body      CLAUDE.md   -> AGENTS.md or CLAUDE.md
#   routing   opencode cannot pick a model per dispatch, so each entry in
#             OPENCODE_IMPL_MODELS becomes a pinned flow-impl-<alias> agent and
#             the build command's **Model:** table points at those agents.
#
# This script owns every flow-*.md under $OPENCODE_ROOT/{commands,agents}: they
# are deleted and rewritten on each run. Nothing else there is touched.
#
# Environment variables:
#   OPENCODE_ROOT         opencode config dir   (default: $HOME/.config/opencode)
#   OPENCODE_MODEL        model: line for every flow subagent (default: unset,
#                         subagents inherit the session model)
#   OPENCODE_IMPL_MODELS  space-separated alias=model pairs for per-task routing
#                         (default: sonnet=github-copilot/claude-sonnet-5.5
#                                   opus=github-copilot/claude-opus-5.5)
#                         set to "" to render no pinned implementers
#
set -euo pipefail

PLUGIN="$(cd "$(dirname "$0")/../flow" && pwd)"
OPENCODE_ROOT="${OPENCODE_ROOT:-$HOME/.config/opencode}"
OPENCODE_MODEL="${OPENCODE_MODEL-}"
OPENCODE_IMPL_MODELS="${OPENCODE_IMPL_MODELS-sonnet=github-copilot/claude-sonnet-5.5 opus=github-copilot/claude-opus-5.5}"

strip_frontmatter() { awk 'BEGIN{n=0} /^---$/ && n<2 {n++; next} n>=2 {print}' "$1"; }
field() { sed -n "s/^$2: //p" "$1" | head -1; }
to_opencode() { sed -e 's|/flow:|/flow-|g' -e 's|CLAUDE\.md|AGENTS.md or CLAUDE.md|g'; }

# render_agent <source file> <output name> <model, may be empty> [description suffix]
render_agent() {
  local src=$1 name=$2 model=$3 note=${4-} tools ed bs
  tools=$(field "$src" tools)
  case "$tools" in *Write*|*Edit*) ed=allow;; *) ed=deny;; esac
  case "$tools" in *Bash*)         bs=allow;; *) bs=deny;; esac
  {
    echo "---"
    echo "description: $(field "$src" description)$note"
    echo "mode: subagent"
    if [ -n "$model" ]; then echo "model: $model"; fi
    echo "permission:"
    echo "  edit: $ed"
    echo "  bash: $bs"
    echo "---"
    strip_frontmatter "$src"
  } | to_opencode > "$OPENCODE_ROOT/agents/$name.md"
}

echo "==> Rendering opencode files into $OPENCODE_ROOT"
mkdir -p "$OPENCODE_ROOT/commands" "$OPENCODE_ROOT/agents"
rm -f "$OPENCODE_ROOT"/commands/flow-*.md "$OPENCODE_ROOT"/agents/flow-*.md

for f in "$PLUGIN"/commands/*.md; do
  {
    echo "---"
    echo "description: $(field "$f" description)"
    echo "agent: build"
    echo "---"
    strip_frontmatter "$f"
  } | to_opencode > "$OPENCODE_ROOT/commands/flow-$(basename "$f")"
done

for f in "$PLUGIN"/agents/*.md; do
  render_agent "$f" "$(basename "$f" .md)" "$OPENCODE_MODEL"
done

# Per-task model routing: one pinned implementer per alias, and the build
# command's Claude Code routing rows replaced by rows naming those agents.
routes=""
for pair in $OPENCODE_IMPL_MODELS; do
  alias=${pair%%=*}
  model=${pair#*=}
  render_agent "$PLUGIN/agents/flow-impl.md" "flow-impl-$alias" "$model" " Pinned to $model."
  routes="$routes       - $alias or $model -> flow-impl-$alias\n"
done

build="$OPENCODE_ROOT/commands/flow-build.md"
awk -v routes="$routes" '
  /^ +- [a-z0-9]+ -> flow-impl, dispatched on the / {
    if (!done) { printf "%s", routes; done = 1 }
    next
  }
  { print }
  END { if (!done) exit 1 }
' "$build" > "$build.tmp" || {
  rm -f "$build.tmp"
  echo "ERROR: model routing rows not found in flow/commands/build.md"; exit 1
}
mv "$build.tmp" "$build"

echo "==> Validating"
for f in "$OPENCODE_ROOT"/commands/flow-*.md "$OPENCODE_ROOT"/agents/flow-*.md; do
  test -s "$f" || { echo "ERROR: $f is empty"; exit 1; }
done
if grep -l '/flow:' "$OPENCODE_ROOT"/commands/flow-*.md "$OPENCODE_ROOT"/agents/flow-*.md; then
  echo "ERROR: the files above still contain /flow: syntax"; exit 1
fi
echo "    $(ls "$OPENCODE_ROOT"/commands/flow-*.md | wc -l | tr -d ' ') commands, $(ls "$OPENCODE_ROOT"/agents/flow-*.md | wc -l | tr -d ' ') agents"

# The flow-rules skill is shared, not copied. Check opencode can see it.
OC_JSON="$OPENCODE_ROOT/opencode.json"
if ! grep -q 'flow.*skills' "$OC_JSON" 2>/dev/null; then
  echo
  echo "NOTE: add the flow skills directory to skills.paths in $OC_JSON"
  echo "      so the flow-rules skill loads:"
  echo "        $PLUGIN/skills"
fi
echo "Restart opencode and type /flow- to confirm."
