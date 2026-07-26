#compdef bd-view bd-log bd-export-csv bd-dolt-check bd-dolt-diff claude-session-find claude-session-list claude-session-report
#
# zsh tab completion for beads-utils.
#
# Install: source this file from your ~/.zshrc, e.g.
#     source /path/to/beads-utils/completions/beads-utils.zsh
# (oh-my-zsh users: place the line *after* `source $ZSH/oh-my-zsh.sh`, so
# compinit has already run.)
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

# Belt-and-suspenders: keep `_`-prefixed names (this file's helpers) out of
# *command-name* completion. Appended rather than clobbering any user value.
() {
  local -a _ignored
  zstyle -a ':completion:*:*:-command-:*:*' ignored-patterns _ignored
  if (( ! ${_ignored[(Ie)_*]} )); then
    zstyle ':completion:*:*:-command-:*:*' ignored-patterns "${_ignored[@]}" '_*'
  fi
}

# --- dynamic candidate emitters -------------------------------------------
# The only call sites for dynamic data; a future TTL cache wraps `bd-complete`
# itself, so nothing here changes.

__beads_ids() {
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

# --- single dispatcher ----------------------------------------------------
# Registered (below) for every command via one compdef; `$service` is the
# command being completed. Flag lists are transcribed from each script's
# argparse definition. Positionals delegate to the emitters above (dynamic)
# or to _files (paths).

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
      '--no-prompts[hide human-typed user text]' \
      '--no-replies[hide assistant text replies]' \
      '--no-slash-commands[hide /slash-command turns]' \
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
      '(-n --limit)'{-n,--limit}'[max sessions to show (0 = unlimited)]:count' \
      '(-s --sort)'{-s,--sort}'[comma-separated sort keys (-key for descending)]:keys' \
      '(-m --match)'{-m,--match}'[show only sessions whose title or uuid contains PATTERN]:pattern' \
      '(-a --all --min-prompts)'{-a,--all}'[show every session, including empty ones]' \
      '(-a --all --min-prompts)--min-prompts[only sessions with >= N human prompts]:count' \
      '(--oneline -q --quiet)--oneline[single-row output]' \
      '(--oneline -q --quiet)'{-q,--quiet}'[print only session UUIDs]' \
      '--no-pager[write directly to stdout; skip the pager]'
    ;;
  bd-log)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(-n --limit)'{-n,--limit}'[max events to show (0 = unlimited)]:count' \
      '--only[comma-separated event kinds to include]:kinds' \
      '(--status --open)--status[include only beads with these current statuses]:statuses:(open in_progress blocked deferred closed pinned hooked)' \
      '(--status --open)--open[shorthand: only beads still open (not closed)]' \
      '--since[show only events on/after DATE]:date' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '1:project:_files -/'
    ;;
  bd-export-csv)
    _arguments -s -S \
      '(- *)--version[show version and exit]' \
      '(- *)'{-h,--help}'[show help and exit]' \
      '(-o --output)'{-o,--output}'[output CSV path]:file:_files' \
      '(-s --sort)'{-s,--sort}'[comma-separated sort keys (-key for descending)]:keys' \
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
      '--base[revision to treat as before (default: remote-tracking ref)]:rev' \
      '--head[revision to treat as after (default: local branch)]:rev' \
      '--remote[Dolt remote name]:remote' \
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
      '(-n --limit)'{-n,--limit}'[max matching sessions to show (0 = unlimited)]:count' \
      '--no-pager[write directly to stdout; skip the pager]' \
      '1:query:'
    ;;
  esac
}

compdef _beads_dispatch \
  bd-view bd-log bd-export-csv bd-dolt-check bd-dolt-diff \
  claude-session-find claude-session-list claude-session-report
