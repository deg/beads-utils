# beads-utils

[![lint](https://github.com/deg/beads-utils/actions/workflows/lint.yml/badge.svg)](https://github.com/deg/beads-utils/actions/workflows/lint.yml)

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
| [`claude-session-list`](claude-session-list) | Git-log-style listing of Claude Code sessions (default: current project; `-g` for all) |
| [`bd-view`](bd-view) | Pretty-print a single bead with rendered Markdown |
| [`claude-session-report`](claude-session-report) | Render a Claude Code session as a Markdown discussion transcript |
| [`bd-complete`](bd-complete) | Emit completion candidates (bead ids, session uuids) — the helper behind shell tab completion |

Run any script with `--help` for full usage. Per-script details and
conventions live in [`CLAUDE.md`](CLAUDE.md); see
[`CONTRIBUTING.md`](CONTRIBUTING.md) to contribute.

## Shell completion

Tab completion for zsh and bash lives in [`completions/`](completions).
`bd-view` completes bead ids (with titles shown in zsh),
`claude-session-report` completes session uuids/titles, the project-path
scripts complete directories, and every script completes its flags.

Source the file for your shell from your rc file:

```bash
# ~/.zshrc  (oh-my-zsh users: put this *after* `source $ZSH/oh-my-zsh.sh`)
source /path/to/beads-utils/completions/beads-utils.zsh
# ~/.bashrc
source /path/to/beads-utils/completions/beads-utils.bash
```

The scripts (including `bd-complete`, which feeds the dynamic candidates)
must be on your `$PATH`. Prefer the autoload convention instead? Drop
`beads-utils.zsh` into a directory on your `$fpath`, or `beads-utils.bash`
into your `bash-completion.d`.

## License

Released under the [MIT License](LICENSE).
