## Unreleased

* [feature] `claude-session-list` — git-log-style listing of recent Claude Code sessions. Defaults to cwd's project; `-g/--global` spans all. `--oneline` for one-per-row, `-q/--quiet` for UUIDs only (pipe-friendly for `claude --resume`). Shows timestamp range, age, prompt/reply counts (`N prompts / M replies` in block view, `Np/Mr` in oneline), and title.
* [feature] `claude-session-list` filters truly-empty sessions (e.g. `/clear`-ghost sessions where `0p/0r`) by default; `-a/--all` shows everything, `--min-prompts N` is a stricter filter. Hidden count reported to stderr (suppressed in `-q` so pipes stay clean). The prompt counter strips wrapper tags (`<command-name>`, `<system-reminder>`, `<local-command-caveat>`, `<bash-input>`, …) so entries that are pure plumbing don't count as human prompts.
* [feature] `claude-session-list --oneline` now emits an `ID / STARTED / AGE / COUNTS / PROJECT / TITLE` header row and sizes the COUNTS and PROJECT columns to fit the actual data — no more title-column jitter when a project name like `marketbuzzr_landing_page` shows up under `-g`. STARTED is the session's first timestamp (when the conversation began); AGE is time since the last activity. `-q` continues to skip the header (pipe-friendly).
* [feature] `claude-session-list -s/--sort=KEYS` — comma-separated sort keys with `-` prefix for descending. Keys: `started`, `last`, `duration`, `prompts`, `replies`, `turns`, `title`, `project`, `id`. Default order unchanged (newest activity first).
* [feature] `claude-session-list -m/--match=PATTERN` — case-insensitive substring filter against title OR full UUID.
* [breaking] `bd-export-csv --sortby` renamed to `-s/--sort` to align with `claude-session-list` and the GNU coreutils convention (`ls --sort`, `ps --sort`). Semantics unchanged: comma-separated keys, `-` prefix for descending.
* [refactor] Session enumeration helpers (`iter_sessions`, `list_sessions`, `resolve_session`, project-dir lookup) moved from `claude-session-report` into a new shared `claudeutils` module. `bd-complete sessions` now imports the helper directly instead of shelling out.
* [breaking] Removed `claude-session-report --list-sessions` — its only consumer was `bd-complete`. `claude-session-list -g -q` is the user-facing replacement; `bd-complete sessions` is unaffected.

## v0.2.0 (26May26)

* [feature] Shell tab completion for zsh and bash — completes full bead ids (with titles shown in zsh) for `bd-view`, session uuids/titles for `claude-session-report`, project directories for the path-taking scripts, and flags for every command. Source `completions/beads-utils.zsh` or `completions/beads-utils.bash` to enable; dynamic candidates come from a new `bd-complete` helper.
* [feature] `claude-session-report --list-sessions` — print every known Claude session as `uuid<TAB>title`, newest first; a standalone session index that also feeds completion.

## v0.1.0 (pre-25May26)

* [feature] `bd-export-csv` — export a beads database to a flat CSV for spreadsheet review, with comma-separated `--sortby` keys (`-` prefix for descending)
* [feature] `bd-dolt-check` — verify a beads repo's Dolt data is actually pushed to its git remote; exits non-zero so CI can gate on it
* [feature] `bd-log` — git-log-style view of recently closed beads, auto-paged, with `-n` and `--since`
* [feature] `bd-view` — pretty-print a single bead with rendered Markdown (via `rich`, resolved through `uv`)
* [feature] `claude-session-find` — substring search across Claude Code session transcripts to recover an old session UUID
* [feature] `claude-session-report` — render a Claude Code session as a Markdown discussion transcript, with per-channel toggles
* [feature] Shared `bdutils` module and a normalized CLI surface — `--version` on every script, `--no-pager` parity, consistent help formatting
