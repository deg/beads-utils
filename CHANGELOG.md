## Unreleased

* [feature] Limit `bd-log` to named beads with `--id=LIST`, or to their whole subtrees with `--children`
* [feature] Color `bd-log` events by kind, with `--color=auto|always|never`
* [feature] Add a pytest suite covering every script — run it with `make test`:
  * Exercise `bd` and `dolt` through programmable fakes, and Claude sessions through synthetic transcripts, so no test touches a real project
  * Pin the `bd-log --children` subtree behaviors that live bead data can't reach
  * Fail when either completion file drifts from a script's flags
  * Run the suite in CI on every push and pull request
* [feature] Add a `Makefile` covering test, lint, coverage, and Dolt-sync commands — `make help` lists them all
* [fix] Complete options written as `--opt=value` in both shells, not just `--opt value`
* [fix] Complete each element of a comma-separated option, so `--only=create,st` finishes
* [fix] Complete `claude-session-report`'s `--prompts`, `--replies` and `--slash-commands`, which neither completion file listed
* [fix] Offer candidates for `bd-log --only` and `claude-session-list --sort`, which previously completed nothing
* [fix] Lint `claudeutils.py`, which shebang-based discovery had been skipping
* [refactor] Fold `claude-session-find`'s duplicated session helpers into `claudeutils`
* [cleanup] Write down the changelog bullet style in `CLAUDE.md`

## v0.3.0 (27Jul26)

* [breaking] Rename `bd-export-csv --sortby` to `-s/--sort`, matching `claude-session-list` and GNU convention
* [breaking] Remove `claude-session-report --list-sessions` — use `claude-session-list -g -q` instead
* [feature] Add `bd-dolt-diff` — preview the issue-level changes a `bd dolt push` would send, or diff any two Dolt revisions with `--base`/`--head`
* [feature] Add `claude-session-list` — git-log-style listing of recent Claude Code sessions:
  * Show timestamp range, age, prompt/reply counts, and title; `-g/--global` spans every project
  * Hide truly-empty sessions by default; `-a/--all` and `--min-prompts N` override
  * `--oneline` for a one-row-per-session table, `-q/--quiet` for UUIDs only
  * Sort with `-s/--sort=KEYS`, filter titles and UUIDs with `-m/--match=PATTERN`
* [feature] Filter `bd-log` by a bead's current status with `--status=LIST` and `--open`
* [fix] Render every field `bd show` displays in `bd-view`, with dependencies grouped by relationship and anything unclaimed listed under `Other Fields`
* [refactor] Move Dolt/git plumbing out of `bd-dolt-check` into `bdutils`, and Claude session enumeration out of `claude-session-report` into a new `claudeutils`
* [cleanup] Add a README "Why these tools?" section and write down the release process

## v0.2.0 (26May26)

* [feature] Add zsh and bash tab completion for bead ids, session uuids, project paths, and flags — source `completions/beads-utils.zsh` or `.bash` to enable
* [feature] Add `claude-session-report --list-sessions` — a standalone session index that also feeds completion

## v0.1.0 (pre-25May26)

* [feature] `bd-export-csv` — export a beads database to a flat CSV for spreadsheet review, with comma-separated `--sortby` keys (`-` prefix for descending)
* [feature] `bd-dolt-check` — verify a beads repo's Dolt data is actually pushed to its git remote; exits non-zero so CI can gate on it
* [feature] `bd-log` — git-log-style view of recently closed beads, auto-paged, with `-n` and `--since`
* [feature] `bd-view` — pretty-print a single bead with rendered Markdown (via `rich`, resolved through `uv`)
* [feature] `claude-session-find` — substring search across Claude Code session transcripts to recover an old session UUID
* [feature] `claude-session-report` — render a Claude Code session as a Markdown discussion transcript, with per-channel toggles
* [feature] Shared `bdutils` module and a normalized CLI surface — `--version` on every script, `--no-pager` parity, consistent help formatting
