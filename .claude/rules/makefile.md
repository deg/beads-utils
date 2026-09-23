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
- `LINT_TARGETS` names `*.py` and `tests/` explicitly alongside `$(SCRIPTS)`.
  Shebang discovery finds neither the helper modules (no shebang — which is
  how `claudeutils.py` went unlinted until the Makefile landed) nor anything
  in a subdirectory.
- `tests/` is named explicitly in CI's ruff arguments. Shebang discovery uses
  `grep -lE -d skip '^#!' *`, which only looks at the repo root and skips
  subdirectories, so the tests would otherwise never be linted.

`tests/test_makefile.py` is the one file that invokes `make` itself, marked
`makefile` and skipped when make is absent. Its cheap tier reads `make -n`
output rather than running anything, which is enough for the whole class of
variable-expansion bug that produced `f066e16` — a `PREFIX=~/bin` that built a
directory literally named `~`. Two rules for anything added there: never
invoke `make test` or `make ci` (that recurses), and always pass an explicit
`PREFIX` under `tmp_path`, or the suite installs into the developer's real
`~/.local/bin`.
