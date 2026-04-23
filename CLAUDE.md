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

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## What This Is

A collection of standalone utility scripts that augment the **beads** (`bd`) issue tracker
and its Dolt-backed storage. Each script is a single self-contained executable at the
repo root — there is no package, no build step, and no installer. To use, run them in
place or symlink into `~/bin/`.

Current scripts:

- `bd-export-csv` — Python 3 CLI. Shells out to `bd export --all --no-memories`, parses
  the JSONL, and writes a flat CSV suitable for spreadsheet review. Supports
  `--sortby` with comma-separated keys and `-`-prefixed descending order.
- `dolt-remote-check` — Bash script. Verifies that a beads repo's Dolt data (stored under
  `refs/dolt/data` on the git remote, invisible in GitHub's UI) has actually been pushed.
  Compares `.beads/push-state.json` against `git ls-remote` and the local
  `.dolt/repo_state.json` / `dolt log`.

Both scripts accept an optional project path argument (default: cwd) and print a
user-facing summary to stdout / errors to stderr with non-zero exit on failure.

## Running & Testing

No build system. There are no automated tests — verify manually against a real beads
project (this repo itself is one):

```bash
./bd-export-csv .                             # Export this repo to CSV in cwd
./bd-export-csv . --sortby=-priority,created_at
./dolt-remote-check .                          # Check Dolt sync state
```

The `dolt-remote-check` script assumes the `dolt` CLI is installed for its richest output
but degrades gracefully when it isn't. `bd-export-csv` requires only Python 3 stdlib and
`bd` on `PATH`.

## Conventions

- **Shebangs**: `#!/usr/bin/env python3` and `#!/usr/bin/env bash` — no hardcoded paths.
- **Bash scripts**: always `set -euo pipefail` at the top.
- **Python**: `from __future__ import annotations`; stdlib only; no third-party deps.
- **Argument parsing**: Python uses `argparse`; Bash uses a manual `case` block with
  `-h|--help` support and a `show_help()` heredoc.
- **Errors**: exit with a non-zero code and a short `error:` / `Error:` prefixed message
  to stderr — do not raise tracebacks.
- **No config files, no state** beyond what `bd` / Dolt already manage under `.beads/`.
