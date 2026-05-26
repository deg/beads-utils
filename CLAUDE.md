# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

When ending a work session:

1. **File issues for remaining work** — create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) — tests, linters, builds
3. **Update issue status** — close finished work, update in-progress items
4. **Commit** — stage and commit your changes
5. **Hand off** — provide context for next session

Pushing (`git push` / `bd dolt push`) is the user's call, not the agent's. Commit, then ask — do not push autonomously.
<!-- END BEADS INTEGRATION -->


## What This Is

A small collection of Python utility scripts that augment the **beads** (`bd`) issue
tracker and its Dolt-backed storage. Each script sits at the repo root alongside a
shared `bdutils.py` helper module — no package, no build step, no installer. Scripts
are expected to run from the repo directory (Python's default `sys.path[0]` resolves
the sibling `bdutils` import).

Current scripts:

- `bd-export-csv` — Shells out to `bd export --all --no-memories`, parses the JSONL,
  and writes a flat CSV suitable for spreadsheet review. Supports `--sortby` with
  comma-separated keys and `-`-prefixed descending order.
- `bd-dolt-check` — Verifies that a beads repo's Dolt data (stored under
  `refs/dolt/data` on the git remote, invisible in GitHub's UI) has actually been
  pushed. Compares `.beads/push-state.json` against `git ls-remote` and the local
  `.dolt/repo_state.json` / `dolt log`. Exits 1 on OUT OF SYNC so CI can gate on it.
- `bd-log` — Shows recently closed beads in a git-log-style view. Wraps
  `bd list --status=closed --sort=closed --json` (newest first). Supports
  `-n/--limit` (default 0 = unlimited, like `git log`) and `--since DATE`
  (passed through as `--closed-after`). Pages through `bdutils.paged_output()`
  (`$PAGER` or `less -FRX` when stdout is a tty). `--no-pager` disables.
- `claude-session-find` — Finds the UUID of an old Claude Code session by
  grepping its transcript. Reads `~/.claude/projects/<mangled-cwd>/<uuid>.jsonl`
  (mangling = `/` and `.` → `-`). Defaults to the current project and
  human-typed user messages only; `-g/--global` spans all projects,
  `-a/--all` also searches assistant text, thinking, and tool inputs/outputs.
  Git-log-style output with timestamp, project label, full UUID, match count,
  and up to 3 snippets per session; `-q/--quiet` prints only UUIDs
  (pipe-friendly for `claude --resume`). Pages via `bdutils.paged_output()`.
- `bd-view` — Pretty-prints a single bead with rendered Markdown. Where `bd
  show` dumps fields as plain text and `bd edit` shows raw markdown one
  section at a time, this renders the full bead (header metadata,
  description, design, notes, acceptance criteria, dependencies, comments)
  with proper formatting via the `rich` library. Subclasses
  `rich.markdown.Markdown` to disable raw HTML so placeholder text like
  `<id>` survives. Single positional arg: `bd-view <issue-id>`. Pages via
  `bdutils.paged_output()`; `--no-pager` disables. Falls back to a
  plain-text dump (with a `warning:`) if `rich` isn't installed.
  Shebang is `#!/usr/bin/env -S uv run --script` with PEP 723 inline
  metadata declaring `rich` + `markdown-it-py`, so deps come from `uv`'s
  per-script cached venv — nothing is added to any global Python env.
  Requires `uv` on `PATH`.
- `claude-session-report` — Renders a Claude Code session JSONL as a
  Markdown discussion transcript. Each emitted item is its own H2
  section (`## User — ts`, `## /cmd-name — ts`, `## Claude — ts`,
  `## Claude thinking — ts`, `## Claude tool: <name> — ts`, …); ATX
  headings inside content are demoted by 2 levels (capped at h6) so
  they nest cleanly under the turn header. Long boilerplate (thinking,
  slash-command skill bodies) is wrapped in `<details>` so GitHub
  viewers collapse them. Fence lengths in code blocks adapt to nested
  backtick runs in the content. Pages via `bdutils.paged_output()`;
  `--no-pager` disables.
  Positional arg resolves in order: (1) path to a `.jsonl` file, (2)
  UUID — `<uuid>.jsonl` lookup across every `~/.claude/projects/*/`
  dir, (3) case-insensitive substring match against the session's
  `custom-title` (set via `/rename`) or auto `ai-title`; ambiguous
  matches list candidates and exit non-zero.
  Each content category is an independent toggle. Default-on (the
  "discussion"): `--prompts`, `--replies`, `--slash-commands`.
  Default-off (opt-in): `--thinking`, `--tools`, `--slash-bodies`,
  `--bash-shortcuts`, `--system-reminders`, `--task-notifications`,
  `--sidechains`. `--all` enables every channel.
  Skill bodies — the boilerplate Claude Code appends as a *child* user
  entry of a slash-command turn (identified by `parentUuid`) — are
  hidden by default because they repeat verbatim across every
  invocation of the same skill; `--slash-bodies` brings them back.
  Note: Claude Code does not currently persist extended-thinking
  content to disk (only the signature), so `--thinking` is
  forward-compatible but produces no output for current sessions.

