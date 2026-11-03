---
paths:
  - "claude-session-*"
  - "claude-sessions-*"
  - "claudeutils.py"
  - "tests/test_claude*.py"
---

# claude-session-* and claudeutils design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

## claude-session-find

`claude-session-find` — Finds the UUID of an old Claude Code session by
grepping its transcript. Reads `~/.claude/projects/<mangled-cwd>/<uuid>.jsonl`
(mangling = `/` and `.` → `-`, via `claudeutils` — this script kept private
copies of that and three sibling helpers until beads-utils-8ju; it now reads
`claudeutils.CLAUDE_PROJECTS` through the module rather than from-importing
it, so there is exactly one binding for tests and callers to redirect). Defaults to the current project and
human-typed user messages only; `-g/--global` spans all projects,
`-a/--all` also searches assistant text, thinking, and tool inputs/outputs.
Git-log-style output with timestamp, project label, full UUID, match count,
and up to 3 snippets per session; `--oneline` keeps each entry's own first
line and drops its snippets (padding the project label so the uuid and
hit-count columns align — the block form has no column to align to). Like
`bd-log --oneline` and for the same reason, it prints no column-header row:
timestamp, project, uuid and hit count are self-describing, where
`claude-session-list`'s `8f3a2b1c` / `3h ago` / `12p/47r` are not.
`-q/--quiet`
prints only UUIDs (pipe-friendly for `claude --resume`). The three form the
same block → oneline → quiet ladder `claude-session-list` has, and
`--oneline`/`-q` share its mutex group. Neither brief mode gathers snippets
it won't print. Pages via `bdutils.paged_output()`.

## claude-session-list

`claude-session-list` — Git-log-style listing of recent Claude Code
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

## claude-session-report

`claude-session-report` — Renders a Claude Code session JSONL as a
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

## claude-session-rename

