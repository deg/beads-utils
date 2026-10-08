---
paths:
  - "bd-verify-backup"
  - "tests/test_bd_verify_backup.py"
---

# bd-verify-backup design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bd-verify-backup` answers "if this machine died now, what would be lost?"
for one beads repo, or with `-g/--global` for every one on the machine
(`beads-utils-axs`). The design was agreed with the owner before code:

- **Every local branch counts, not just the current one.** A branch with no
  upstream, one whose upstream is `[gone]`, and one ahead of its upstream
  all fail, except that a `gone` branch whose every commit is on some
  remote branch (`git rev-list --count <b> --not --remotes` is 0, typically a
  merged PR's leftover) passes and is listed under `Cleanup:` in the detailed
  view only (`beads-utils-50m`, the owner's spec). "On some remote" rather
  than "merged into the default branch", since `origin/HEAD` is often unset.
  A squash- or rebase-merged branch still fails: its own commits are on no
  remote. So does a detached HEAD holding commits on no remote: no branch
  holds them, so the per-branch check alone would pass. Behind is fine: the
  remote has more, not less. A branch whose upstream is another *local*
  branch (`git branch -u main feature`, `%(upstream:remotename)` is `.`)
  counts as no upstream: tracking a local branch says nothing about any
  remote. Someone who tracks locally on purpose will see that branch fail
  every run; the owner chose that over a silent hole. Stashes fail too,
  since nothing pushes a stash. "Pushed" means pushed to the branch's own
  upstream, whatever host; every repo here is on GitHub anyway.
- **Uncommitted is `git status --porcelain`, untracked included, unfiltered.**
  bd 1.3.0's untracked `.beads.gate.lock` shows up in a few repos; that is
  `beads-utils-724`'s to deal with, not something to hide here.
- **The beads leg is bd-dolt-check's own computation**, lifted into
  `bdutils.dolt_sync_state()` / `DoltSyncState` so the two cannot disagree.
  bd-dolt-check renders it verbosely; this script renders one cell. The lift
  was checked by diffing the old and new bd-dolt-check's full output and
  exit code on all 19 repos: identical. Stricter than bd-dolt-check in two
  places, because a backup check cannot pass on what it did not see: a
  working set that could not be read, and `UNVERIFIABLE`, both fail here
  (bd-dolt-check exits 0 on them). `BEHIND` passes, for the reason above.
  A `.beads` with no Dolt database (a legacy sqlite/JSONL store, as
  `degel/fortune` was until its 2026-10-08 migration) fails as `no Dolt
  database`.
- **Never runs `bd`.** Opening a store with a newer bd migrates it on the
  spot (see the `bd-upgrade-playbook` memory), so a read-only sweep of 20
  repos must stick to git, dolt and file reads.
- **A beads dir that is not a git repo, or has no git remote, fails** with
  a single line: nothing in it has an off-machine copy.
- **Fetch first**, `git fetch --all --prune` plus bd-dolt-check's `dolt
  fetch`, because "ahead" against a stale ref is a guess; `--prune` is what
  makes a deleted upstream show as `gone`. `--no-fetch` opts out. A failed
  fetch is a note, not a failure: comparing against older refs can raise a
  false alarm, never a false all-clear. That holds for a failed `dolt fetch`
  too, which gets the same note. Network git calls get
  `GIT_TERMINAL_PROMPT=0` and `bdutils.GIT_NETWORK_TIMEOUT`, so one dead
  git remote cannot hang a `--global` run; `dolt fetch` has no such limit.
  `--no-fetch` skips the network entirely, including bd-dolt-check's `git
  ls-remote` presence check: the last-fetched Dolt tracking ref decides, and
  a repo that never had one fails as `UNVERIFIABLE`. A full `-g` with fetch took ~25 s for
  20 repos on 8 threads.
- **`git ls-remote` failing is `UNREACHABLE`, not `NOT FOUND`.** Before this
  script, bd-dolt-check read any ls-remote failure as "never pushed"; across
  20 parallel network calls that misreport would be routine.
- **Errors inside one repo are caught**, all of them. `bdutils.error()`
  raises `SystemExit`, and a non-UTF-8 `config.yaml` raises
  `UnicodeDecodeError`, which no helper catches; either, uncaught in a worker
  thread, comes back out of `pool.map` and ends the whole `--global` run with
  no table. `check_repo()` turns any exception into that repo's failure line.
  Fixes 1-4 of the post-ship cold review (detached HEAD, dolt fetch note,
  broad catch, and bd-dolt-check's sync.remote remedy) landed after
  `40c388a`.

## The --global inventory

Union of three sources, deduplicated by resolved path, keeping any directory
with `.beads/metadata.json`:

1. The `projects` keys of `~/.claude.json` (`claudeutils.claude_project_paths()`):
   literal absolute paths, unlike the sanitized names under `~/.claude/projects`.
2. A scan of `~/Documents/*/*/` (`SCAN_GLOBS`). Added after the first
   inventory missed `degel-ai-server`, which has beads but had never had a
   Claude session started in it.
3. `~/.emacs.d`, `~/bin`, `~/core-personal-files` (`EXTRA_REPOS`), the three
   the bd-upgrade inventory found outside `~/Documents`.

No exclusion list, by the owner's choice: a dead or legacy store fails every
run until its `.beads` goes or is migrated. `mirror/beads` drops out on its own,
since it has a `.beads` but no `metadata.json`.

## Tests

The git legs run against real throwaway repos with a bare local "remote"
(no network), with `GIT_CONFIG_GLOBAL=/dev/null` so the user's own git config
(signing, hooks) cannot decide the outcome. A remote-side branch deletion is
done in the bare repo itself: a local `git push --delete` would also drop the
remote-tracking ref, and the `gone` state would never arise.

## Manual checks

```bash
./bd-verify-backup                 # this repo, detailed
./bd-verify-backup -g              # every beads repo, one line each
./bd-verify-backup -g --no-fetch   # same, offline and fast
```
