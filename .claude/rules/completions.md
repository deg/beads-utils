---
paths:
  - "completions/**"
  - "bd-complete"
  - "tests/test_completions.py"
  - "tests/test_bd_complete.py"
---

# Shell completion design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

## bd-complete

`bd-complete` — Emits shell-completion candidates as
`value<TAB>description` lines; the single front door behind the
zsh/bash completion in `completions/` (so candidate logic is never
duplicated across shells, and a future TTL cache has one wrap point).
`bd-complete ids` lists full bead ids (e.g. `beads-utils-v9o.4`) from
`bd list --status=all` — full rather than the short suffix so a
wrong-project id is visible at the prompt.
`bd-complete sessions` calls into `claudeutils.list_sessions()`
directly. Lookups fail silently (no output, exit 0) so a
broken/slow command never garbles the prompt.

Since bd 1.3.0, `--status=all` no longer hides pinned beads, so pinned
beads now complete too. That is wanted: completion offers every bead.

## Shell-specific corrections

Both files carry two shell-specific corrections that are invisible until a
particular spelling stops completing (each was a live defect; see
beads-utils-dk6):

- **`--opt=value` must be declared.** zsh's `_arguments` matches the option
  name literally, so a value-taking long option is spelled `--id=[…]` and a
  short one `-n+[…]`. Without the marker only the space-separated form
  completes and `--id=bea` falls through to the positional, offering nothing —
  which is the form the epilogs and this file use throughout. The marker also
  forces short/long pairs with a value apart into two specs: `{-n,--limit}`
  can't carry both markers, and `-n=5` isn't valid `argparse`. In bash the
  same spelling breaks differently: `=` is in `COMP_WORDBREAKS`, so `--id=bea`
  arrives as three words and `case $prev` never fires; `__beads_split_eq`
  folds them back, assigning to its *caller's* `cur`/`prev` via bash's dynamic
  scoping.
- **Comma-separated options complete one element at a time.** In zsh each
  emitter opens with `compset -P '*,'`; in bash the value helpers split the
  word at the last comma and re-attach the prefix to every candidate (`,` is
  not a word break, so the current word is the whole `a,b`). The bash split
  helper assigns to caller variables rather than echoing a result — a command
  substitution is a subshell, so the prefix would never escape it.

The completion files are read at *shell startup*. A shell that predates a new
flag holds the old definitions and completes nothing for it; that is not a bug
in the file, and it is what the original beads-utils-dk6 report turned out to
be.

## Verifying

Shell completion has two layers of verification. `tests/test_completions.py`
covers what can be read off the files — that both transcriptions match each
script's `argparse`, and that value-taking options carry the zsh marker — by
intercepting `parse_args` to get the real parser rather than parsing `--help`
(the epilogs are full of example command lines, and every flag in one would
otherwise register as defined). What it cannot cover is whether zsh and bash
*behave*, so also tab-complete in a real shell after changing these files
(`source completions/beads-utils.zsh` / `.bash`, then `bd-view <TAB>`). Worth
trying both spellings and a comma: `bd-log --id=<TAB>` and
`bd-log --only=create,<TAB>` are the two shapes that silently regressed
before. Both files offer only the three canonical `--only` verbs; `start` and
`close` still work but are not advertised, since five names for three things
read as five choices.

## Manual checks

```bash
./bd-complete ids                                      # Completion feed: short ids + titles
./bd-complete sessions                                 # Completion feed: session uuids + titles
```
