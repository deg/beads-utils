---
paths:
  - "claude-memory-check"
  - "tests/test_claude_memory_check.py"
---

# Claude Code memory tooling design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

Claude Code's auto-memory is a directory of markdown files per project
(`~/.claude/projects/<mangled-cwd>/memory/`), each carrying a frontmatter
`name:` slug, indexed by a `MEMORY.md` of one pointer line per file, and
cross-referenced as `[[name]]`. Nothing in Claude Code checks any of
that, and nothing versions it.

## claude-memory-check

`claude-memory-check` — Lints those directories; every project's by
default (read through `claudeutils.CLAUDE_PROJECTS`, the one binding the
session tools share, so the tests redirect it with the `claude_home`
fixture), or the ones named. It was `check-memory-links.py` in the owner's
dotfiles before it moved here (beads-utils-3bf.1), written after a link
to a memory that never existed sat in a store for months.

The one line it must hold is **ERROR versus pending**:

- **ERROR** (exit 1) is a link that was *meant* to resolve and does not:
  some spelling of it (hyphens for underscores or back) hits a real slug
  or filename stem. Also structural: a slug that is not kebab-case, two
  files claiming one slug, `MEMORY.md` naming a file that is gone or
  missing one that exists.
- **pending** (exit 0) is a link that matches nothing at all. The memory
  format says a `[[name]]` with no memory behind it "marks something
  worth writing later, not an error", so failing on it would make this a
  checker nobody runs twice. They are listed so they stay visible.

One deliberate difference from the dotfiles script: a named directory
that does not exist is an error, not a clean bill. The original globbed
whatever matched and printed "No broken memory links." for a typo'd path,
which is the silent success this tool exists to prevent.

Three more, from the fresh-eyes review at the port (beads-utils-3bf.1):
a store with no memory files still has its `MEMORY.md` checked, since
that is the state deleting the last memory leaves behind; only the
frontmatter's `name:` counts (a `name:` in the body is not the slug, and
quotes around the value are dropped); and when a link hits a *filename
stem* rather than a slug, the hint names the slug that file carries now,
not the link itself. Files are read as UTF-8 with replacement, so one bad
byte cannot turn the run into a traceback.

Known limitation, stated so nobody trusts it further than it goes: it
catches a link resolving to *nothing*; it cannot catch one resolving to
the *wrong* memory. That is what `/close-shop`'s reading subagent is for.

## Manual checks

```bash
./claude-memory-check                                  # Every store on this machine
./claude-memory-check ~/.claude/projects/<slug>/memory  # One store
```
