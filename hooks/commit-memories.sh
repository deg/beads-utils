#!/bin/bash
# SessionEnd hook: give Claude Code auto-memory files git history, and keep it offsite.
#
# The memories have a repo of their own, created by claude-memory-setup: its .git is
# $CLAUDE_MEMORIES_GIT (default ~/claude-memories.git) and its core.worktree is
# ~/.claude/projects, where Claude Code writes them, so every git command here needs only
# --git-dir. The allowlist .gitignore at the top of the work tree exposes only
# <slug>/memory/*.md to git. Nothing else commits those files, so without this hook a new
# project's memories would sit untracked forever and a wrong delete would still be
# unrecoverable. This runs at the end of EVERY session on the machine.
#
# Usage:  commit-memories.sh [commit message]     (hook JSON on stdin, may be empty)
# /close-shop calls it with a message saying what the audit did, so its commit goes
# through the same guard as the automatic one instead of a bare `git add`.
#
# Built to run unattended:
#   - Commits, then pushes if the branch has an upstream -- THIS repo only. It never
#     fetches or merges: one machine writes at a time, and a rejected push is reported
#     by check-memories-pushed.sh for the user to resolve by hand.
#   - Silent when there is nothing to do, and exits 0 no matter what: a hook failure must
#     never turn into a session-end error.
#
# SessionEnd stdout is not injected into context, so output only matters for logs. The
# last push's output is kept in $GITDIR/last-push.log, and the reason for the latest
# guard refusal in $GITDIR/last-refusal (deleted once a run passes the guard).
# check-memories-pushed.sh shows that file at SessionStart, and warns when commits have
# sat unpushed for a day.

GITDIR=${CLAUDE_MEMORIES_GIT:-$HOME/claude-memories.git}
git() { command git --git-dir="$GITDIR" "$@"; }

WORKTREE=$(git config core.worktree 2>/dev/null) || exit 0
cd "$WORKTREE" 2>/dev/null || exit 0

# Bail out of a half-finished merge or rebase rather than commit into it.
for state in MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD; do
  [ -e "$GITDIR/$state" ] && exit 0
done

# Fail closed. The allowlist .gitignore is the only thing keeping transcripts out of
# git; if it is ever deleted or mangled, the next session end must NOT be the moment
# 1 GB of everything-ever-pasted becomes permanent history -- and, since this hook
# pushes, copied to the remote too. Refuse the whole commit if even one visible path
# is not a memory file (or an edit to the .gitignore itself; deleting it is refused,
# since a missing allowlist may only look safe while no transcript is visible). A
# refusal skips only the commit: what is already committed still gets pushed, and the
# reason is recorded, because a refusal repeats at every session end until someone
# fixes the cause.
# A memory file is exactly <one segment>/memory/<one segment>.md, matched with an
# anchored regex rather than a case pattern: in a pattern `*` matches `/` too, so
# `*/memory/*.md` would have accepted a/b/memory/c.md and p/memory/d/e.md.
# -z: NUL-separated and unquoted, so a name with a space or non-ASCII char is not
# wrapped in quotes that would fail the pattern. A rename/copy record is followed by
# a second NUL-terminated record holding the OLD path; the new path is the one that
# gets committed, so the old one is read and dropped.
# Also refuse a mass deletion: the work tree coming up empty or replaced would otherwise
# be committed and pushed as "every memory deleted". Moving a whole store (10 files) is
# the largest legitimate delete seen so far; past this, commit by hand.
MAX_DELETES=20
REFUSED=
ANY=0
DELETES=0
while IFS= read -r -d '' entry; do
  xy=${entry:0:2}
  p=${entry:3}
  case "$xy" in R*|C*) IFS= read -r -d '' _old ;; esac
  if [ "$p" = .gitignore ]; then
    case "$xy" in *D*) REFUSED="the allowlist .gitignore is deleted"; break ;; esac
  elif [[ ! $p =~ ^[^/]+/memory/[^/]+\.md$ ]]; then
    REFUSED="a non-memory path is visible: $p"; break
  fi
  case "$xy" in *D*) DELETES=$((DELETES + 1)) ;; esac
  ANY=1
done < <(git status --porcelain -z -uall 2>/dev/null)
[ -z "$REFUSED" ] && [ "$DELETES" -gt "$MAX_DELETES" ] &&
  REFUSED="$DELETES memory files deleted at once (limit $MAX_DELETES); commit them by hand"

if [ -n "$REFUSED" ]; then
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M')" "$REFUSED" >"$GITDIR/last-refusal"
else
  rm -f "$GITDIR/last-refusal"
fi

if [ -z "$REFUSED" ] && [ "$ANY" = 1 ]; then
  # Name the session in the message so `git log` on a memory file says where it came from.
  MSG=$1
  if [ -z "$MSG" ]; then
    INPUT=$(cat)
    SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null | cut -c1-8)
    CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
    case "$CWD" in "$HOME"|"$HOME"/*) CWD="~${CWD#"$HOME"}" ;; esac   # abbreviate; a bare ~ in ${var/…/~} would expand
    MSG="Snapshot Claude Code memories at session end"
    [ -n "$CWD" ] && MSG="$MSG ($CWD"
    [ -n "$SESSION" ] && MSG="$MSG, session $SESSION"
    [ -n "$CWD" ] && MSG="$MSG)"
  fi
  git add -A 2>/dev/null && git commit -q -m "$MSG" >/dev/null 2>&1
fi

# Push anything unpushed, including commits an earlier, failed push left behind. Detached
# (setsid via perl, which macOS has and setsid(1) it does not), because a SessionEnd hook
# gets only a moment before Claude Code exits. BatchMode makes a key that wants a
# passphrase fail at once instead of waiting forever on a prompt nobody will see.
if [ -n "$(git rev-list -1 '@{upstream}..HEAD' 2>/dev/null)" ]; then
  GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=20' \
    nohup perl -MPOSIX -e 'setsid(); exec @ARGV' -- \
      git --git-dir="$GITDIR" push -q origin HEAD \
      </dev/null >"$GITDIR/last-push.log" 2>&1 &
fi

exit 0
