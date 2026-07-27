# bash tab completion for beads-utils.
#
# Install: source this file from your ~/.bashrc, e.g.
#     source /path/to/beads-utils/completions/beads-utils.bash
#
# All dynamic candidates come from the `bd-complete` helper — no enumeration
# logic lives here, which is what keeps bash and zsh in sync. `bd-complete`
# must be on $PATH (it ships alongside the scripts in this repo).
#
# bash completion can't show the title beside each candidate the way zsh does,
# so only the value column (bead id / session uuid) is offered.

# --- shared glue ----------------------------------------------------------
# `bd-complete` is the only call site for dynamic data; a future TTL cache
# wraps it, so nothing here changes.

__beads_values() {
  # $1 = bd-complete subcommand (ids|sessions). Completes the value column.
  local cur=${COMP_WORDS[COMP_CWORD]} values
  values=$(bd-complete "$1" 2>/dev/null | cut -f1)
  COMPREPLY=($(compgen -W "$values" -- "$cur"))
}

__beads_dirs() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  if declare -F _filedir >/dev/null; then
    _filedir -d
  else
    COMPREPLY=($(compgen -d -- "$cur"))
  fi
}

__beads_files() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  if declare -F _filedir >/dev/null; then
    _filedir
  else
    COMPREPLY=($(compgen -f -- "$cur"))
  fi
}

__beads_flags() {
  # $1 = space-separated flag list.
  local cur=${COMP_WORDS[COMP_CWORD]}
  COMPREPLY=($(compgen -W "$1" -- "$cur"))
}

# --- per-command completers -----------------------------------------------
# Flag lists are transcribed from each script's argparse definition.

_beads_bd_view() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  COMPREPLY=()
  if [[ $cur == -* ]]; then
    __beads_flags "--no-pager --version -h --help"
  else
    __beads_values ids
  fi
}

_beads_claude_session_report() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  COMPREPLY=()
  if [[ $cur == -* ]]; then
    __beads_flags "--no-prompts --no-replies --no-slash-commands --thinking \
      --tools --slash-bodies --bash-shortcuts --system-reminders \
      --task-notifications --sidechains --all --no-pager \
      --version -h --help"
  else
    __beads_values sessions
  fi
}

_beads_claude_session_list() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  case $prev in
    -n|--limit|--min-prompts|-s|--sort|-m|--match) return ;;
  esac
  if [[ $cur == -* ]]; then
    __beads_flags "-g --global -n --limit -s --sort -m --match \
      -a --all --min-prompts --oneline -q --quiet --no-pager \
      --version -h --help"
  fi
  # no positional args.
}

_beads_bd_log() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  case $prev in
    --status)
      COMPREPLY=( $(compgen -W "open in_progress blocked deferred closed pinned hooked" -- "$cur") )
      return ;;
    --id)
      __beads_values ids
      return ;;
    --color)
      COMPREPLY=( $(compgen -W "auto always never" -- "$cur") )
      return ;;
    -n|--limit|--only|--since) return ;;
  esac
  if [[ $cur == -* ]]; then
    __beads_flags "-n --limit --only --status --open --id --children --since --no-pager --color --version -h --help"
  else
    __beads_dirs
  fi
}

_beads_bd_export_csv() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  case $prev in
    -o|--output) __beads_files; return ;;
    -s|--sort) return ;;
  esac
  if [[ $cur == -* ]]; then
    __beads_flags "-o --output -s --sort --version -h --help"
  else
    __beads_dirs
  fi
}

_beads_bd_dolt_check() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  COMPREPLY=()
  if [[ $cur == -* ]]; then
    __beads_flags "--version -h --help"
  else
    __beads_dirs
  fi
}

_beads_bd_dolt_diff() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  case $prev in
    # Dolt revisions and remote names aren't enumerable via bd-complete.
    --base|--head|--remote) return ;;
  esac
  if [[ $cur == -* ]]; then
    __beads_flags "--base --head --remote --no-fetch --full --no-pager \
      --version -h --help"
  else
    __beads_dirs
  fi
}

_beads_claude_session_find() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  case $prev in
    -n|--limit) return ;;
  esac
  if [[ $cur == -* ]]; then
    __beads_flags "-g --global -a --all -q --quiet -n --limit --no-pager \
      --version -h --help"
  fi
  # positional is a free-text query — nothing to complete.
}

complete -F _beads_bd_view bd-view
complete -F _beads_claude_session_report claude-session-report
complete -F _beads_claude_session_list claude-session-list
complete -F _beads_bd_log bd-log
complete -F _beads_bd_export_csv bd-export-csv
complete -F _beads_bd_dolt_check bd-dolt-check
complete -F _beads_bd_dolt_diff bd-dolt-diff
complete -F _beads_claude_session_find claude-session-find
