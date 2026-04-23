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
- `dolt-remote-check` — Verifies that a beads repo's Dolt data (stored under
  `refs/dolt/data` on the git remote, invisible in GitHub's UI) has actually been
  pushed. Compares `.beads/push-state.json` against `git ls-remote` and the local
  `.dolt/repo_state.json` / `dolt log`. Exits 1 on OUT OF SYNC so CI can gate on it.
- `bd-log` — Shows recently closed beads in a git-log-style view. Wraps
  `bd list --status=closed --sort=closed --reverse --json`. Supports `-n/--limit`
  (default 10) and `--since DATE` (passed through as `--closed-after`).

Shared helper:

- `bdutils.py` — `error()`, `warn()`, and `resolve_project_path()`. Imported by every
  script; keep small and stdlib-only.

All scripts accept an optional project path argument (default: cwd) and print a
user-facing summary to stdout / errors to stderr with non-zero exit on failure.

## Running & Testing

No build system. There are no automated tests — verify manually against a real beads
project (this repo itself is one):

```bash
./bd-export-csv .                             # Export this repo to CSV in cwd
./bd-export-csv . --sortby=-priority,created_at
./dolt-remote-check .                          # Check Dolt sync state
./bd-log                                       # Last 10 recently closed beads
./bd-log -n 25 --since 2026-04-01              # 25 closures on/after date
```

`dolt-remote-check` assumes the `dolt` CLI is installed for its richest output but
degrades gracefully when it isn't. All scripts require only Python 3 stdlib and `bd`
on `PATH`.

## Conventions

- **Shebang**: `#!/usr/bin/env python3` — no hardcoded paths.
- **Python**: `from __future__ import annotations`; stdlib only; no third-party deps.
- **Argument parsing**: `argparse`. Use `RawDescriptionHelpFormatter` with
  `description=` and `epilog=` when a richer help block is warranted.
- **Errors**: use `bdutils.error(msg)` — exits non-zero with a lowercase `error: ...`
  line to stderr. Never raise tracebacks at the top level.
- **Warnings**: use `bdutils.warn(msg)` — writes `warning: ...` to stderr without exit.
- **Project path**: use `bdutils.resolve_project_path(arg)` for the expanduser/resolve/
  `.beads/`-validation dance.
- **Subprocess**: pass `cwd=project_path` rather than `os.chdir`. Use `check=True` only
  for calls that must succeed; tolerate empty/missing output where it's a valid state.
- **No config files, no state** beyond what `bd` / Dolt already manage under `.beads/`.
