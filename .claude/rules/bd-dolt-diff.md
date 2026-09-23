---
paths:
  - "bd-dolt-diff"
  - "tests/test_bd_dolt_diff.py"
---

# bd-dolt-diff design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bd-dolt-diff` — Previews what a `bd dolt push` would actually send: an
issue-level diff between the remote-tracking ref and the local branch
(added/removed issues, field-level before/after for changed ones, plus
dependency/label/comment changes). `--base`/`--head` diff any two Dolt
revisions. Dependency and comment rows are keyed on their semantic tuple,
not the surrogate `id` column (Dolt mints a fresh `uuid()` per insert, so
the same logical edge created on two clones would otherwise show as a
spurious add+remove). When a schema migration means the two revisions
don't share a column set, compares the intersection and names the skipped
columns (selecting a column absent from one side is a hard Dolt error).
Read-only; always exits 0 when the comparison ran — `bd-dolt-check`
remains the CI gate. Pages via `bdutils.paged_output()`; `--no-pager`
disables. Requires the `dolt` CLI.

## Manual checks

```bash
./bd-dolt-diff .                              # Preview what a push would send
./bd-dolt-diff . --base <branch-or-hash>      # Diff vs an arbitrary revision
```
