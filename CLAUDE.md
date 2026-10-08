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
shared `bdutils.py` helper module — no package, no build step. Scripts run from the
repo directory (Python's default `sys.path[0]` resolves the sibling `bdutils`
import), or from anywhere via the symlinks `make install` puts in `PREFIX`, since
`sys.path[0]` is the *resolved* directory and the sibling import survives the link.

Current scripts:

- `bd-export-csv` — Shells out to `bd export --all --no-memories`, parses the JSONL,
  and writes a flat CSV suitable for spreadsheet review. Supports `-s/--sort` with
  comma-separated keys and `-`-prefixed descending order.
- `bd-dolt-check` — Verifies that a beads repo's Dolt data is committed *and*
  pushed. The Dolt data lives under `refs/dolt/data` on the beads remote
  (the Dolt database's own remote, else `sync.remote`, else the git origin),
  invisible in GitHub's UI. It checks that ref with `git ls-remote`, compares
  the local Dolt branch with its remote-tracking ref, and reads the Dolt working set
  (`dolt_status`) for tables changed but in no commit. Exits 1 on `OUT OF
  SYNC` or `UNCOMMITTED` so CI can gate on it.
- `bd-dolt-diff` — Previews what a `bd dolt push` would send: an issue-level
  diff between the remote-tracking ref and the local branch. `--base`/`--head`
  diff any two Dolt revisions. Read-only, exits 0 whenever the comparison ran.
  Requires the `dolt` CLI.
- `bd-verify-backup` — Is everything on GitHub? Per repo: no uncommitted
  files or stashes, every local branch has an upstream and is not ahead of
  it, and the beads data is committed and pushed (`bdutils.dolt_sync_state()`,
  the same computation `bd-dolt-check` renders). `-g/--global` checks every
  beads repo on the machine in parallel, one line each. Fetches first unless
  `--no-fetch`. Never runs `bd`. Exits 1 if anything is not backed up.
- `bd-log` — Git-log-style timeline of bead *and* memory lifecycle events,
  newest first. `--only` picks the verb (create/change/end), `--about` the
  entity (beads/memories); `--status`, `--open`, `--id`, `--children`,
  `--no-deferred` and `--no-blocked` scope the beads. Memory events are
  reconstructed from Dolt commit history, because `bd remember` records no
  timestamps.
- `bd-view` — Pretty-prints a single bead with rendered Markdown via `rich`,
  resolved through a `uv run --script` shebang; falls back to plain text
  without it. Takes an issue id.
- `claude-session-find` — Finds an old Claude Code session's UUID by grepping
  transcripts; current project by default, `-g` for all.
- `claude-session-list` — Git-log-style listing of recent Claude Code
  sessions, with prompt/reply counts and titles; hides empty sessions.
- `claude-session-report` — Renders a session transcript as Markdown, with
  each content category (thinking, tools, skill bodies, …) a separate toggle.
- `claude-session-rename` — Retitles a session from the shell exactly as
  `/rename` would, by appending the same two records. Refuses a running
  session.
- `claude-traffic-monitor` — Live `top`-style screen (curses) of internet
  traffic per running Claude Code session since the monitor started:
  5 s / 1 min / 15 min rates plus a 1-minute peak, totals, API share,
  context size, images in context and the estimated upload of the next
  request, plus the busiest non-Claude processes. `top`-style keys (`?`
  lists them). macOS only (`nettop`). Needs a terminal.
- `bd-complete` — Emits `value<TAB>description` completion candidates (`ids`,
  `sessions`); the single front door behind `completions/`.

Shared helpers, both stdlib-only:

- `bdutils.py` — `error()`, `warn()`, `resolve_project_path()`,
  `format_ts()`, `format_priority()`, `paged_output()`, and color
  (`add_color_arg()`, `want_color()`, `paint()`).
- `claudeutils.py` — Claude session enumeration and resolution (path, UUID or
  title substring), shared by the `claude-session-*` scripts and
  `bd-complete`.

Most scripts accept an optional project path argument (default: cwd) and print a
user-facing summary to stdout / errors to stderr with non-zero exit on failure.
Exceptions: `bd-view` takes an issue id (and relies on `bd`'s own `.beads/`
auto-discovery from the current directory); `claude-session-report` takes a
Claude session UUID, title substring, or `.jsonl` path; `claude-session-list`
takes no positional args (current project unless `-g/--global`);
`claude-session-rename` takes a session and a title; `claude-traffic-monitor`
takes none (it watches the whole machine); `bd-complete`
takes a candidate kind (`ids` or `sessions`).

## Design notes live in `.claude/rules/`

The rationale behind each script — why a flag delegates to `bd`, what was
verified rather than assumed, which alternatives were tried and rejected —
lives in path-scoped files under `.claude/rules/`. Claude Code loads each one
when a matching file is read, so it arrives when you open the script or its
tests and costs nothing otherwise:

| Rule file | Loads for |
|---|---|
| `bd-log.md`, `bd-dolt-check.md`, `bd-dolt-diff.md`, `bd-verify-backup.md`, `bd-view.md` | that script and its test file |
| `claude-sessions.md` | `claude-session-*`, `claudeutils.py`, their tests |
| `claude-traffic-monitor.md` | `claude-traffic-monitor` and its test file |
| `completions.md` | `completions/`, `bd-complete`, their tests |
| `bdutils.md` | `bdutils.py` and its tests |
| `tests.md` | anything under `tests/`, `pytest.ini` |
| `makefile.md` | `Makefile`, `tests/test_makefile.py` |
| `screenshots.md` | `tools/`, `docs/img/` |

Before changing a script's behavior, make sure its rule file is in context,
and read it directly if not. New rationale goes into the matching rule file,
not here: this file loads into every session, so it holds only what every
session needs. Each script's rule file ends with its manual checks.

## Shell completion

`completions/beads-utils.zsh` and `completions/beads-utils.bash` provide tab
completion (sourced from the user's rc file; see `README.md`). They are pure
glue — `compdef`/`complete` wiring plus per-command flag lists transcribed
from each script's `argparse` — and route every *dynamic* lookup through
`bd-complete`, so enumeration logic is never duplicated across the two shells.
When adding/renaming a flag or script, update the matching flag list in both
completion files — `tests/test_completions.py` fails if either drifts from the
script's `argparse`, which is how `claude-session-report`'s `--prompts` /
`--replies` / `--slash-commands` were found missing from both. There is no
caching yet; if added, it wraps `bd-complete` alone.

The shell-specific corrections both files carry, and how to test them in a
real shell, are in `.claude/rules/completions.md`.

## Running & Testing

No build system, no package — but a `Makefile` as the single front door for
every routine command, so neither a returning maintainer nor CI has to recall
an invocation. `make help` lists all of it; `make` alone shows that help.

```bash
make test                                     # the suite (rich installed, nothing skips)
make test PYTEST_ARGS='tests/test_bd_log.py -k SelectSubtreesBranches'
make test-minimal                             # without rich: 3 skips, no failures
make check                                    # ruff + a --version smoke test of each script
make ci                                       # exactly what CI runs
make coverage                                 # suite + htmlcov/
make dolt-check / dolt-diff / export-csv      # this repo's own beads data
make install / uninstall                      # symlink the scripts onto PATH (PREFIX=)
make screenshots                              # regenerate the README's terminal images
make outdated                                 # newer releases of the pinned tools
```

`.github/workflows/lint.yml` invokes `make check` and `make test` rather than
spelling the commands out, so a command and its pinned tool version exist in
exactly one place. Add a target rather than documenting a raw invocation.

Tests are a pytest suite under `tests/`, run through `uv` so nothing is
installed into any global environment (`pytest.ini` is config, not packaging —
a `pyproject.toml` would read as packaging the collection).

The suite's traps — fake `bd`/`dolt` on `PATH`, the two assertion styles,
timezone pinning, cache clearing — are in `.claude/rules/tests.md`; notes
for editing the Makefile are in `.claude/rules/makefile.md`.

Also verify manually against a real beads project (this repo itself is
one). Each rule file lists its script's commands; `bd-export-csv` has no
rule file, so its are here:

```bash
./bd-export-csv .                             # Export this repo to CSV in cwd
./bd-export-csv . --sort=-priority,created_at
```

`bd-dolt-check` assumes the `dolt` CLI is installed for its richest output but
degrades gracefully when it isn't. `bd-log` is in the same position for its
memory row only: without `dolt` (or in a JSONL-only repo) the bead half still
renders in full, and nothing is said unless `--about` asked for memories.
`bd-view` requires `uv` on `PATH` — its shebang
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
  Colorizing scripts take `--color=auto|always|never` via
  `bdutils.add_color_arg(parser)` and resolve it once with
  `bdutils.want_color()` — same rationale as `--version`, so the flag
  spelling and the auto-detection rules can't drift between scripts.
  Do **not** bump `__version__` as part of feature work — add a bullet under
  `## Unreleased` in `CHANGELOG.md` and leave the number alone; it moves only
  at release time (see [Releases](#releases)).
- **Changelog bullets**: one short outcome clause each — what a user gets, not
  how it works. Group by category in the order `[breaking]`, `[feature]`,
  `[fix]`, `[refactor]`, `[cleanup]`; nest sub-bullets under a multi-part
  feature rather than spreading it across several top-level lines. Design
  rationale belongs in `CLAUDE.md` or the matching `.claude/rules/` file, not
  in `CHANGELOG.md` — the one thing a
  bullet must never drop is a `[breaking]` change's migration path.
- **Color**: plain 30–37 hues only. Solarized repurposes the bright slots
  (90–97) as greys, and `bold` reaches those slots on terminals that draw
  bold in bright colors, so either can erase a hue. See
  `.claude/rules/bdutils.md`.
- **Errors**: use `bdutils.error(msg)` — exits non-zero with a lowercase `error: ...`
  line to stderr. Never raise tracebacks at the top level.
- **Warnings**: use `bdutils.warn(msg)` — writes `warning: ...` to stderr without exit.
- **Project path**: use `bdutils.resolve_project_path(arg)` for the expanduser/resolve/
  `.beads/`-validation dance.
- **Subprocess**: pass `cwd=project_path` rather than `os.chdir`. Use `check=True` only
  for calls that must succeed; tolerate empty/missing output where it's a valid state.
- **No config files, no state** beyond what `bd` / Dolt already manage under `.beads/`.

## Releases

Nothing here is packaged or published — no `pyproject.toml`, no PyPI, no
installer; the scripts run in place. A release is only a marker of a known-good
point: `## Unreleased` in `CHANGELOG.md` becomes `## vX.Y.Z (DDMonYY)`,
`bdutils.__version__` is set to match, and the commit is tagged `vX.Y.Z`
(annotated). The one exception is `v0.2.0`, a lightweight tag backfilled long
after the fact — an annotated one would have stamped the backfill date onto a
May release.

Two rules carry the weight:

- **The version moves only at release time.** Feature work adds a `## Unreleased`
  bullet and leaves `__version__` alone. `dc63e10` bumped mid-cycle instead, and
  0.3.0's notes then went a full cycle missing the `bd-log --status/--open`
  entry that same commit shipped.
- **Bump from the last release tag, not from `__version__`.** Pre-1.0, any
  `[breaking]` or `[feature]` bullet takes the minor; `[fix]` / `[cleanup]` /
  `[refactor]` alone take the patch. Bumping off `__version__` after a stray
  mid-cycle bump skips a version.

The procedure itself is scripted as the `/release` slash command
([`.claude/commands/release.md`](.claude/commands/release.md)) — run it rather
than working through the steps by hand. It gathers the commit range from the
last tag, audits `## Unreleased` for completeness against that range, runs the
CI gates, and stops before pushing.
