---
paths:
  - "bd-dolt-check"
  - "tests/test_bd_dolt_check.py"
---

# bd-dolt-check design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bd-dolt-check` — Verifies that a beads repo's Dolt data (stored under
`refs/dolt/data` on the git remote, invisible in GitHub's UI) has actually been
pushed. Compares `.beads/push-state.json` against `git ls-remote` and the local
`.dolt/repo_state.json` / `dolt log`. Exits 1 on OUT OF SYNC so CI can gate on it.
It answers **committed *and* pushed**, on two independent axes. The commit
comparison above is one; the other is the Dolt **working set**, read from the
`dolt_status` system table. Without it a repo reads `IN SYNC` / exit 0 while
a whole table sits changed-but-uncommitted — in no commit, so no push can
carry it, and the commit comparison is blind to it by construction. That is
not hypothetical: it is `beads-utils-ksk`, found on `nutshell-mvp`, where
three weeks of `bd remember` memories lived only on one machine.
The section prints *before* anything touches the remote, because the working
set is purely local truth — a repo with no Dolt remote at all still needs to
hear it, and that path returns early. `clean` is printed out loud, as is
`not verifiable`; silence reading as "fine" is the failure this whole check
exists to end.
A dirty working set is its own status word, `UNCOMMITTED`, rather than being
folded into `OUT OF SYNC`: the two failures are independent and want
different remedies (commit vs. push), and they co-occur, in which case the
commit verdict keeps its own wording and picks up a `; N tables uncommitted`
clause. Exit 1 either way, including from the two "sync delta not
verifiable" returns — not knowing the commit delta says nothing about data
that is in no commit to begin with. That fold has to cover every one of
`main()`'s five returns; an "unverifiable *and* uncommitted" repo quietly
exiting 0 is precisely the bug.
Four things were checked rather than assumed, each of which would otherwise
invite defensive code:
- **`dolt_ignore` needs no filtering.** Every beads repo ignores
  `local_metadata`, `repo_mtimes`, `wisps`, `wisp_%` and
  `ignored_schema_migrations`. The `dolt_status` *system table* honors that
  list for untracked-new tables (an ignored new table simply does not
  appear) but not for a tracked table that later changes — which is exactly
  what `dolt status` itself does, so matching it is the right behavior, not
  a gap. No ignored table is dirty in any repo on this machine.
- **There is no "normal mid-session churn" to tolerate**, which is what the
  bead left open. bd's `batch` auto-commit policy *is* documented to
  accumulate changes in the working set by design — but `bd config get
  dolt.auto-commit` returns `on` for every repo here, and even under batch,
  uncommitted is still unpushed, which is the question this tool answers. So
  no `--strict`, no tolerance knob, and no new flag (which also keeps
  `completions/` out of it).
- **The cost of being right is small and known.** Across the 18 beads repos
  on this machine, all 13 embedded ones are clean and 3 of the 5 server-mode
  ones are dirty; two of those three have no Dolt remote and already exited
  1. This repo stays at 0, so `make dolt-check` here is unchanged.
- **Rows are reported raw.** No whitelist of dolt's status vocabulary
  (`modified`, `new table`, `deleted`, `renamed`, `conflict`, …) — same
  delegation principle as `bd-log`'s `--status` pass-through — and no
  filtering on `staged`, since a staged table is still uncommitted. Don't
  start reading `staged` without normalizing it: it comes back as int `0`/`1`
  from embedded repos and string `"0"`/`"1"` from server ones.
