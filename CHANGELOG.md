## Unreleased

* [feature] Add `bd-verify-backup`, which says whether a repo would lose anything if this machine died: uncommitted files or stashes, branches not pushed, or beads not pushed
  * `-g/--global` checks every beads repo on the machine at once, one line each, failures first
  * Fetches first so the answer is current; `--no-fetch` skips it
  * A merged branch whose remote copy was deleted is listed as cleanup rather than counted as unbacked-up
  * A branch with no upstream whose commits are all on a remote still fails, but says so and prints the `git branch -u` command that fixes it
* [feature] Add `claude-traffic-monitor`, a live `top`-like view of how much each running Claude Code session uploads and downloads, which share goes to the API, and the context and images driving it, plus the busiest other processes on the link (macOS)
  * Rates over 5 s, 1 min and 15 min, plus the peak second of the last minute, so a single request's burst stays visible
  * An estimate of what each session's next message will upload, with the live-measured bytes per token beside it
  * `top`-style keys (sort, hide child or other processes, reset the totals, pause), with a status bar showing the current mode
  * Child processes that have exited and sat idle for 15 minutes drop off the screen (their bytes stay in the session's total); `c` shows them again
  * Count traffic from apps that send without a fixed destination, such as Tailscale and many VPNs and calls, and flag tunnelled traffic that appears on screen twice
  * Count traffic a security proxy relays (Norton for Chrome) once, under the app that made it, and the last second of every closed connection
* [feature] Cover the `Makefile` itself in the test suite, which nothing previously exercised
* [feature] Put the scripts on your `PATH` with `make install`, which symlinks them into `PREFIX` (default `~/.local/bin`); `make uninstall` removes them again
* [feature] Show what the tools actually print — the README now carries terminal screenshots, regenerated with `make screenshots`
  * `bd-verify-backup -g` and `claude-traffic-monitor` are shown on sample data, so the README shows nobody's real repos or sessions
* [fix] `bd-dolt-check` looks for pushed beads on the repo's Dolt remote rather than its git origin, so a project whose beads live in a separate repository no longer reads as never pushed
* [fix] `bd-dolt-check` says it could not check the remote when `git ls-remote` fails (offline, refused), instead of reporting the beads as never pushed
* [fix] Stop telling server-mode users that `bd dolt commit` commits nothing — bd 1.3.0 fixed that, so `bd-dolt-check` now gives both modes the same remedy and keeps the `bd dolt stop` workaround as a note for older bd
* [cleanup] Bring the README, `CLAUDE.md` and the PR template up to date with the scripts added since v0.4.0

## v0.4.0 (22Sep26)

* [feature] Add `claude-session-rename`, which sets a session's title from the shell like `/rename` does, without starting the session (a running session is refused)
* [feature] Count what `bd-log` showed with `--count-events`, `--count-beads` and `--count-memories`, each adding a line after the log
* [feature] Drop currently-deferred beads from `bd-log` with `--no-deferred` (`--open --no-deferred` is what's live and not parked)
* [feature] Drop beads waiting on an unsatisfied dependency from `bd-log` with `--no-blocked`
* [feature] Log memories alongside beads in `bd-log` — when one was remembered, revised, or forgotten:
  * `--about=beads,memories` picks what to log; `--only=create,change,end` picks the verb, for either
  * `--only=start` and `--only=close` keep working, as the change and end verbs
  * A memory written but not yet committed to Dolt has no date, so those changes lead in a labelled group and `-n` doesn't count them
  * Needs the `dolt` CLI and a Dolt-backed repo, since `bd remember` stores no timestamps
* [feature] Print a tinted symbol key below `bd-log`'s output, showing what each glyph and color means (`--legend=auto|always|never`; auto = only on a terminal)
* [feature] Limit `bd-log` to named beads with `--id=LIST`, or to their whole subtrees with `--children`
* [feature] Color `bd-log` events by kind, with `--color=auto|always|never`
* [feature] Collapse each entry to a single row with `--oneline`, in both `bd-log` and `claude-session-find`
* [feature] Add a pytest suite covering every script — run it with `make test`:
  * Exercise `bd` and `dolt` through programmable fakes, and Claude sessions through synthetic transcripts, so no test touches a real project
  * Pin the `bd-log --children` subtree behaviors that live bead data can't reach
  * Fail when either completion file drifts from a script's flags
  * Run the suite in CI on every push and pull request
* [feature] Add a `Makefile` covering test, lint, coverage, and Dolt-sync commands — `make help` lists them all
* [fix] Flag uncommitted Dolt tables in `bd-dolt-check`, which reported a repo as in sync while whole tables sat in the working set — in no commit, and therefore in no push:
  * An uncommitted table is its own `UNCOMMITTED` status and exits 1, so a gate that passed on such a repo now fails
  * The working set is reported before the remote is consulted, so a repo that has never pushed hears it too
  * Names the remedy that works for the repo's Dolt mode — `bd dolt stop` in server mode, where `bd dolt commit` reports success without committing
* [fix] Show `?` for a bead whose id is missing or empty in `bd-log`, rather than a gap in the id column
* [fix] Reject an empty `bd-log --status=`, which silently logged every bead and every memory instead of narrowing
* [fix] Show `(no title)` in `bd-log` for a bead whose title is only whitespace, rather than a blank colored line
* [fix] Complete options written as `--opt=value` in both shells, not just `--opt value`
* [fix] Complete each element of a comma-separated option, so `--only=create,st` finishes
* [fix] Complete `claude-session-report`'s `--prompts`, `--replies` and `--slash-commands`, which neither completion file listed
* [fix] Offer candidates for `bd-log --only` and `claude-session-list --sort`, which previously completed nothing
* [fix] Lint `claudeutils.py`, which shebang-based discovery had been skipping
* [refactor] Fold `bd-log`'s two `bd` JSON queries onto one run-and-parse helper
* [refactor] Fold `claude-session-find`'s duplicated session helpers into `claudeutils`
* [cleanup] Write down the changelog bullet style in `CLAUDE.md`
* [cleanup] Link to the beads repo's current home, `gastownhall/beads`, instead of relying on the redirect from its old path

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
