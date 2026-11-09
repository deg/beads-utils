#!/bin/bash
# PreToolUse hook (matcher: Bash): when a command claims a bead (`bd update <id> --claim`)
# while the git tree already holds uncommitted work, turn the claim into a permission
# prompt instead of letting it pass silently.
#
# House rule: one bead, one commit, at the boundary. An agent that reaches green on one
# bead and starts the next without committing is the failure this catches (seen once as
# six beads and thirty files uncommitted at the end of a session). Claiming the next bead
# is the one deterministic step on that path, so this is where the tripwire sits.
#
# "ask", not "deny": several agents may share one repo, so a dirty tree may be another
# agent's work. The user decides; the agent cannot. Under the PreToolUse contract an
# "ask" reason and the systemMessage both go to the USER; what reaches the agent is
# additionalContext, so the same text is sent there too, or the agent would only see
# that its command needs permission and not what to do about it.
#
# Prints nothing (no decision, normal flow) unless a claim meets a dirty tree, so it costs
# zero context in ordinary sessions. Needs jq.

IN=$(cat)
# Newlines become spaces so a command continued over lines is one line to grep.
CMD=$(printf '%s' "$IN" | jq -r '.tool_input.command // empty' | tr '\n' ' ')
# `bd` at a word start, then zero or more whole tokens (a global flag before the
# subcommand), then `update`, then anything, then `--claim` followed by a non-word
# character or the end: a space, or a shell separator such as `;`, `&`, `)`.
# A command that merely QUOTES a claim matches too; that costs one needless prompt,
# which an "ask" can afford, where a quote-aware pattern could not be trusted.
printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_-])bd([[:space:]]+[^[:space:]]+)*[[:space:]]+update[[:space:]]+.*--claim([^A-Za-z0-9_-]|$)' || exit 0

ROOT=${CLAUDE_PROJECT_DIR:-$(printf '%s' "$IN" | jq -r '.cwd // empty')}
[ -n "$ROOT" ] || exit 0
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# .beads/ is bd's own bookkeeping (the issues.jsonl export), not a bead's work. It goes
# dirty from closing or filing beads and by house rule rides along in the next work
# commit, so it never signals an unfinished bead. Porcelain may quote paths, hence '"?'.
# --no-optional-locks: a plain `status` refreshes the index under index.lock, which in a
# repo several agents share could fail another agent's commit at that instant.
DIRTY=$(git --no-optional-locks -C "$ROOT" status --porcelain 2>/dev/null | grep -Ev '^.. "?\.beads/')
[ -n "$DIRTY" ] || exit 0

N=$(printf '%s\n' "$DIRTY" | wc -l | tr -d ' ')
LIST=$(printf '%s\n' "$DIRTY" | head -6 | sed 's/^...//' | paste -sd ' ' -)
[ "$N" -gt 6 ] && LIST="$LIST ..."

# Name the beads in progress as candidates, never as the files' owner: every agent claims
# under the same assignee, so a match cannot be proven. Epics are dropped (always in
# progress). Bounded by a timeout so a Dolt lock cannot stall every claim; any failure or
# missing tool just omits the clause.
WIP=""
TO=$(command -v timeout || command -v gtimeout)
if [ -n "$TO" ] && command -v bd >/dev/null 2>&1; then
  IDS=$(cd "$ROOT" && "$TO" 3 bd list --status in_progress --json 2>/dev/null |
    jq -r '[.[] | select(.issue_type != "epic") | .id] | (.[:4] | join(", ")) + (if length > 4 then " and more" else "" end)' 2>/dev/null)
  [ -n "$IDS" ] && WIP=" In progress right now: $IDS."
fi

REASON="claim-guard: claiming a new bead while $N path(s) are uncommitted ($LIST).$WIP Rule: one bead, one commit, at the boundary. If these are the previous bead's work, present its commit for approval first and do not claim yet. If another agent owns them, tell the user so."

jq -n --arg r "$REASON" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "ask",
    permissionDecisionReason: $r,
    additionalContext: $r
  },
  systemMessage: $r
}'
exit 0
