# beads-utils

A small collection of Python CLI scripts that augment
[`bd`](https://github.com/steveyegge/beads) (the beads issue
tracker) and its Dolt-backed storage. No package, no build step —
each script lives at the repo root alongside a shared `bdutils.py`
helper and runs with `python3` (or `uv` for the one script that
needs `rich`).

## Scripts

| Script | What it does |
|---|---|
| [`bd-export-csv`](bd-export-csv) | Export the bead database to a flat CSV for spreadsheet review |
| [`bd-dolt-check`](bd-dolt-check) | Verify the Dolt data behind a `bd` repo is actually pushed to its git remote |
| [`bd-log`](bd-log) | Git-log-style view of recently closed beads (auto-paged) |
| [`claude-session-find`](claude-session-find) | Substring search across `~/.claude/projects/*.jsonl` to find old Claude Code sessions |
| [`bd-view`](bd-view) | Pretty-print a single bead with rendered Markdown |
| [`claude-session-report`](claude-session-report) | Render a Claude Code session as a Markdown discussion transcript |

Run any script with `--help` for full usage. Per-script details and
conventions live in [`CLAUDE.md`](CLAUDE.md).

## License

Released under the [MIT License](LICENSE).
