# Contributing to beads-utils

Thanks for your interest! This is a small collection of Python CLI scripts that
augment the [`bd`](https://github.com/steveyegge/beads) issue tracker.

The current setup is deliberately minimal — no package, no CI, no automated
tests — but that's a starting point, not a principle. Contributions are
welcome, including:

- **New scripts** that fit the collection — something else useful built on top
  of `bd`, its Dolt storage, or Claude Code sessions.
- **Improvements to the project itself** — tests, a CI check, packaging, or
  other tooling. The bar is low here; if you want to add scaffolding this repo
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

There is no automated test suite. Verify changes **manually against a real
beads project** — this repo is itself one:

```bash
./bd-export-csv .                 # exercise against this repo
python3 -m py_compile <files>     # at minimum, confirm everything still compiles
```

When you open a PR, describe what you ran and what you observed.

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
3. Run the affected script(s) manually and `python3 -m py_compile` on what you
   touched.
4. Open a pull request and fill out the template.

Contributions are accepted under the project's [MIT License](LICENSE).
