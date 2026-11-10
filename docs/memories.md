# Keeping Claude Code memories

Claude Code's auto-memory is a directory of Markdown files per project under
`~/.claude/projects/`, next to the session transcripts, and nothing versions
it: a memory that goes false and gets rewritten, or deleted by mistake, is
simply gone. `claude-memory-setup` gives those files a git repository of
their own, and two hooks keep it current.

## claude-memory-setup

The repo's `.git` lives outside (`~/claude-memories.git` by
default, or `$CLAUDE_MEMORIES_GIT`) and its work tree *is* the projects
directory, so the only thing added there is one `.gitignore`. That file is
an allowlist — ignore everything, then re-include exactly `*/memory/*.md` —
so a missed pattern can only hide a memory, never leak a transcript, which
holds everything ever pasted into a session.

```bash
claude-memory-setup                                  # a fresh repo; first commit = allowlist + current memories
claude-memory-setup --remote git@github.com:me/claude-memories.git   # a new machine: clone and track
make install-claude                                  # link hooks/*.sh into ~/.claude/hooks
```

## The hooks

Two hooks keep it current, once wired into `~/.claude/settings.json`:

```json
"hooks": {
  "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "bash \"$HOME/.claude/hooks/check-memories-pushed.sh\""}]}],
  "SessionEnd":   [{"matcher": "", "hooks": [{"type": "command", "command": "bash \"$HOME/.claude/hooks/commit-memories.sh\""}]}]
}
```

`commit-memories.sh` commits whatever changed at the end of every session,
naming the session and directory in the message, and pushes if the branch has
an upstream. It fails closed: if anything but a memory file is visible to git
(the allowlist edited, a transcript showing through) it refuses the whole
commit and records why, because it pushes, and a transcript pushed is a
transcript published. It also refuses to commit more than twenty deletions at
once. `check-memories-pushed.sh` is the backstop at session start: it shows a
recorded refusal, a missing upstream, or commits that have sat unpushed for a
day, as a message to you rather than context for the agent.

## Recovering a memory

To recover a deleted
memory, find the deleting commit and take the file from its parent:
`git -C ~/.claude/projects --git-dir=$HOME/claude-memories.git log
--diff-filter=D -1 --format=%h -- <project>/memory/<file>.md`, then
`checkout <that>^ -- <project>/memory/<file>.md` with the same prefix.

## Caveats

Make the remote **private**: memories routinely hold client names, paths and
whatever else a session learned about your work. The hooks need `jq`, and
`claude-memory-setup` refuses to run without it. One machine writes at a time: the hooks push but never fetch or merge, so if two
machines commit before pulling, every push from the second is rejected. The
SessionStart hook says so as soon as it happens, and the fix is by hand:
`git -C ~/.claude/projects --git-dir=$HOME/claude-memories.git pull --rebase`.
