#compdef bd-view bd-log bd-export-csv bd-dolt-check bd-dolt-diff claude-session-find claude-session-list claude-session-report
#
# zsh tab completion for beads-utils.
#
# Install: source this file from your ~/.zshrc, e.g.
#     source /path/to/beads-utils/completions/beads-utils.zsh
# (oh-my-zsh users: place the line *after* `source $ZSH/oh-my-zsh.sh`, so
# compinit has already run.)
#
# Note that the file is read at *shell startup*, so a shell already running
# when a flag was added still has the old dispatcher in memory and completes
# nothing for the new flag. Start a new shell after pulling.
#
# All dynamic candidates come from the `bd-complete` helper — no enumeration
# logic lives here, which is what keeps zsh and bash in sync. `bd-complete`
# must be on $PATH (it ships alongside the scripts in this repo).
#
# Why a single dispatcher instead of one `_bd-view` / `_bd-dolt-check` per
# command: oh-my-zsh's default matcher does *substring* completion (`r:|=*`),
# so a live function literally named `_bd-dolt-check` surfaces as a candidate
# when you type `bd-do` in command position. The dispatcher name shares no
# substring with the commands, so that can't happen.
#
# Two spelling rules the specs below follow, because `_arguments` matches on
# the option name exactly as written:
#
#   * a long option that takes a value ends in `=` (`--id=[...]`). Without it
#     only `--id VALUE` completes and `--id=VALUE` — the form this repo's own
#     docs and help text use throughout — silently falls through to the
#     positional and offers nothing.
#   * a short option that takes a value ends in `+` (`-n+[...]`), which allows
#     both `-n5` and `-n 5`. That is why short/long pairs with a value are
#     written as two specs rather than one `{-n,--limit}` brace: the two halves
#     need different markers (`-n=5` is not something argparse accepts).

# Belt-and-suspenders: keep `_`-prefixed names (this file's helpers) out of
# *command-name* completion. Appended rather than clobbering any user value.
() {
  local -a _ignored
  zstyle -a ':completion:*:*:-command-:*:*' ignored-patterns _ignored
  if (( ! ${_ignored[(Ie)_*]} )); then
    zstyle ':completion:*:*:-command-:*:*' ignored-patterns "${_ignored[@]}" '_*'
  fi
}

# --- candidate emitters ---------------------------------------------------
# The only call sites for dynamic data; a future TTL cache wraps `bd-complete`
# itself, so nothing here changes.
#
# Every emitter for a comma-separated option opens with `compset -P '*,'`,
# which moves everything through the last comma into IPREFIX. Without it the
# whole `a,b` string is matched against the candidate set and a second element
# never completes. It is a no-op on the single-valued uses (bd-view's bead
# argument), since no comma is ever typed there.

__beads_ids() {
  compset -P '*,'
  local -a items
  local line
  for line in "${(@f)$(bd-complete ids 2>/dev/null)}"; do
    [[ -z $line ]] && continue
    # bd-complete emits value<TAB>description; _describe wants value:description.
    items+=("${line/$'\t'/:}")
  done
  _describe -t beads 'bead' items
}

__beads_sessions() {
  local -a items
  local line
  for line in "${(@f)$(bd-complete sessions 2>/dev/null)}"; do
    [[ -z $line ]] && continue
    items+=("${line/$'\t'/:}")
  done
  _describe -t sessions 'session' items
}

__beads_event_kinds() {
  compset -P '*,'
  local -a kinds=(create start close)
  _describe -t kinds 'event kind' kinds
}

__beads_statuses() {
  # bd owns this vocabulary (bd-log passes --status straight through); the
  # list is a convenience, not a validation.
  compset -P '*,'
  local -a statuses=(open in_progress blocked deferred closed pinned hooked)
  _describe -t statuses 'status' statuses
}

__beads_session_sort_keys() {
  # A leading `-` selects descending order, so it is consumed like the comma
  # and the bare key still completes behind it.
  compset -P '*,'
  compset -P -
  local -a keys=(started last duration prompts replies turns title project id)
  _describe -t sortkeys 'sort key' keys
}

# --- single dispatcher ----------------------------------------------------
# Registered (below) for every command via one compdef; `$service` is the
# command being completed. Flag lists are transcribed from each script's
# argparse definition — tests/test_completions.py fails if they drift.
# Positionals delegate to the emitters above (dynamic) or to _files (paths).

