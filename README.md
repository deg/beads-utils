# beads-utils

[![lint](https://github.com/deg/beads-utils/actions/workflows/lint.yml/badge.svg)](https://github.com/deg/beads-utils/actions/workflows/lint.yml)

Tools for working with [`bd`](https://github.com/gastownhall/beads) (the
beads issue tracker) and Claude Code together: see what an agent did to your
beads and what it learned, keep its memory honest and backed up, and have it
follow a workflow instead of improvising one each session.

## Why

When an AI coding agent works your issue tracker for you, three things get
harder to see. **What it did**: a session can create, claim and close half a
dozen beads while you were reading the code, and `bd list` shows you the
result, not the story. **What it learned**: the memories it keeps shape every
later session, nothing shows you their history, and a memory that has gone
false is worse than none. **Whether any of it is safe**: beads data travels on
a git ref GitHub's UI never shows, and Claude Code's memory files aren't
versioned at all.

This repo answers all three with small, single-purpose scripts that read what
is already on your disk, plus a set of Claude Code skills and hooks that carry
a disciplined way of working with beads into the agent itself:

- A git-log for beads *and* memories (`bd-log`), a renderer for long beads
  (`bd-view`), the live-work listing an audit needs (`bd-find-live`), and
  checks that your beads really reached the remote (`bd-dolt-check`,
  `bd-verify-backup -g` for every repo on the machine).
- Session tools: list, find, rename and export Claude Code sessions, spot the
  tool failures that recur across them (`claude-sessions-review`), and watch
  what a running session costs you in bytes.
- A workflow: `/start-task` before code, `/finalize` per bead, `/close-shop` at
  the end of a session, `/defer` to park; two hooks that guard it; and a git
  repo of their own for the memory files, committed at every session end.

![bd-log --oneline](docs/img/bd-log.png)

Everything here is a plain Python 3 script. There is no package to install
and nothing to build: clone the repo, and the scripts run from the clone.

## Install

```bash
git clone https://github.com/deg/beads-utils && cd beads-utils
make install            # symlink the scripts into ~/.local/bin (PREFIX=... for elsewhere)
make install-claude     # symlink the skills and hooks into ~/.claude
make completions        # the line to add to your rc file for tab completion
```

Both install targets make symlinks back to the clone, so an edit takes effect
with no reinstall; `make uninstall` and `make uninstall-claude` remove them.
The hooks still have to be wired into `settings.json` by hand:
[docs/workflow.md](docs/workflow.md#the-hooks) and
[docs/memories.md](docs/memories.md#the-hooks) have the snippets.

`make install` and `make install-claude` check for the tools below and, on a
terminal, offer to install each missing one (`?` at the prompt explains what
it is for); nothing is installed without your yes, and `make doctor` runs the
same check on its own. Besides Python 3, `git` and `make`:

- `bd` — the scripts that read beads through it (`bd-log`, `bd-view`,
  `bd-find-live`, `bd-export-csv`) and the skills.
- `jq` — the hooks; `make install-claude` and `claude-memory-setup` refuse
  without it.
- `uv` — `bd-view`, which renders Markdown with `rich`.
- `dolt` (optional) — the full answers from `bd-dolt-check`, `bd-dolt-diff`
  and `bd-verify-backup`, and `bd-log`'s memory history.
- GNU `timeout` (optional; `coreutils` on macOS) — lets `claim-guard` name
  the beads in progress.

The `claude-session-*` tools need none of these.

## Scripts

| Script | What it does | Docs |
|---|---|---|
| [`bd-log`](bd-log) | Git-log-style timeline of bead *and* memory lifecycle events — created, changed, ended | [§](docs/beads.md#bd-log) |
| [`bd-view`](bd-view) | Pretty-print a single bead with rendered Markdown | [§](docs/beads.md#bd-view) |
| [`bd-find-live`](bd-find-live) | List the beads that are live work — open or in progress, minus those parked behind a deferred bead — as JSON | [§](docs/beads.md#bd-find-live) |
| [`bd-export-csv`](bd-export-csv) | Export the bead database to a flat CSV for spreadsheet review | [§](docs/beads.md#bd-export-csv) |
| [`bd-dolt-check`](bd-dolt-check) | Verify the Dolt data behind a `bd` repo is actually committed and pushed to its git remote | [§](docs/beads.md#bd-dolt-check-and-bd-dolt-diff) |
| [`bd-dolt-diff`](bd-dolt-diff) | Preview what a `bd dolt push` would send: issue-level diff between local and remote Dolt state | [§](docs/beads.md#bd-dolt-check-and-bd-dolt-diff) |
| [`bd-verify-backup`](bd-verify-backup) | Check a repo is fully backed up — nothing uncommitted, every branch pushed, beads pushed; `-g` checks every beads repo on the machine | [§](docs/beads.md#bd-verify-backup) |
| [`claude-session-list`](claude-session-list) | Git-log-style listing of Claude Code sessions (default: current project; `-g` for all) | [§](docs/claude-sessions.md#claude-session-list) |
| [`claude-session-find`](claude-session-find) | Substring search across `~/.claude/projects/*.jsonl` to find old Claude Code sessions | [§](docs/claude-sessions.md#claude-session-find) |
| [`claude-session-report`](claude-session-report) | Render a Claude Code session as a Markdown discussion transcript | [§](docs/claude-sessions.md#claude-session-report) |
| [`claude-session-rename`](claude-session-rename) | Set a Claude Code session's title from the shell, like `/rename`, without starting the session | [§](docs/claude-sessions.md#claude-session-rename) |
| [`claude-sessions-review`](claude-sessions-review) | Find tool calls that fail the same way across many Claude Code sessions, ranked by how many sessions hit them | [§](docs/claude-sessions.md#claude-sessions-review) |
| [`claude-memory-check`](claude-memory-check) | Find broken `[[links]]`, bad slugs and a stale `MEMORY.md` index in Claude Code's memory directories | [§](docs/claude-sessions.md#claude-memory-check) |
| [`claude-memory-setup`](claude-memory-setup) | Give Claude Code's memory files a git repo of their own, fresh or cloned from another machine | [§](docs/memories.md#claude-memory-setup) |
| [`claude-traffic-monitor`](claude-traffic-monitor) | Live `top`-like view of the internet traffic of every running Claude Code session, plus the busiest other processes (macOS) | [§](docs/claude-sessions.md#claude-traffic-monitor) |
| [`bd-complete`](bd-complete) | Emit completion candidates (bead ids, session uuids) — the helper behind shell tab completion | [§](docs/development.md#shell-completion) |

Run any script with `--help` for full usage.

## The beads workflow

Six Claude Code skills, installed by `make install-claude`, answer to their
bare names and read an optional extension file of yours before the project's:

| Skill | Scope | When |
|---|---|---|
| `/start-task` | one task | Before any code: load context, interview, create and claim a bead, plan, wait for a go-ahead |
| `/finalize` | one task | When a bead's work is done: review, tests, gates, a commit you approve, then `bd close` |
| `/close-shop` | the session | Once, at the end: audit every memory and open bead against what changed, then record what was learned |
| `/defer` | one bead | Park without closing, recording the gate for revisiting |
| `/status` | the project | A twenty-line orientation |
| `/changelog` | the repo | A changelog entry since the last tag, in the file's own style |

Two hooks guard it (`claim-guard` asks before a bead is claimed on a dirty
tree; `defer-hint` points the agent at `/defer`), and two more keep the memory
files in a git repo of their own. All of it is in
[docs/workflow.md](docs/workflow.md) and [docs/memories.md](docs/memories.md).

## Essays

Some of the thinking behind these tools, written up at
[degel.com/writing](https://degel.com/writing/):

- [The Slash Command That Knew Too Much](https://degel.com/writing/slash-command-that-knew-too-much/)
  — workflows as programs written in English: the idea behind `/start-task`,
  `/finalize` and their extension files.
- [The Persistence of Memory](https://degel.com/writing/persistence-of-memory/)
  — agent memory files are configuration, not notes, and the configuration now
  writes itself: why the memories get a git repo and a linter.
- [Scheme in a Weekend, or, LLM: The Ultimate Intern](https://degel.com/writing/scheme-in-a-weekend/)
  — a weekend Rust project run on beads, and managing an agent that keeps
  declaring "done".
- [The Comment That Lied](https://degel.com/writing/comment-that-lied/) — four
  of sixteen memories gone stale after the fixes that invalidated them: the
  case for `/close-shop`'s memory audit.

## Documentation

- [docs/beads.md](docs/beads.md) — the tools for looking at beads, with screenshots
- [docs/claude-sessions.md](docs/claude-sessions.md) — the tools for looking at Claude Code sessions and memories
- [docs/workflow.md](docs/workflow.md) — the skills, their extensions, and the two guard hooks
- [docs/memories.md](docs/memories.md) — the memories repo, its hooks, recovery and caveats
- [docs/development.md](docs/development.md) — make targets, the test suite, shell completion, conventions
- [CONTRIBUTING.md](CONTRIBUTING.md), [CLAUDE.md](CLAUDE.md) and the design notes in [.claude/rules/](.claude/rules)

## License

Released under the [MIT License](LICENSE).
