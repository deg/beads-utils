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
  and writes a flat CSV suitable for spreadsheet review. Supports `-s/--sort` with
  comma-separated keys and `-`-prefixed descending order.
- `bd-dolt-check` — Verifies that a beads repo's Dolt data (stored under
  `refs/dolt/data` on the git remote, invisible in GitHub's UI) has actually been
  pushed. Compares `.beads/push-state.json` against `git ls-remote` and the local
  `.dolt/repo_state.json` / `dolt log`. Exits 1 on OUT OF SYNC so CI can gate on it.
- `bd-dolt-diff` — Previews what a `bd dolt push` would actually send: an
  issue-level diff between the remote-tracking ref and the local branch
  (added/removed issues, field-level before/after for changed ones, plus
  dependency/label/comment changes). `--base`/`--head` diff any two Dolt
  revisions. Dependency and comment rows are keyed on their semantic tuple,
  not the surrogate `id` column (Dolt mints a fresh `uuid()` per insert, so
  the same logical edge created on two clones would otherwise show as a
  spurious add+remove). When a schema migration means the two revisions
  don't share a column set, compares the intersection and names the skipped
  columns (selecting a column absent from one side is a hard Dolt error).
  Read-only; always exits 0 when the comparison ran — `bd-dolt-check`
  remains the CI gate. Pages via `bdutils.paged_output()`; `--no-pager`
  disables. Requires the `dolt` CLI.
- `bd-log` — Shows recent beads lifecycle events (create/start/close) in a
  git-log-style timeline, newest first. Wraps `bd list ... --json` and
  synthesizes one event per non-empty `created_at`/`started_at`/`closed_at`
  timestamp on each issue. Two orthogonal filter axes: `--only=KINDS`
  (comma-separated event kinds — `create,start,close`; default all) selects
  which *events* to render, and `--status=LIST` (comma-separated statuses,
  passed straight through to `bd list --status`; bd owns the vocabulary and
  validation) scopes to beads by *current* status. `--open` is shorthand for
  "not closed" (mutually exclusive with `--status`); with neither flag the
  default is `bd list --all` (everything, incl. closed). Also `-n/--limit`
  (default 0 = unlimited, like `git log`) and `--since DATE`
  (timestamp filter applied to every event kind). Pages through
  `bdutils.paged_output()` (`$PAGER` or `less -FRX` when stdout is a tty).
  `--no-pager` disables.
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
  description, design, notes, acceptance criteria, metadata, dependencies,
  comments) with proper formatting via the `rich` library. Subclasses
  `rich.markdown.Markdown` to disable raw HTML so placeholder text like
  `<id>` survives. Single positional arg: `bd-view <issue-id>`.
  Field coverage is meant to be a superset of `bd show`'s, and is
  self-defending: `RENDERED_KEYS` lists every top-level JSON key some
  renderer accounts for, and whatever is left (minus the redundant
  `dependency_count`/`dependent_count`/`comment_count`) lands in a trailing
  `Other Fields` section — so a column `bd` adds later shows up unprompted
  instead of vanishing. This mirrors `bd show --long`'s own
  `EXTENDED DETAILS` section. Dependencies are grouped by the
  `dependency_type` that `bd dep list --json` returns (`Parent:`,
  `Children:`, `Depends on:`, `Blocks:`, plus the rarer `tracks` /
  `discovered-from` / `supersedes` / … kinds); unknown types render under
  their raw name rather than being folded into depends-on/blocks. If a bead
  has a `parent` but no parent-child edge comes back, the bare id is shown.
  Pages via `bdutils.paged_output()`; `--no-pager` disables. Falls back to a
  plain-text dump (with a `warning:`) if `rich` isn't installed — the
  fallback renders the same field set.
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
- `claude-session-list` — Git-log-style listing of recent Claude Code
  sessions. Default scope = current project (matched by mangled-cwd
  lookup under `~/.claude/projects/`); `-g/--global` spans all projects
  and adds a project-label line to each entry. Each entry shows the
  full UUID (copy-paste-ready for `claude --resume`), an optional
  project label, a timestamp range with relative age and active span
  (`2026-05-27 09:11 → 14:32  (3h ago, 5h21m active)`), the
  prompt/reply counts (`N prompts / M replies` in block view, `Np/Mr`
  in `--oneline`), and the session title (`custom-title` from
  `/rename`, else `ai-title`, else `(untitled)`).
  Counts: "prompts" = `type=='user'` entries whose content has
  non-wrapper prose; entries consisting only of `<command-name>`,
  `<system-reminder>`, `<local-command-caveat>`, `<bash-input>`, etc.
  (no human-typed text) don't count. This is what lets `/clear`-ghost
  sessions register as `0p/0r`. "replies" = `type=='assistant'`
  entries. Both exclude subagent sidechains.
  Filters: by default, sessions with `0p/0r` (truly empty — `/clear`
  ghosts, aborted sessions) are hidden; a stderr footer reports the
  hidden count. `-a/--all` shows everything. `--min-prompts N`
  (mutex with `-a`) is a stricter filter — only sessions with ≥ N
  human prompts. `--oneline` collapses each session to one row and
  prints an `ID / STARTED / AGE / COUNTS / PROJECT / TITLE` header
  (STARTED is the session's first timestamp; AGE is time since last
  activity — independent dimensions). The COUNTS and PROJECT columns
  auto-size to the actual data so the TITLE column doesn't jitter
  row-to-row. `-q/--quiet` prints UUIDs only (pipe-friendly,
  suppresses the header and the filter-hint footer). `-n/--limit`
  caps the count (0 = unlimited).
  `-s/--sort=KEYS` accepts comma-separated keys with `-`-prefix
  descending (matches `bd-export-csv --sort`); keys = `started`,
  `last`, `duration`, `prompts`, `replies`, `turns`, `title`,
  `project`, `id`. Default order is mtime-newest-first (same as
  before). `-m/--match=PATTERN` is a case-insensitive substring
  match on title OR full UUID, applied before the empty-session
  filter. Pages via `bdutils.paged_output()`; `--no-pager` disables.
