# beads-utils

A small collection of Python CLI scripts that augment
[`bd`](https://github.com/your-handle/beads) (the beads issue
tracker) and its Dolt-backed storage. No package, no build step —
each script lives at the repo root alongside a shared `bdutils.py`
helper and runs with `python3` (or `uv` for the one script that
needs `rich`).

## Scripts

| Script | What it does |
|---|---|
| [`bd-export-csv`](bd-export-csv) | Export the bead database to a flat CSV for spreadsheet review |
| [`dolt-remote-check`](dolt-remote-check) | Verify the Dolt data behind a `bd` repo is actually pushed to its git remote |
| [`bd-log`](bd-log) | Git-log-style view of recently closed beads (auto-paged) |
| [`find-claude-session`](find-claude-session) | Substring search across `~/.claude/projects/*.jsonl` to find old Claude Code sessions |
| [`bd-view`](bd-view) | Pretty-print a single bead with rendered Markdown |
| [`claude-session-report`](claude-session-report) | Render a Claude Code session as a Markdown discussion transcript |

Run any script with `--help` for full usage. Per-script details and
conventions live in [`CLAUDE.md`](CLAUDE.md).

## The story behind it

This repo started as a deliberate experiment: pick a contained but
non-trivial coding project and try to do all of it with Claude in
the driver's seat. Six weeks and 2,140 lines later, the experiment
is in [`PROJECT.md`](PROJECT.md) — what we built, what worked, what
broke, and what I'd carry forward.
