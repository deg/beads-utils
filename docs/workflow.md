# The beads workflow

Seven Claude Code skills and two hooks carry a way of working with beads that
an agent otherwise has to be told every session: a bead is claimed before
code is written, finished with a review and a commit, parked rather than
closed when it has to wait, and the session ends with an audit of what
the work made stale. `make install-claude` links all of them into
`~/.claude`.

## The skills

Once `make install-claude` has linked them into `~/.claude/skills`, they
answer to their bare names. They call `bd-find-live` and
`claude-memory-check` from this repo by name, so run `make install` as
well:

| Skill | Scope | When |
|---|---|---|
| `/start-task` | one task | Before any code: load the beads context, interview, create and claim a bead, read the affected files, propose a plan, wait for a go-ahead |
| `/finalize` | one task | When a bead's work is done: self-review, tests, lint and test until clean, a senior review, a commit you approve, then `bd close`. Once per bead |
| `/close-shop` | the session | Once, at the end: audit every standing memory and every open bead against what the session changed, correct what rotted, and only then record what was learned |
| `/defer` | one bead | Park a bead without closing it, recording the gate for revisiting; never `bd close` to park |
| `/review-titles` | the open beads | Check every title against the title rules and the code, say which are kept, then show the rest one at a time for a one-word answer |
| `/status` | the project | A twenty-line orientation |
| `/changelog` | the repo | A changelog entry for everything since the last tag, in the file's own style |

If you already have commands of the same names under `~/.claude/commands/`,
remove them: both would load. The one that is easy to skip and expensive to
skip is `/close-shop`. Memories
go false when your own work invalidates them, and nothing else ever re-reads
them. Its audit uses `claude-memory-check` and `bd-find-live` from this repo.

## Extensions

Five of the skills (`/start-task`, `/finalize`, `/defer`, `/close-shop`, `/review-titles`) read
an **extension** file and follow it, from two places in order: your own
`~/.claude/skill-extensions/<name>.md`, for conventions and standing
permissions that hold in every project, then the project's
`.claude/skill-extensions/<name>.md`, for its own steps (regenerate API types,
always check a particular document). The skills themselves grant nothing:
`/close-shop` asks before `git push` and `bd dolt push` unless your extension
says it may. The one push it does not ask about is the memories repo's, made
through the SessionEnd hook, which pushes whenever you have given that repo
an upstream: the same push happens at the end of every session, and the
upstream you configured is the consent for it.

## The hooks

Two hooks hold the line the workflow depends on. `claim-guard.sh` runs
before every Bash command: when the command claims a bead (`bd update <id>
--claim`) while the git tree holds uncommitted work, it turns the claim into
a permission prompt naming the dirty paths and the beads in progress. The
rule is one bead, one commit, at the boundary, and claiming the next bead is
the one deterministic step an agent takes on the way to breaking it. It
asks rather than denies, because a dirty tree may be another agent's work.
`defer-hint.sh` runs on every prompt and, when you ask to park a bead in
your own words ("shelve that ticket"), injects a single line pointing the
agent at `/defer`, because the failure mode is an agent that parks with `bd
close` and loses the bead. Neither prints anything otherwise. Both need
`jq`; install them with `make install-claude` and wire them in:

```json
"hooks": {
  "PreToolUse":       [{"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"$HOME/.claude/hooks/claim-guard.sh\""}]}],
  "UserPromptSubmit": [{"matcher": "",     "hooks": [{"type": "command", "command": "bash \"$HOME/.claude/hooks/defer-hint.sh\""}]}]
}
```

The two hooks that keep the memory files versioned are in
[memories.md](memories.md).
