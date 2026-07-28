# Contributing to beads-utils

Thanks for your interest! This is a small collection of Python CLI scripts that
augment the [`bd`](https://github.com/steveyegge/beads) issue tracker.

The current setup is deliberately minimal — no package, no build step, no
installer — but that's a starting point, not a principle. Contributions are
welcome, including:

- **New scripts** that fit the collection — something else useful built on top
  of `bd`, its Dolt storage, or Claude Code sessions.
- **Improvements to the project itself** — packaging, more CI, or other
  tooling. The bar is low here; if you want to add scaffolding this repo
  doesn't have yet, go for it.
- **Fixes and refinements** to the existing scripts.

The one standing preference is to stay reasonably dependency-light (see
[Conventions](#conventions)) — but that's a default to discuss, not a veto.

## How the repo works

There is **no package, no build step, and no installer**. Each script lives at
the repo root next to a shared `bdutils.py` helper and runs directly:

```bash
./bd-log -n 5            # run any script from the repo directory
./bd-view --help         # every script supports --help and --version
```

Scripts must be run from the repo directory — Python puts the script's own
directory on `sys.path[0]`, which is how `from bdutils import ...` resolves the
sibling helper without any install. All scripts use Python 3 standard library
only, except `bd-view`, whose `#!/usr/bin/env -S uv run --script` shebang pulls
`rich` from a per-script `uv` cache (so nothing is added to any global env).

## Testing

There is a pytest suite in [`tests/`](tests). Everything runs through the
`Makefile` — `make help` lists every target:

```bash
make test                                          # the whole suite
make test PYTEST_ARGS=tests/test_bd_log.py         # one file
make check                                         # ruff + a --version smoke test
make ci                                            # everything CI runs
```

Dependencies resolve through `uv` into a throwaway environment, so nothing
lands in a global one. CI invokes these same targets, so a green `make ci`
locally is a green CI.

How it's put together, if you're adding to it:

- **Loading the scripts.** They're executables with no `.py` extension, so
  `tests/conftest.py` provides `load_script("bd-log")` (a `SourceFileLoader`
  import). `pytest.ini` puts the repo root on `sys.path` so the scripts'
  `from bdutils import ...` resolves the way it does in real use.
- **No real external state.** `bd` and `dolt` are replaced by programmable
  fakes on `PATH` (the `fake_bd` / `fake_dolt` fixtures); Claude session
  history is synthetic `.jsonl` written under `tmp_path`. The suite never
  reads a real beads project or your session history.
- **Two failure-output styles.** `bdutils.error()` calls `sys.exit(str)`, whose
  message the interpreter prints — invisible to `capsys`, so assert on
  `excinfo.value.code`. `warn()` writes to stderr directly and *is* captured.
- **Timezone.** `format_ts()` renders local time, so a session fixture pins
  `TZ=UTC`. Don't assert a formatted timestamp without it.
- **Optional deps.** `make test` installs `rich` so bd-view's rendering tests
  run; `make test-minimal` omits it, and they should *skip* — three of them,
  loudly. That's the check that the fallback path isn't quietly standing in
  for the real one.

Also verify changes **manually against a real beads project** — this repo is
itself one — and describe what you ran in the PR:

```bash
make export-csv                   # exercise against this repo
```

## Conventions

The authoritative list lives in [`CLAUDE.md`](CLAUDE.md). The essentials:

- **Shebang**: `#!/usr/bin/env python3` (no hardcoded paths). Use the `uv`
  shebang only when a third-party dependency is genuinely load-bearing.
- **Python**: `from __future__ import annotations`; standard library only by
  default. `bdutils.py` itself stays stdlib-only.
- **Argument parsing**: `argparse` with `RawDescriptionHelpFormatter` and an
  `epilog` of examples when a richer help block helps.
- **Versioning**: scripts share `bdutils.__version__`; add `--version` via
  `bdutils.add_version_arg(parser)`. Paging scripts accept `--no-pager`.
  Don't bump the version in a PR — add a bullet under `## Unreleased` in
  [`CHANGELOG.md`](CHANGELOG.md) instead; the number moves only at release time.
- **Errors / warnings**: `bdutils.error(msg)` (exits non-zero with a lowercase
  `error: …`) and `bdutils.warn(msg)`. Never surface a raw traceback.
- **Project path**: `bdutils.resolve_project_path(arg)` for the
  expanduser/resolve/`.beads/`-validation dance.

If you add behavior or flags, update `README.md` and `CLAUDE.md` to match.

## Releases

Maintainer-only, and nothing to do on your side beyond the `## Unreleased` note
described above. The conventions live in [`CLAUDE.md`](CLAUDE.md); the procedure
is scripted as the `/release` Claude Code slash command
([`.claude/commands/release.md`](.claude/commands/release.md)).

## Issue tracking

This project's own work is tracked in **beads (`bd`)**, stored in the Dolt
remote alongside the git data — not in GitHub Issues. You don't need `bd` to
contribute: open a normal GitHub issue for a bug or idea and the maintainer
will triage accepted work into beads. Discussion and questions are welcome
there too.

## Submitting changes

1. Fork and create a topic branch.
2. Keep changes focused and match the surrounding style.
3. Run the test suite, and the affected script(s) manually. New behavior wants
   a test; a bug fix wants the test that would have caught it.
4. Open a pull request and fill out the template.

Contributions are accepted under the project's [MIT License](LICENSE).
