---
paths:
  - "bd-view"
  - "tests/test_bd_view.py"
---

# bd-view design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bd-view` — Pretty-prints a single bead with rendered Markdown. Where `bd
show` dumps fields as plain text and `bd edit` shows raw markdown one
section at a time, this renders the full bead (header metadata,
description, design, notes, acceptance criteria, metadata, dependencies,
comments) with proper formatting via the `rich` library. Subclasses
`rich.markdown.Markdown` to disable raw HTML so placeholder text like
`<id>` survives. Single positional arg: `bd-view <issue-id>`.
Field coverage is meant to be a superset of `bd show`'s, and is
self-defending: `RENDERED_KEYS` lists every top-level JSON key some
renderer accounts for, and whatever is left (minus the redundant
`dependency_count`/`dependent_count`/`comment_count`) lands in a trailing
`Other Fields` section — so a column `bd` adds later shows up unprompted
instead of vanishing. This mirrors `bd show --long`'s own
`EXTENDED DETAILS` section. Dependencies are grouped by the
`dependency_type` that `bd dep list --json` returns (`Parent:`,
`Children:`, `Depends on:`, `Blocks:`, plus the rarer `tracks` /
`discovered-from` / `supersedes` / … kinds); unknown types render under
their raw name rather than being folded into depends-on/blocks. If a bead
has a `parent` but no parent-child edge comes back, the bare id is shown.
Pages via `bdutils.paged_output()`; `--no-pager` disables. Falls back to a
plain-text dump (with a `warning:`) if `rich` isn't installed — the
fallback renders the same field set.
Shebang is `#!/usr/bin/env -S uv run --script` with PEP 723 inline
metadata declaring `rich` + `markdown-it-py`, so deps come from `uv`'s
per-script cached venv — nothing is added to any global Python env.
Requires `uv` on `PATH`.

## Manual checks

```bash
./bd-view beads-utils-s4s                      # Pretty-print a single bead
```
