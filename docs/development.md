# Development

## Make targets

There's still no package and no build step — but there is a `Makefile`, so you
don't have to remember any of the invocations. `make help` lists everything:

```bash
make test        # run the test suite
make check       # ruff, plus a --version smoke test of every script
make ci          # everything CI runs
make dolt-check  # verify this repo's own beads data is pushed
make screenshots # regenerate the terminal images in docs/img
make install     # symlink the scripts onto your PATH
make install-claude  # symlink the skills and hooks into ~/.claude
```

Dependencies resolve through `uv` into a throwaway environment, so nothing is
installed globally. CI runs these same targets, so a green `make ci` locally
means a green CI.

## The test suite

The suite in [`tests/`](../tests) is fixtures all the way down: `bd` and `dolt`
are replaced by programmable fakes on `PATH`, and Claude session history by
synthetic `.jsonl` trees under a temporary `HOME`. Nothing touches a real beads
project or your session history. The hooks run as bash subprocesses against
git repos built under a temporary directory, and the docs are checked too:
every relative link and image in the README and these pages must resolve.

## Shell completion

Tab completion for zsh and bash lives in [`completions/`](../completions).
`bd-view` completes bead ids (with titles shown in zsh),
`claude-session-report` and `claude-session-rename` complete session
uuids/titles, the project-path
scripts complete directories, and every script completes its flags.
Options that take a value complete in either spelling (`--id beads-1` or
`--id=beads-1`), and the comma-separated ones with a known vocabulary
(`bd-log`'s `--id`, `--only`, `--about` and `--status`;
`claude-session-list --sort`) complete one element at a time, so
`--only=create,ch` finishes as `--only=create,change`.

Source the file for your shell from your rc file:

```bash
# ~/.zshrc  (oh-my-zsh users: put this *after* `source $ZSH/oh-my-zsh.sh`)
source /path/to/beads-utils/completions/beads-utils.zsh
# ~/.bashrc
source /path/to/beads-utils/completions/beads-utils.bash
```

The scripts (including `bd-complete`, which feeds the dynamic candidates)
must be on your `$PATH`. The file is read when the shell starts, so after
pulling a release that adds a flag, start a new shell — an existing one
still holds the old definitions and will complete nothing for it.
Prefer the autoload convention instead? Drop
`beads-utils.zsh` into a directory on your `$fpath`, or `beads-utils.bash`
into your `bash-completion.d`.

## Conventions and design notes

Conventions live in [`CLAUDE.md`](../CLAUDE.md) and per-script design
notes in [`.claude/rules/`](../.claude/rules); see
[`CONTRIBUTING.md`](../CONTRIBUTING.md) to contribute.