_beads_dispatch() {
  case $service in
  bd-view)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '1:bead:__beads_ids'
    ;;
  claude-session-report)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(--prompts --no-prompts)--prompts[include human-typed user text]' \
      '(--prompts --no-prompts)--no-prompts[hide human-typed user text]' \
      '(--replies --no-replies)--replies[include assistant text replies]' \
      '(--replies --no-replies)--no-replies[hide assistant text replies]' \
      '(--slash-commands --no-slash-commands)--slash-commands[include /slash-command turns]' \
      '(--slash-commands --no-slash-commands)--no-slash-commands[hide /slash-command turns]' \
      '--thinking[include extended-thinking blocks]' \
      '--tools[include tool calls and results]' \
      '--slash-bodies[include slash-command skill bodies]' \
      '--bash-shortcuts[include ! shell shortcuts]' \
      '--system-reminders[include <system-reminder> blocks]' \
      '--task-notifications[include background task notifications]' \
      '--sidechains[include sidechain subagent entries]' \
      '--all[enable every channel]' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '1:session:__beads_sessions'
    ;;
  claude-session-list)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(-g --global)'{-g,--global}'[list sessions across all projects]' \
      '(-n --limit)-n+[max sessions to show (0 = unlimited)]:count' \
      '(-n --limit)--limit=[max sessions to show (0 = unlimited)]:count' \
      '(-s --sort)-s+[comma-separated sort keys (-key for descending)]:keys:__beads_session_sort_keys' \
      '(-s --sort)--sort=[comma-separated sort keys (-key for descending)]:keys:__beads_session_sort_keys' \
      '(-m --match)-m+[show only sessions whose title or uuid contains PATTERN]:pattern' \
      '(-m --match)--match=[show only sessions whose title or uuid contains PATTERN]:pattern' \
      '(-a --all --min-prompts)'{-a,--all}'[show every session, including empty ones]' \
      '(-a --all --min-prompts)--min-prompts=[only sessions with >= N human prompts]:count' \
      '(--oneline -q --quiet)--oneline[single-row output]' \
      '(--oneline -q --quiet)'{-q,--quiet}'[print only session UUIDs]' \
      '--no-pager[write directly to stdout; skip the pager]'
    ;;
  bd-log)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(-n --limit)-n+[max events to show (0 = unlimited)]:count' \
      '(-n --limit)--limit=[max events to show (0 = unlimited)]:count' \
      '--only=[comma-separated event kinds to include]:kinds:__beads_event_kinds' \
      '(--status --open)--status=[include only beads with these current statuses]:statuses:__beads_statuses' \
      '(--status --open)--open[shorthand: only beads still open (not closed)]' \
      '--id=[include only these beads (comma-separated full bead ids)]:ids:__beads_ids' \
      '--children[with --id, also include every bead under each named id]' \
      '--since=[show only events on/after DATE]:date' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '--color=[colorize events by kind]:when:(auto always never)' \
      '1:project:_files -/'
    ;;
  bd-export-csv)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(-o --output)-o+[output CSV path]:file:_files' \
      '(-o --output)--output=[output CSV path]:file:_files' \
      '(-s --sort)-s+[comma-separated sort keys (-key for descending)]:keys' \
      '(-s --sort)--sort=[comma-separated sort keys (-key for descending)]:keys' \
      '1:project:_files -/'
    ;;
  bd-dolt-check)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '1:project:_files -/'
    ;;
  bd-dolt-diff)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '--base=[revision to treat as before (default: remote-tracking ref)]:rev' \
      '--head=[revision to treat as after (default: local branch)]:rev' \
      '--remote=[Dolt remote name]:remote' \
      '--no-fetch[skip dolt fetch; compare against last-known remote-tracking ref]' \
      '--full[show complete field values instead of truncating]' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '1:project:_files -/'
    ;;
  claude-session-find)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(-g --global)'{-g,--global}'[search all projects under ~/.claude/projects]' \
      '(-a --all)'{-a,--all}'[search assistant/thinking/tool content too]' \
      '(-q --quiet)'{-q,--quiet}'[print only matching session IDs]' \
      '(-n --limit)-n+[max matching sessions to show (0 = unlimited)]:count' \
      '(-n --limit)--limit=[max matching sessions to show (0 = unlimited)]:count' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '1:query:'
    ;;
  esac
}

compdef _beads_dispatch \
  bd-view bd-log bd-export-csv bd-dolt-check bd-dolt-diff \
  claude-session-find claude-session-list claude-session-report