Shared helper:

- `bdutils.py` — `error()`, `warn()`, `resolve_project_path()`,
  `format_ts()`, `format_priority()`, and `paged_output()` (context manager
  that pipes through `$PAGER` or `less -FRX` when stdout is a tty; `-F` makes
  short output indistinguishable from direct-to-stdout). Imported by scripts
  in this repo; keep small and stdlib-only.

Most scripts accept an optional project path argument (default: cwd) and print a
user-facing summary to stdout / errors to stderr with non-zero exit on failure.
Exceptions: `bd-view` takes an issue id (and relies on `bd`'s own `.beads/`
auto-discovery from the current directory); `claude-session-report` takes a
Claude session UUID, title substring, or `.jsonl` path.

## Running & Testing

No build system. There are no automated tests — verify manually against a real beads
project (this repo itself is one):

```bash
./bd-export-csv .                             # Export this repo to CSV in cwd
./bd-export-csv . --sortby=-priority,created_at
./bd-dolt-check .                             # Check Dolt sync state
./bd-log                                       # Last 10 recently closed beads
./bd-log -n 25 --since 2026-04-01              # 25 closures on/after date
./claude-session-find 'bd-log'                 # Sessions in this project matching
./claude-session-find -g 'paged_output'        # All projects
./claude-session-find -a 'dolt push'           # Include assistant/tool content
./claude-session-find -q foo | head -1         # UUID only (for `claude --resume`)
./bd-view beads-utils-s4s                      # Pretty-print a single bead
./claude-session-report <uuid>                 # Default discussion-only render
./claude-session-report 'bd-view'              # Substring-match a session title
./claude-session-report <uuid> --thinking --tools     # Add agent thinking + tool I/O
./claude-session-report <uuid> --all > session.md     # Everything, to a file
```

`bd-dolt-check` assumes the `dolt` CLI is installed for its richest output but
degrades gracefully when it isn't. `bd-view` requires `uv` on `PATH` — its shebang
is `#!/usr/bin/env -S uv run --script` and PEP 723 inline metadata declares the
`rich` + `markdown-it-py` deps, which uv resolves into a per-script cached venv
(no global Python install touched). All other scripts require only Python 3 stdlib
and `bd` on `PATH`.

## Conventions

- **Shebang**: `#!/usr/bin/env python3` — no hardcoded paths.
- **Python**: `from __future__ import annotations`; stdlib only by default. Third-party
  deps allowed where they're load-bearing for the script's purpose (e.g. `bd-view`
  needs `rich` for Markdown rendering); `bdutils.py` itself stays stdlib-only.
- **Argument parsing**: `argparse`. Use `RawDescriptionHelpFormatter` with
  `description=` and `epilog=` when a richer help block is warranted.
- **Versioning**: all scripts share a single `bdutils.__version__`; add the
  `--version` flag via `bdutils.add_version_arg(parser)` so every script prints
  `<prog> <version>` identically. Paging scripts also accept `--no-pager`.
- **Errors**: use `bdutils.error(msg)` — exits non-zero with a lowercase `error: ...`
  line to stderr. Never raise tracebacks at the top level.
- **Warnings**: use `bdutils.warn(msg)` — writes `warning: ...` to stderr without exit.
- **Project path**: use `bdutils.resolve_project_path(arg)` for the expanduser/resolve/
  `.beads/`-validation dance.
- **Subprocess**: pass `cwd=project_path` rather than `os.chdir`. Use `check=True` only
  for calls that must succeed; tolerate empty/missing output where it's a valid state.
- **No config files, no state** beyond what `bd` / Dolt already manage under `.beads/`.
