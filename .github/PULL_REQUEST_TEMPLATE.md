<!-- Thanks for contributing! Keep changes focused and dependency-light. -->

## What

<!-- What does this change do? -->

## Why

<!-- Motivation / the problem it solves. -->

## How tested

<!-- `make ci` runs the pytest suite, but it runs against fakes. Also describe
     a manual run against a real beads project and what you observed, e.g.
     `./bd-log -n 5` against this repo, before/after output. -->

## Checklist

- [ ] Ran the affected script(s) manually against a real beads project
- [ ] `make ci` passes (new behavior has a test; a fix has the test that
      would have caught it)
- [ ] Followed the conventions in [`CLAUDE.md`](../CLAUDE.md) (shebang,
      stdlib-only `bdutils`, argparse, `bdutils.error`/`warn`, `--version` via
      `add_version_arg`)
- [ ] Updated `README.md`, `CLAUDE.md` and the script's `.claude/rules/` file
      if behavior or flags changed, plus both `completions/` files for a flag
- [ ] Added a bullet under `## Unreleased` in `CHANGELOG.md`