What it cannot say is *since when*. Uncommitted changes carry no date —
`dolt_status` has no time column, there is no `dolt_workspace_*` table, and
`dolt_diff_config` reports `to_commit='WORKING'` with a NULL date (see
`bd-log`'s memory-events notes, where the same wall was hit). The bead's
"uncommitted since 2026-07-12" was read off commit history, not the working
set.
The remedy is `bd dolt commit`, then push, in both modes — but the
section keeps a caveat in server mode, because **bd's own commit used to
silently do nothing there**, which was watched happening rather than
inferred. On `nutshell-mvp` (server mode, bd 1.1.0), `bd dolt commit`
printed `Committed.` and `bd vc commit` answered with a commit hash — the
*existing* HEAD's — while `config` stayed `modified` through both. The
changes were real (`dolt diff --stat`: 4 rows, four `kv.memory.*` values),
and the running server and the CLI agreed the table was dirty, so it was
bd's bug (upstream #4078; `beads-utils-fyn`, closed). A Dolt data dir can
serve several databases; `metadata.json` designates one, `locate_dolt_db()`
returns that one, and the working set asked about is that one's — following
bd's designation rather than surveying whatever else sits there.
At 1.1.0 the remedy was therefore mode-dependent, and both halves were run
in pristine repos of each mode: *embedded*, `bd dolt commit` cleared
`config`, `events` and `issues` together with `dolt.auto-commit off`;
*server*, it cleared nothing, and only **`bd dolt stop`** committed, on the
way down (`auto-flush: commit working set before server stop`). Server mode
then also left `config` dirty from `bd init` onwards and ignored
`dolt.auto-commit off`.
**bd 1.3.0 fixed all of that**, and it was re-verified on 2026-09-23 rather
than taken from the changelog: in a throwaway server-mode repo with
`dolt.auto-commit off`, `bd create` + `bd remember` left `config` and
`issues` modified (so `off` is honored now), one `bd dolt commit` cleared
both and put the `kv.memory.*` rows in HEAD, and a second `bd dolt commit`
answered `Nothing to commit`. So both modes now print the same first line.
Server mode adds a parenthetical for older binaries — `bd dolt stop`, or the
dolt-native one-liner below — since the tool cannot know which bd the reader
runs, and no server-mode repo remains on this machine to catch a regression.
Two consequences of that, both of which a cold-eyes review caught after the
first cut shipped with them wrong:
- **Every closing action line has to be reachable.** Each one names a state
  the command cannot get to on its own while tables sit uncommitted — a push
  does not carry them, and a pull onto a dirty working set can conflict
  rather than merely be incomplete — so `commit_first()` prefixes all four
  with "Commit the working set first (above)". It points *back at the
  section* rather than naming a command, because at 1.1.0 which command
  committed depended on the mode; spelling `bd dolt commit` there
  contradicted the server-mode remedy printed ten lines above it, which is
  the loop this bead exists to break. The section still carries the
  older-binary caveat, so the pointer stays. The suite could not see that: `conftest.py`'s `project`
  fixture hardcodes `dolt_mode: embedded`, so until `server_dolt_project`
  landed, no `main()` test ran in server mode at all.
- **`IN SYNC` is never claimed on an axis that wasn't checked.** When the
  `dolt_status` query itself fails the verdict reads `IN SYNC (commits) —
  working set not verifiable`. Exit stays 0, since nothing is known to be
  wrong; but a flat all-clear would be the same silence-reads-as-fine
  failure the whole check exists to end.
The section also prints, in server mode, a `dolt sql` one-liner that
commits exactly the tables it just listed — the one remedy independent of
bd's version, and the only one when a server isn't running (`bd dolt stop`
has nothing to flush: `Error: dolt server is not running`). Its path is `shlex.quote`d and its database name backticked:
the line is printed to be pasted verbatim, and both come from outside
(the filesystem and `metadata.json`). It is rooted at the database dir's **parent**, the
one spelling that works in both layouts: in server mode that is the
sql-server's data dir, where the CLI finds `.dolt/sql-server.info` and
proxies to the running server instead of writing the files out from under
it; in embedded mode it is just a directory holding one database. Both were
run. `call dolt_add(...)` takes the whole table list in one call (checked;
it commits every one), with the caveat that a table matching `dolt_ignore`
is skipped by `dolt_add` even when `dolt_status` lists it as modified — the
tracked-and-ignored case above, which nothing on this machine is in.

## Manual checks

```bash
./bd-dolt-check .                             # Check Dolt sync state
```

`make dolt-check` runs the same thing.
