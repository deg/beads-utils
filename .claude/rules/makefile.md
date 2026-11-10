---
paths:
  - "Makefile"
  - "tests/test_makefile.py"
---

# Makefile design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

Two Makefile details worth knowing before editing it:

- `SCRIPTS` is discovered by shebang, via `HASH := \#` indirection. An inline
  `'^#!'` inside `$(shell ...)` does not work: make strips `#` and everything
  after it *before* parsing the function call, truncating it mid-expression.
- `SCRIPTS` runs the grep inside `bin/`, so the names come out bare
  (`bd-log`): `install` links each into `PREFIX` under that name, and the
  recipes that run a script spell out `$(BIN)/`. Scripts lived at the repo
  root until beads-utils-b9k (Move scripts into bin/); `uninstall` still
  recognises links to a file directly at the root, which an older install made.
- `LINT_TARGETS` names each script as `bin/<script>`, plus `bin/`, `tests/` and
  `tools/`. Ruff given a directory lints only its `*.py` files, so the
  extension-less scripts must be named one by one, and `bin/` is what covers the
  helper modules, which have no shebang (which is how `claudeutils.py` went
  unlinted until the Makefile landed).

`tests/test_makefile.py` is the one file that invokes `make` itself, marked
`makefile` and skipped when make is absent. Its cheap tier reads `make -n`
output rather than running anything, which is enough for the whole class of
variable-expansion bug that produced `f066e16` — a `PREFIX=~/bin` that built a
directory literally named `~`. Two rules for anything added there: never
invoke `make test` or `make ci` (that recurses), and always pass an explicit
`PREFIX` under `tmp_path`, or the suite installs into the developer's real
`~/.local/bin`. The same goes for `CLAUDE_HOME` and the `install-claude` tests,
which would otherwise link into the real `~/.claude/hooks`. `uninstall-claude`
removes with `unlink` rather than `rm -f`: one path, no recursion, which is all a
symlink needs. `make doctor`, `install` and `install-claude` run `tools/doctor.py`, which reports
the tools and, on a terminal, offers to install each missing one; it never prompts
a pipe, so CI and the tests get the report alone, and `DOCTOR_RUN=echo` makes it
print an install command instead of running it. `--for install-claude` exits 1 when
jq is still missing, and that target runs it before linking so a refusal is not a
half-install. The tests put only `python3` on `PATH` to make every other tool missing.
