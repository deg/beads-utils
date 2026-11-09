---
paths:
  - "claude-memory-check"
  - "claude-memory-setup"
  - "hooks/commit-memories.sh"
  - "hooks/check-memories-pushed.sh"
  - "tests/test_claude_memory_check.py"
  - "tests/test_claude_memory_setup.py"
  - "tests/test_claude_memory_hooks.py"
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

## The memories repo, claude-memory-setup and the two hooks

The design (beads-utils-3bf.4, moved from the owner's dotfiles, where it
had run since 2026-10): a git repo whose `.git` is `~/claude-memories.git`
(`$CLAUDE_MEMORIES_GIT` overrides) and whose `core.worktree` is
`~/.claude/projects`. Every git command therefore needs only `--git-dir`,
and anything that touches the work tree must run from inside it. The
projects directory gains exactly one file, the allowlist `.gitignore`:
`*`, `!*/`, `!/*/memory/*.md`, `!/.gitignore`. Allowlist, because the
directory also holds every transcript, and a transcript holds everything
ever pasted into a session; a missed pattern can only hide a memory. Only
`*.md`, not the directory, so editor backups and `.DS_Store` stay out.

`claude-memory-setup` has two shapes. Fresh: `git init --bare
--initial-branch=main`, un-bare it with a work tree, write the allowlist,
commit it with whatever memories exist. `--remote`: bare clone, fetch
refspec and upstream set explicitly (a bare clone has neither, and both
hooks read `@{upstream}`), then a first checkout that writes out only the
files `ls-files --deleted` reports as missing, so a memory Claude Code
already wrote on the new machine is left alone. It refuses to run without
`jq`, which the hooks need. Four things review and tests caught:

- **The first checkout is keyed on the index not existing**, as the owner's
  original bootstrap had it, not on the git dir. A run that dies right
  after the clone leaves a git dir and no index; keyed on the dir, the rerun
  skips the checkout and the SessionEnd hook then sees every tracked memory
  as deleted, and with 20 or fewer would commit and push that.
- **HEAD is pinned to `main` before that checkout.** The clone's HEAD copies
  the remote's, and a bare remote made by `git init` points at `master`. An
  unborn HEAD makes `reset` empty the index, so nothing was checked out and
  nothing complained.
- **An empty remote gets the first commit pushed to it.** Warning and
  stopping left a repo whose hook committed with nowhere to push, and the
  hook's own fix (`branch -u origin/main`) failed, there being no
  `origin/main`.
- **On a clone the allowlist is written after the checkout**, so one the
  old machine customised wins over the default; only its pattern lines are
  compared, since a clone of an older allowlist has other comments.

Checkout paths run with `GIT_LITERAL_PATHSPECS=1`, so a name holding `*`
or `[` is not read as a pattern.

`commit-memories.sh` (SessionEnd) commits and, when there is an upstream,
pushes. It **fails closed**: one visible path that is not exactly
`<segment>/memory/<segment>.md`, or the `.gitignore` deleted, refuses the
whole commit; so does deleting more than `MAX_DELETES=20` memory files at
once (moving a whole store, 10 files, is the largest legitimate delete
seen). The memory-file test is an anchored regex, not a `case` pattern:
in a pattern `*` matches `/`, so `*/memory/*.md` accepted `a/b/memory/c.md`,
a hole the owner's original had too. A refusal is recorded in
`$GITDIR/last-refusal` and repeats at every session end until fixed; what is
already committed still pushes. `git status --porcelain -z -uall` is read
NUL-separated so a path with a space or non-ASCII character is not quoted
into failing the pattern, and a rename record's second (old-path) field is
read and dropped. The push is detached through `perl -e 'setsid(); exec'`
(macOS has no `setsid(1)`) because a SessionEnd hook gets only a moment, with
`ssh -o BatchMode=yes` so a key that wants a passphrase fails at once; its
output goes to `$GITDIR/last-push.log`. Exits 0 always: a hook failure must
never become a session-end error. `/close-shop` calls it with a commit
message so the audit's commit goes through the same guard.

`check-memories-pushed.sh` (SessionStart) is the backstop for all that
silence. Local state only, so free offline; it reports the first of: no
repo, a recorded refusal, a rejected push (read off `last-push.log`: the
hooks never fetch or merge, so two machines that commit before pulling
diverge, and waiting a day to say "not pushed" would hide the cause), no
upstream, commits unpushed for over a day (a younger one is not worth a
warning, since the next session end retries). Its hints carry
`-C <worktree>`, because `git --git-dir=X status` run elsewhere scans the
current directory instead. Output is a `systemMessage`, shown to the user,
not context for the agent.

Tests run the hooks as bash subprocesses against a store `claude-memory-setup`
built under `tmp_path` and a bare local remote, with `GIT_CONFIG_GLOBAL=/dev/null`
and author env vars set; they skip without `jq`. The push test polls the
remote rather than sleeping. Mutation-checked: the non-memory and nested-path
refusals, the deleted allowlist, the 20/21 boundary, the push, the cleared
refusal, the one-day age, the index-keyed checkout, the HEAD pin, the
allowlist comparison. Not covered: rename records in porcelain, which appear
only for a staged rename and the hook never stages one before reading status.

## Manual checks

```bash
./claude-memory-check                                  # Every store on this machine
./claude-memory-check ~/.claude/projects/<slug>/memory  # One store
./claude-memory-setup --remote <url> --git-dir /tmp/x.git --projects /tmp/x  # Clone path, harmlessly
bash hooks/check-memories-pushed.sh </dev/null          # Read-only against the live repo
make install-claude CLAUDE_HOME=/tmp/claude-home        # Links without touching ~/.claude
```
