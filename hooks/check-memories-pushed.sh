#!/bin/bash
# SessionStart hook: tell the user when Claude Code memories are not reaching the remote.
#
# commit-memories.sh commits and pushes the memories repo ($CLAUDE_MEMORIES_GIT, default
# ~/claude-memories.git) at every session end, and its failures are silent by design: a
# guard refusal, a broken key, a passphrase BatchMode refused, a remote that went away, a
# push rejected because another machine pushed first. This is the backstop. It checks
# only local state, so it costs nothing offline. It reports the first of, in order: no
# repo, a guard refusal (repeated at every session end until fixed, so shown at once), a
# rejected push (same: it repeats until someone pulls), no upstream (so nothing is ever
# pushed), and commits unpushed for over a day. A younger commit is not worth a warning,
# since the next session end retries it; @{upstream} moves only when a push succeeds.
#
# Output is a systemMessage, shown to the user, not context for the agent. Needs jq,
# which claude-memory-setup checks for.

GITDIR=${CLAUDE_MEMORIES_GIT:-$HOME/claude-memories.git}
git() { command git --git-dir="$GITDIR" "$@"; }
say() { jq -n --arg m "claude-memories: $1" '{systemMessage: $m}'; exit 0; }

[ -d "$GITDIR" ] || say "$GITDIR is missing, so memory files have no history. Run claude-memory-setup."
WORKTREE=$(git config core.worktree 2>/dev/null)
INSPECT="git -C $WORKTREE --git-dir=$GITDIR"
[ -f "$GITDIR/last-refusal" ] &&
  say "the SessionEnd hook refused to commit: $(cat "$GITDIR/last-refusal"). Inspect: $INSPECT status -uall"
[ -f "$GITDIR/last-push.log" ] && grep -q -E 'rejected|non-fast-forward|fetch first' "$GITDIR/last-push.log" &&
  say "the last push was rejected: another machine pushed first. Fix by hand: $INSPECT pull --rebase, then $INSPECT push. Log: $GITDIR/last-push.log"
git rev-parse -q --verify '@{upstream}' >/dev/null 2>&1 ||
  say "main has no upstream, so nothing is pushed. Fix: $INSPECT branch -u origin/main main"

OLDEST=$(git log --reverse --format=%ct '@{upstream}..HEAD' 2>/dev/null | head -1)
[ -n "$OLDEST" ] || exit 0
AGE=$(( $(date +%s) - OLDEST ))
[ "$AGE" -gt 86400 ] || exit 0

N=$(git rev-list --count '@{upstream}..HEAD')
say "$N commit(s) not pushed, oldest $((AGE / 3600))h old. Last push attempt: $GITDIR/last-push.log"
