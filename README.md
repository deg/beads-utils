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
| [`bd-dolt-diff`](bd-dolt-diff) | Preview what a `bd dolt push` would send: issue-level diff between local and remote Dolt state |
| [`bd-log`](bd-log) | Git-log-style timeline of bead lifecycle events — create, start, close (color-coded, auto-paged) |
| [`claude-session-find`](claude-session-find) | Substring search across `~/.claude/projects/*.jsonl` to find old Claude Code sessions |
| [`claude-session-list`](claude-session-list) | Git-log-style listing of Claude Code sessions (default: current project; `-g` for all) |
| [`bd-view`](bd-view) | Pretty-print a single bead with rendered Markdown |
| [`claude-session-report`](claude-session-report) | Render a Claude Code session as a Markdown discussion transcript |
| [`bd-complete`](bd-complete) | Emit completion candidates (bead ids, session uuids) — the helper behind shell tab completion |

Run any script with `--help` for full usage. Per-script details and
conventions live in [`CLAUDE.md`](CLAUDE.md); see
[`CONTRIBUTING.md`](CONTRIBUTING.md) to contribute.

## Why these tools?

The scripts fall into two families: tools for looking at your beads, and
tools for looking at your Claude Code sessions. Either way the theme is
the same — the data is already on your disk; these make it pleasant to
read.

### Looking at beads

When an issue carries a long description — design notes, acceptance
criteria, nested lists — `bd show` prints the raw Markdown as one long
wall of text. `bd-view beads-utils-s4s` (that's an issue id) renders it
instead: real headings, real code blocks, dependencies and comments
included, paged like `git log`. Field coverage is a superset of `bd
show`'s — labels, external refs, the metadata dict, parent and children
each shown as themselves — and anything `bd` grows later lands in a
trailing `Other Fields` section rather than silently disappearing.

Agentic coding changes what an issue tracker has to answer. A Claude
session can create, claim, and close half a dozen beads while your
attention was on the code, and afterwards you want to know what it
actually did. `bd-log` shows the lifecycle events — created, started,
closed — newest first, git-log style. `bd-log --open` narrows to beads
still open: the to-do list the session left behind, and `bd-log --id
<id> --children` narrows the other way — one bead, or one epic and
everything under it, from creation to close.

Sometimes the right reading tool is a spreadsheet — sorting issues for a
triage meeting, or sharing the list with someone who doesn't live in a
terminal. `bd-export-csv --sort=-priority,created_at` flattens the whole
database to a CSV, presorted before the spreadsheet even opens.

The last pair guards against a quiet failure mode. Beads keeps its data
in Dolt and pushes it to your git remote under `refs/dolt/data` — a ref
GitHub's UI never shows, so the repo page looks identical whether or not
your issues actually made it to the remote. `bd-dolt-check` answers
"did they?", comparing local state against the remote and exiting
non-zero on drift (which also makes it a CI gate). `bd-dolt-diff`
answers the follow-up — what exactly would a `bd dolt push` send? —
with an issue-level diff: added and removed beads, field-by-field
changes, dependency and comment edits.

### Looking at Claude sessions

`claude --resume` offers a picker of recent sessions, but the picker is
cramped and can't be scripted. `claude-session-list` is the long-form
version: the sessions for the current project (or every project, with `-g`),
each with its full UUID ready to paste, a timestamp range with the
active span, prompt/reply counts, and the session title. `--oneline`
gives a compact table; `claude-session-list -q | head -1` hands a
script the newest UUID.

That covers "which session was most recent"; `claude-session-find`
covers "which session was it where we discussed the pager?" It greps
the transcripts for a substring and lists the matching sessions with
snippets for context. `claude --resume $(claude-session-find -q pager |
head -1)` drops you straight back into the conversation.

And when a session turns out to be worth keeping — a design discussion,
a long debugging hunt — `claude-session-report` renders it as a
Markdown transcript: your prompts, Claude's replies, and (with `--all`)
the tool calls and every other channel too. The result is a document you can
review at leisure, commit next to the code it produced, or hand to a
colleague who asks "how did you get Claude to do that?"

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
