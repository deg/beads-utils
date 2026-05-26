<!-- Thanks for contributing! Keep changes focused and dependency-light. -->

## What

<!-- What does this change do? -->

## Why

<!-- Motivation / the problem it solves. -->

## How tested

<!-- No automated tests here — describe the manual run and what you observed,
     e.g. `./bd-log -n 5` against this repo, before/after output. -->

## Checklist

- [ ] Ran the affected script(s) manually against a real beads project
- [ ] `python3 -m py_compile` passes on the files I changed
- [ ] Followed the conventions in [`CLAUDE.md`](../CLAUDE.md) (shebang,
      stdlib-only `bdutils`, argparse, `bdutils.error`/`warn`, `--version` via
      `add_version_arg`)
- [ ] Updated `README.md` / `CLAUDE.md` if behavior or flags changed