- `bd-complete` — Emits shell-completion candidates as
  `value<TAB>description` lines; the single front door behind the
  zsh/bash completion in `completions/` (so candidate logic is never
  duplicated across shells, and a future TTL cache has one wrap point).
  `bd-complete ids` lists full bead ids (e.g. `beads-utils-v9o.4`) from
  `bd list --status=all` — full rather than the short suffix so a
  wrong-project id is visible at the prompt.
  `bd-complete sessions` calls into `claudeutils.list_sessions()`
  directly. Lookups fail silently (no output, exit 0) so a
  broken/slow command never garbles the prompt.

Shared helpers:

- `bdutils.py` — `error()`, `warn()`, `resolve_project_path()`,
  `format_ts()`, `format_priority()`, and `paged_output()` (context manager
  that pipes through `$PAGER` or `less -FRX` when stdout is a tty; `-F` makes
  short output indistinguishable from direct-to-stdout). Imported by scripts
  in this repo; keep small and stdlib-only.
- `claudeutils.py` — Claude session enumeration/resolution: `CLAUDE_PROJECTS`,
  `mangle_cwd()`, `find_project_dir()`, `project_label()`, `has_human_prose()`
  (strips known wrapper tags listed in `USER_WRAPPER_TAGS` — `<command-name>`,
  `<system-reminder>`, `<local-command-caveat>`, `<bash-input>`, etc. — and
  reports whether anything is left), `read_session_meta()` (one-pass scan:
  titles, cwd, first/last timestamps, `human_prompts` count using
  `has_human_prose`, `assistant_turns` count, all returned as a `SessionMeta`
  dataclass with an `is_empty` property), `iter_sessions()`, `list_sessions()`,
  and `resolve_session()` (UUID-or-title-or-path → `.jsonl` path). Used by
  `claude-session-report`, `claude-session-list`, and `bd-complete`. Also
  stdlib-only.

Most scripts accept an optional project path argument (default: cwd) and print a
user-facing summary to stdout / errors to stderr with non-zero exit on failure.
Exceptions: `bd-view` takes an issue id (and relies on `bd`'s own `.beads/`
auto-discovery from the current directory); `claude-session-report` takes a
Claude session UUID, title substring, or `.jsonl` path; `claude-session-list`
takes no positional args (current project unless `-g/--global`); `bd-complete`
takes a candidate kind (`ids` or `sessions`).

## Shell completion

`completions/beads-utils.zsh` and `completions/beads-utils.bash` provide tab
completion (sourced from the user's rc file; see `README.md`). They are pure
glue — `compdef`/`complete` wiring plus per-command flag lists transcribed
from each script's `argparse` — and route every *dynamic* lookup through
`bd-complete`, so enumeration logic is never duplicated across the two shells.
When adding/renaming a flag or script, update the matching flag list in both
completion files. There is no caching yet; if added, it wraps `bd-complete`
alone.

## Running & Testing

No build system. There are no automated tests — verify manually against a real beads
project (this repo itself is one):

```bash
./bd-export-csv .                             # Export this repo to CSV in cwd
./bd-export-csv . --sort=-priority,created_at
./bd-dolt-check .                             # Check Dolt sync state
./bd-dolt-diff .                              # Preview what a push would send
./bd-dolt-diff . --base <branch-or-hash>      # Diff vs an arbitrary revision
./bd-log                                       # All lifecycle events (incl. closed)
./bd-log --open                                # Events for beads still open
./bd-log --only=start --status=in_progress     # What's actively being worked
./bd-log -n 25 --since 2026-04-01              # 25 events on/after date
./claude-session-find 'bd-log'                 # Sessions in this project matching
./claude-session-find -g 'paged_output'        # All projects
./claude-session-find -a 'dolt push'           # Include assistant/tool content
./claude-session-find -q foo | head -1         # UUID only (for `claude --resume`)
./bd-view beads-utils-s4s                      # Pretty-print a single bead
./claude-session-report <uuid>                 # Default discussion-only render
./claude-session-report 'bd-view'              # Substring-match a session title
./claude-session-report <uuid> --thinking --tools     # Add agent thinking + tool I/O
./claude-session-report <uuid> --all > session.md     # Everything, to a file
./claude-session-list                                  # Recent sessions for cwd's project
./claude-session-list -g --oneline                     # Every project, one row each
./claude-session-list -q | head -1                     # Newest UUID (for `claude --resume`)
./bd-complete ids                                      # Completion feed: short ids + titles
./bd-complete sessions                                 # Completion feed: session uuids + titles
```

Shell completion is verified by sourcing the file and tab-completing in a real
shell (`source completions/beads-utils.zsh` / `.bash`, then `bd-view <TAB>`).

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
  Do **not** bump `__version__` as part of feature work — add a bullet under
  `## Unreleased` in `CHANGELOG.md` and leave the number alone; it moves only
  at release time (see [Releases](#releases)).
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
