# bash tab completion for beads-utils.
#
# Install: source this file from your ~/.bashrc, e.g.
#     source /path/to/beads-utils/completions/beads-utils.bash
#
# Note that the file is read at *shell startup*, so a shell already running
# when a flag was added still has the old completers in memory and completes
# nothing for the new flag. Start a new shell after pulling.
#
# All dynamic candidates come from the `bd-complete` helper — no enumeration
# logic lives here, which is what keeps bash and zsh in sync. `bd-complete`
# must be on $PATH (it ships alongside the scripts in this repo).
#
# bash completion can't show the title beside each candidate the way zsh does,
# so only the value column (bead id / session uuid) is offered.
#
# Two readline quirks every completer below has to absorb, both of which used
# to silently produce no candidates at all:
#
#   * `=` is in COMP_WORDBREAKS, so `--id=bea` arrives as three words
#     (`--id`, `=`, `bea`) and `--id=` as two with `=` as the current one.
#     `__beads_split_eq` folds those back together — see there.
#   * `,` is *not* a word break, so the current word for `--id a,b` is the
#     whole `a,b`. The value helpers complete the final element and re-attach
#     everything before it.

# --- shared glue ----------------------------------------------------------
# The helpers read `$cur` / `$prev` from their caller rather than recomputing
# them: bash's dynamic scoping makes the caller's locals visible, and the
# caller has already normalized them via __beads_split_eq. Every completer
# below therefore declares both.

__beads_split_eq() {
  # Undo readline's splitting of `--opt=value` on the `=` word break, so a
  # completer can keep matching on plain option names. Assigns to the caller's
  # `cur`/`prev` (dynamic scoping), which is the whole point of the helper.
  if [[ $cur == "=" ]]; then
    cur=""
  elif [[ $prev == "=" ]]; then
    prev=${COMP_WORDS[COMP_CWORD-2]}
  fi
}

__beads_split_list() {
  # Split the current word at its last comma, for options that take a
  # comma-separated list. Assigns to the caller's `__word` (the element to
  # complete) and `__pfx` (the part to re-attach, empty when there is no
  # comma). Assignment rather than an echoed result on purpose: a command
  # substitution runs in a subshell, where the caller would never see `__pfx`.
  __pfx=""
  __word=$cur
  if [[ $__word == *,* ]]; then
    __pfx="${__word%,*},"
    __word="${__word##*,}"
  fi
}

__beads_values() {
  # $1 = bd-complete subcommand (ids|sessions). Completes the value column.
  local __pfx __word values
  __beads_split_list
  values=$(bd-complete "$1" 2>/dev/null | cut -f1)
  COMPREPLY=($(compgen -W "$values" -- "$__word"))
  if [[ -n $__pfx ]]; then
    COMPREPLY=("${COMPREPLY[@]/#/$__pfx}")
  fi
  return 0
}

__beads_wordlist() {
  # $1 = space-separated candidates for one element of a comma-separated list.
  local __pfx __word
  __beads_split_list
  COMPREPLY=($(compgen -W "$1" -- "$__word"))
  if [[ -n $__pfx ]]; then
    COMPREPLY=("${COMPREPLY[@]/#/$__pfx}")
  fi
  return 0
}

__beads_dirs() {
  if declare -F _filedir >/dev/null; then
    _filedir -d
  else
    COMPREPLY=($(compgen -d -- "$cur"))
  fi
  return 0
}

__beads_files() {
  if declare -F _filedir >/dev/null; then
    _filedir
  else
    COMPREPLY=($(compgen -f -- "$cur"))
  fi
  return 0
}

__beads_flags() {
  # $1 = space-separated flag list.
  COMPREPLY=($(compgen -W "$1" -- "$cur"))
  return 0
}

# --- per-command completers -----------------------------------------------
# Flag lists are transcribed from each script's argparse definition —
# tests/test_completions.py fails if they drift.

_beads_bd_view() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  __beads_split_eq
  if [[ $cur == -* ]]; then
    __beads_flags "--no-pager --version -h --help"
  else
    __beads_values ids
  fi
}

_beads_claude_session_report() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  __beads_split_eq
  if [[ $cur == -* ]]; then
    __beads_flags "--prompts --no-prompts --replies --no-replies \
      --slash-commands --no-slash-commands --thinking \
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
  __beads_split_eq
  case $prev in
    -s|--sort)
      __beads_wordlist "started last duration prompts replies turns title project id"
      return ;;
    -n|--limit|--min-prompts|-m|--match) return ;;
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
  __beads_split_eq
  case $prev in
    --only)
      __beads_wordlist "create start close"
      return ;;
    --status)
      __beads_wordlist "open in_progress blocked deferred closed pinned hooked"
      return ;;
    --id)
      __beads_values ids
      return ;;
    --color)
      COMPREPLY=($(compgen -W "auto always never" -- "$cur"))
      return 0 ;;
    -n|--limit|--since) return ;;
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
  __beads_split_eq
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
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  __beads_split_eq
  if [[ $cur == -* ]]; then
    __beads_flags "--version -h --help"
  else
    __beads_dirs
  fi
}

_beads_bd_dolt_diff() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  COMPREPLY=()
  __beads_split_eq
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
  __beads_split_eq
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