`claude-session-rename` — Does what the `/rename` slash command does, from
the shell and without starting the session: `claude-session-rename
<session> <title>`. `/rename` persists a title by appending two records to
the session's transcript, `{"type":"custom-title","customTitle":…}` and
`{"type":"agent-name","agentName":…}` (both carry `sessionId`, neither a
timestamp), and every reader — the `claude --resume` picker,
`claudeutils.read_session_meta`, hence the three `claude-session-*` scripts
above — takes the *last* `custom-title`. Nothing else stores the title. So
the script appends exactly those two records and the job is done; both are
written so the transcript is indistinguishable from one `/rename` touched.
The session resolves through `claudeutils.resolve_session()` (path, UUID,
or title substring; ambiguity lists candidates and exits 1), same as
`claude-session-report`. It **refuses a running session**: a live process
re-emits its own title on later turns and would silently undo the rename,
and `/rename` is right there inside it. Live means a
`~/.claude/sessions/<pid>.json` names the session *and* the pid answers a
signal-0 probe (`claudeutils.live_session_pid`); a file whose pid is dead
is a crash leftover and is ignored, since a dead process clobbers nothing.
No `--force` (a simple refusal was the owner's call), no show mode, no
`--clear` — set only. The title is stripped and must be a non-empty single
line. Prints `<uuid>: <old title> -> <new title>`. Does not page and takes
no `--color`: one line of output.

## claude-sessions-review

`claude-sessions-review` — Recurring tool failures across sessions
(beads-utils-t29). The plural name says it looks across many sessions, where
`claude-session-report` renders one; it is why the `paths:` above carry a
second glob. The idea comes from an Anthropic talk on agent memory: a
session can't see patterns that span sessions, so an out-of-band pass over
transcripts finds them. This is that pass's deterministic half. `/dream`
(beads-utils-c1k) is meant to be the half that proposes rules.

The design came from a survey of the real transcripts (526 sessions plus
1,475 subagent files, 2026-04-21 to 2026-11-03, 1,641 errors among 76k tool
results), not from guesses about the format:

- **Scan the whole error text, not its first line.** In a compound Bash
  command the line that matters sits mid-output. A first-line match missed
  every one of zsh's `no matches found` failures.
- **Rank by distinct sessions, not hits.** One session looped 57 times on
  `command not found`, and the bar `--min-sessions 2` (the default) exists
  for the same reason. Hidden one-offs are counted on stderr.
- **Group by message, keep the argument as a variant.** `cd: no such file or
  directory` is only actionable once you see `backend` x55 under it.
  `normalize()` abstracts quoted strings, paths, uuids, hex ids (only runs
  with a digit, so all-letter words survive) and numbers. `first_variant()`
  keeps the first thing it abstracted. A `'` with a letter beside it is an
  apostrophe: pairing the one in `can't` with a later quote swallowed the
  text between, and two contractions leaked a real argument into the key.
- **zsh's `=word` expansion names the word in the message** (`===== not
  found`), so without `_ZSH_EQUALS_RE` every separator length was its own
  group. Folded together, it is the most common failure of all.

`classify()` tries extractors in a fixed order, first match wins:
- denials and classifier outages, recognized by their fixed wording on any tool
- harness `<tool_use_error>`, only at the start of the result, since a
  failed `grep` over transcripts can print one
- zsh `(eval):N:` (`(eval):cd:N:` names the builtin)
- the last exception line of a Python traceback
- `Command timed out`
- MCP `Error running <tool>:`
- the first error-looking line, as a fallback

A non-zero exit whose output has no error-looking line is labelled
`exit N, first line: ...`, so stray stdout isn't presented as the error.

Kinds:
- `failure`: harness guards like Edit before Read count, since a rule can
  fix them.
- `denied`: your rejections, the auto-mode classifier, permission rules. These
  are your decisions, not failures, but what keeps being refused is a
  preference signal.
- `unavailable`: the classifier couldn't run.

Text output defaults to `failure`, and `--json` to every kind (so `/dream`
gets the denials).

Other behavior:
- A subagent transcript (`<project>/<parent-uuid>/subagents/agent-*.jsonl`)
  counts under its parent session.
- `--since` drops entries dated before the cutoff (one with no timestamp is
  kept), and skips unread any file last written before it. An empty
  `--since ''` counts as absent, as in `bd-log`.
- A renamed project can leave the same session file under two project dirs
  (`cpemu` and `CPeMulator`). Session counts are sets and survived that, but
  hits, tools and variants counted twice, 119 of 1,995 in the real data, so
  `scan()` skips a `(session, tool_use_id)` already seen. beads-utils-72o is
  the same duplication, hitting `resolve_session()`.
- Titles are read only for the sessions shown as examples (`Titles`), so a
  `-g` run does not read every transcript twice. It takes about 15 s over
  everything.
- Parsing stays in the script until `/dream` needs more than the `--json`.

The tests' guards were each mutation-checked:
- `classify()`: the whole-text scan, the `=word` fold, the error-line
  preference, the anchored harness error and outages
- `normalize()`: the hex digit rule, the apostrophe guard
- `scan()`: session ranking, subagent attribution, the duplicate-file dedupe,
  both `--since` paths, `is_error`, one example per session
- local midnight, which runs under a non-UTC zone, since the suite pins UTC
- end-to-end: the `--min-sessions` default, the `--json` kind default and its
  `totals`, `-n`'s summary, `--since`, and the zero bar

## claudeutils.py

`claudeutils.py` — Claude session enumeration/resolution: `CLAUDE_PROJECTS`,
`CLAUDE_JSON` + `claude_project_paths()` (the `projects` keys of
`~/.claude.json`, or `[]` if unreadable; `bd-verify-backup -g` uses it to find
repos),
`CLAUDE_SESSIONS` + `read_registry()` + `live_session_pid()` (the
running-process registry; `read_registry()` returns every record unvetted,
and each caller decides liveness its own way), `transcripts_for()` (the
`<uuid>.jsonl` lookup across project dirs, shared by `resolve_session()`
and `claude-traffic-monitor`),
`mangle_cwd()`, `find_project_dir()`, `project_label()`, `has_human_prose()`
(strips known wrapper tags listed in `USER_WRAPPER_TAGS` — `<command-name>`,
`<system-reminder>`, `<local-command-caveat>`, `<bash-input>`, etc. — and
reports whether anything is left), `read_session_meta()` (one-pass scan:
titles, cwd, first/last timestamps, `human_prompts` count using
`has_human_prose`, `assistant_turns` count, all returned as a `SessionMeta`
dataclass with an `is_empty` property), `iter_sessions()`, `list_sessions()`,
and `resolve_session()` (UUID-or-title-or-path → `.jsonl` path). Used by
`claude-session-report`, `claude-session-list`, `claude-session-find`,
`claude-session-rename`, `claude-sessions-review`, `claude-traffic-monitor`,
`bd-verify-backup`, and `bd-complete` — `claude-session-find`
predated this module and carried its own copies until beads-utils-8ju
folded them in. Also stdlib-only.

## Manual checks

```bash
./claude-session-find 'bd-log'                 # Sessions in this project matching
./claude-session-find -g 'paged_output'        # All projects
./claude-session-find -a 'dolt push'           # Include assistant/tool content
./claude-session-find --oneline 'bd-log'       # One row per session, no snippets
./claude-session-find -q foo | head -1         # UUID only (for `claude --resume`)
./claude-session-report <uuid>                 # Default discussion-only render
./claude-session-report 'bd-view'              # Substring-match a session title
./claude-session-report <uuid> --thinking --tools     # Add agent thinking + tool I/O
./claude-session-report <uuid> --all > session.md     # Everything, to a file
./claude-session-list                                  # Recent sessions for cwd's project
./claude-session-list -g --oneline                     # Every project, one row each
./claude-session-list -q | head -1                     # Newest UUID (for `claude --resume`)
./claude-session-rename <uuid> 'Pager design'          # /rename without starting the session
./claude-session-rename 'old title' 'new title'        # Resolve by title substring
./claude-sessions-review                               # Recurring failures, this project
./claude-sessions-review -g --since 2w                 # Every project, last two weeks
./claude-sessions-review -g --kind denied              # What gets rejected or denied
./claude-sessions-review -g --json | head -40          # What /dream would read
```
