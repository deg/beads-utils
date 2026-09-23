---
paths:
  - "bd-log"
  - "tests/test_bd_log.py"
---

# bd-log design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bd-log` — Shows recent lifecycle events in a git-log-style timeline,
newest first, for two kinds of thing at once. Events form a 2×3 grid —
`--only` picks the verb, `--about` picks the entity, both defaulting to
everything:

|          | create     | change   | end       |
|----------|------------|----------|-----------|
| beads    | created    | started  | closed    |
| memories | remembered | revised  | forgotten |

The bead row wraps `bd list ... --json` and synthesizes one event per
non-empty `created_at`/`started_at`/`closed_at` timestamp on each issue.
The memory row is reconstructed from Dolt commit history — see
"Memory events" below, which is a whole subsection because nothing about
it is guessable from bd's CLI.
`--only=VERBS` takes `create,change,end`; `start` and `close` remain
accepted as the change and end verbs, because they are what `--only` took
before memories joined the grid and they appear throughout this file, the
epilog, and both completion files. `--about=ENTITIES` takes
`beads,memories` (singulars accepted). Verbs and entities multiply:
`--about=memories --only=end` is exactly the forgotten memories.
The color axis is the *verb*, not the kind, which is what keeps the palette
at three hues (below); the entity rides on the glyph (`+ ▶ ✓` / `* ~ x`)
and is spelled out in the meta cell, which reads `memory` where a bead
reads `P3 task`.
Orthogonal to both axes, `--status=LIST` and `--id=LIST` scope
which *beads* to include. `--status` (comma-separated statuses, passed
straight through to `bd list --status`; bd owns the vocabulary and
validation — except *emptiness*, rejected here by name, because a
`--status=` from an unset shell variable would otherwise fall through to
`--all` **and** drop out of the filters implying `--about=beads`, quietly
returning every bead plus the whole memory log) selects by *current*
status; `--open` is shorthand for
"not closed" (mutually exclusive with `--status`); with neither flag the
default is `bd list --all` (everything, incl. closed). `--id`
(comma-separated **full** bead ids, delegated to `bd list --id`, so bd owns
the id vocabulary — short suffixes like `y13` match nothing, and
`bd-complete` emits full ids for exactly that reason) composes with either.
Every one of them narrows the beads row; which of them additionally implies
"…and *only* the beads row" turns on whether bd-log knows what the filter
means. `--id`/`--children` do imply it: they *enumerate* what to log, and a
memory is never one of the ids typed, so including them would bury the
answer — two bead events under nineteen memory rows, on a project with a few
years of `bd remember` behind it. `--status` implies it too, for the
opposite reason: it is an uninterpreted pass-through, bd owns that
vocabulary *and* has a `custom_statuses` table, so bd-log cannot tell a
live-ish list from a done-ish one and must not guess. It guessed once — an
earlier cut let `--status` inherit `--open`'s behavior, which made
`--status=closed` return the whole memory log, six-eighths identical to
`--status=open` at `-n 8`.
`--open` alone does **not** imply it, because it is the one predicate
bd-log defines itself: bd's default scope, i.e. not closed, i.e. still in
force — a meaning that carries across entities, since every memory that
hasn't been forgotten is in force too. Note this only works because `--open`
is *not* a synonym for `--status=open`: it passes no status flag at all, so
it also covers `in_progress`/`blocked`/`deferred`. Mistaking the two for one
filter is what produced the `--status=closed` defect above.
`--no-deferred` drops beads whose *current* status is `deferred`, and
composes with any scope (`--open --no-deferred` is what's live and not
parked; alone it is everything-but-parked). It is a local post-filter,
not a `bd list` flag: bd has no negated status filter, and translating it
to `--status=open,in_progress,blocked` would hard-code the rest of bd's
vocabulary, which is exactly what the `--status` pass-through refuses to
do. Naming `deferred` alone is not that guess — it is the one status `bd
defer` itself sets (verified across every beads repo on this machine:
all ten beads with a `defer_until` also carry `status: deferred`). Since
bd 1.2.1 an expired `defer_until` *does* un-park a bead, but lazily:
`bd ready` (and `bd ready --claim`, `bd list --ready`) first sweeps every
deferred bead whose date has passed to `status: open`, clearing
`defer_until` and recording a `status_changed` event by `bd-defer-wake`.
Plain `bd list` does not sweep (checked on 1.3.0), so until something runs
`bd ready`, bd-log still sees such a bead as `deferred` and
`--no-deferred` drops it. That is bd's stored answer, which is the one
bd-log reports. The filter runs *after* the `--children` walk, because with
the default scope the fetched list doubles as the topology, and dropping
a deferred epic before the walk would sever the chain to its live
children. Like `--open`, it does not imply `--about=beads`: a memory is
never deferred, so it refines "in force" rather than picking an entity.
`--no-blocked` drops beads that `bd blocked` reports as waiting on an
unsatisfied dependency. It is a *different axis* from `--no-deferred`,
not a stronger version of it: a bead is blocked by what it depends on and
deferred by its own status, and it can be both — a deferred bead still
appears in `bd blocked` when something it needs is open, so the two
filters overlap without either subsuming the other. The set is fetched
from `bd blocked --json`, lazily, only when the flag is passed (~0.3s).
It is delegated rather than computed for the same reason `--status` is a
pass-through: bd owns the dependency semantics. Computing it locally is
not merely more work, it is a guess — the `dependencies` array in `bd
list --json` would require bd-log to decide which edge `type` values
block (`parent-child` does, `related` does not, `discovered-from`
presumably does not), and the *stored* status is no help either, because
a blocked bead's status stays `open` until someone runs `bd
recompute-blocked` (every one of `mbz-et8e.56`–`.59` is `status: open`
while `bd blocked` lists it, and this repo has zero stored `blocked`
statuses across 58 beads). Two properties of the returned set matter:
closed beads are never in it, so the filter cannot drop a closed bead's
events; and it is not capped the way `bd list` is at 50 (a 61-bead test
returned all 61). Like `--no-deferred` it runs *after* the `--children`
walk, and like `--open` it does not imply `--about=beads` — a memory is
never blocked.
The obvious alternative, `bd list --ready`, was tried and rejected. It
looks ideal (bd's own definition, no guess at all) but means open **and**
unblocked **and** not deferred, so an `in_progress` bead is not ready:
setting one bead to `in_progress` and changing nothing else took the
ready set from one bead to zero. `bd-log --open --no-ready` would
therefore hide the bead being actively worked on, which is the one most
likely to have recent events. It also cannot compose with the scope axis
— `bd list --ready --all` returns the ready set, silently overriding
`--all`.
Known gap (`beads-utils-x9x`): a child of a *deferred parent* is excluded
from `bd list --ready` but is **not** in `bd blocked`, so `--no-blocked`
leaves it. That is not the case this flag was built for — the reported
one was a gate bead (`mbz-et8e.60`, `[gate] Resume marketing-site work
(close to activate)`, deferred) with an explicit `blocks` edge from each
child, which `bd blocked` reports. Because of that gap, the three filters
together are the narrowest live view *these* flags give, and not "what can
actually be picked up" — the phrasing an earlier draft used in the epilog,
the changelog and this file, contradicting the paragraph you are reading.
These are soft defaults an explicit
`--about` overrides, in which case an inert bead filter is named on stderr
rather than silently ignored.
`--children` widens each `--id` to its whole subtree, at any depth; it is
the one filter that can't delegate (bd's `--id` doesn't expand children and
`--parent` walks one level per call), so it matches locally: the transitive
closure over the `parent` field, walked over the whole `bd list --all` set
and only then intersected with the scoped one. Walking the scoped set instead
would let `--open`/`--status` hide an intermediate bead and silently sever
the chain to everything below it, so `--children` costs a second `bd list
--all` whenever a scope filter is in play (with the default scope, that
*is* the fetch already made). Nothing matches on id *text*: a dotted id
like `proj-a1b.4` looks like it encodes parentage, but `bd update --parent`
reparents without renumbering, so a moved bead keeps an id naming its
former parent. A requested id that ends up with
no events warns on stderr (neutrally: a bead can be absent because it
doesn't exist *or* because a filter excluded it) without changing the exit
code. The warning names only the filters actually passed — listing every
filter that *could* explain the absence sends the reader hunting for a
`--since` they never typed — so with no other flags it reads just
`(not found)`. The check runs before `-n` trims, so a truncated list never
false-alarms. Also `-n/--limit`
(default 0 = unlimited, like `git log`) and `--since DATE`
(timestamp filter applied to every event kind). Pages through
`bdutils.paged_output()` (`$PAGER` or `less -FRX` when stdout is a tty).
`--no-pager` disables. Events are colored by **verb** via
`--color=auto|always|never` (`bdutils.want_color`), traffic-light style:
red on `end`, where work *stops* (a bead closed, a memory forgotten);
green on `change`, where it goes (a play button is green); blue on
`create`, which is neither. The obvious
alternative maps the lifecycle *sequence* onto the light (create green →
change yellow → end red) and is rejected on legibility: in Solarized
Light — and low-contrast light themes generally — ANSI green and yellow
are both olive (`#859900` vs `#b58900`), so it would put two
near-indistinguishable colors on adjacent event kinds. Blue/green/red are
the three most separated hues on offer — which is also why the entity is
*not* a color axis. A fourth hue would have to come from the same plain
30–37 range, whose remaining candidates are exactly the yellow just
rejected and a cyan that sits next to blue; keying color on the verb
instead lets both rows of the grid share three well-separated hues, and
keeps "one color axis" true.
A **symbol key** prints below the log, laid out as the same 2×3 grid the
flags select and with each cell tinted like the rows it explains — so it is
a color key too, showing the hues rather than naming them (a legend reading
"green = change" tells you what the color is called, not what it looks like
in your theme). `--legend=auto|always|never`, mirroring `--color`'s
spelling; `auto` means a tty, so pipes and `grep` stay clean. It resolves
from `sys.stdout` before `paged_output()` is entered, for the same reason
color does. Its column widths come from `len()`, so the two wide glyphs can
narrow a column by a character in terminals that draw them double-width —
the `beads-utils-fh0` bug, inherited.
The **whole entry** is tinted, not just the leading glyph+timestamp. That
stamp is ~18 characters of an ~80-character entry, and at that size the
eye can't judge a hue at all — every candidate palette read alike until
the colored area grew. The verb stays the sole color axis (nothing
encodes priority, type, or entity), so a long run of one hue is still one
signal. Because
`paged_output()` yields the *pager's stdin pipe*, the color decision is
resolved from `sys.stdout` before that context manager is entered —
testing the yielded stream would report "not a tty" in precisely the case
(a user at a terminal) where color is wanted.
`--oneline` collapses each event to one row —
`glyph ts  id  P3 task  title` — dropping the actor (near-constant in a
single-owner project) and the close reason (a full paragraph in practice;
shedding it *is* the point of the flag). Purely a render mode: the filter
axes above are untouched. Deliberately **no header row**, unlike
`claude-session-list --oneline`: this is a git-log-style view whose columns
are self-describing where that script's (`8f3a2b1c`, `3h ago`, `12p/47r`)
are not, every row is tinted by verb so a header would sit uncolored atop a
colored table, and the output gets grepped. Titles are not truncated to
terminal width — git doesn't, and it keeps pipes honest. A memory's value
*is* truncated, to 100 chars like `bd-dolt-diff`, in both forms: it runs to
well over a thousand characters, and shedding that is the point. A memory
*key* is truncated only in `--oneline` (to 24), because that is the form
where the widest cell pads every other row — keys run to ~50 against a bead
id's ~17, and uncapped they padded this repo's own 15-character ids out to
32, which is `beads-utils-u20`'s failure mode arriving somewhere new. 24 was
picked off the rendered output rather than reasoned about: it is where keys
stay recognizable while the dead space on bead rows drops to a few
characters. The block form caps nothing, having no column to protect. The id and
priority/type columns auto-size over the rows actually rendered, i.e.
*after* `-n` trims, so a long id that got cut off doesn't pad what survived.
One caveat inherited from the color work above: a row is ~70 colored
characters against a block entry's ~160–240. That is still well clear of the
~18 characters at which hues stopped separating in Solarized Light, but it
is a 2–3× cut in the one dimension that has regressed before, so a palette
change should be re-checked at one-line width too.
`--count-events`, `--count-beads` and `--count-memories` each add one
plain line after the log (`12 events` / `7 beads` / `3 memories`), before
the legend, uncolored like the pending-group header because color means
a verb. They count what is on the screen: the event list *after* every
filter and after `-n` trims, so a bead with created/started/closed
entries is one bead, and an uncommitted memory change is one event even
though `-n` skips it. An event is an entry, not a physical line. Zero is
an answer, so the `no matching events` case still prints them; under
`--about=memories`, `--count-beads` says `0 beads` rather than warning.
A trailer, never a replacement for the log -- `grep -c` semantics were
considered and rejected, since the flags are for reading a log and
knowing its size at the same time.

**Memory events.** `bd remember` records **no timestamps**: a memory is a
`kv.memory.<key>` → value row in Dolt's `config` table, key and value and
nothing else, and bd's own `events` audit table holds only issue lifecycle
rows. So "when did this memory appear or change" is answerable from exactly
one place — Dolt's commit history, via the `dolt_diff_config` system table,
whose `added`/`modified`/`removed` rows carry `to_commit_date` plus both
sides of the value. Consequences worth knowing before touching this code,
each verified rather than assumed:
- **`dolt` becomes a soft dependency**, where `bd-log` previously needed
  only `bd`. A repo with no Dolt database (JSONL-only `no-db` mode), or a
  machine without the CLI, simply has no memory row. `memory_events()`
  returns `None` for "couldn't look" and `[]` for "looked, found nothing" —
  and only `--about` naming memories turns the former into a warning, since
  otherwise every run in such a repo would carry one.
- **Uncommitted changes have no date, and none can be derived.** A memory
  written while Dolt auto-commit is off sits in the working set, where
  `dolt_diff_config` reports `to_commit='WORKING'` and a NULL date. Not
  hypothetical — 6 of 13 memory changes in `nutshell-mvp` are working-set,
  and `config` is the *only* modified table there, so bd commits the issue
  tables constantly and this one never. Nothing else dates them:
  `dolt_status` has no time column, there is no `dolt_workspace_*` table,
  and `from_commit_date` dates HEAD rather than the edit. They therefore
  print as a labelled group (`uncommitted -- no date until committed`)
  ahead of the dated log, each row stamped `(uncommitted)` where the
  timestamp would go, and **`-n` does not count them against its budget** —
  `-n` asks how far back through the *history* to go, and a pending change
  isn't in it yet, exactly as `git log -n 4` ignores your working tree.
  Without that, a `bd-log --open -n 4` on `nutshell-mvp` answered with four
  pending memories and no beads at all.
  Resist the temptation to merge them into the timeline as "newest". They
  lead because the working set is a *descendant* of HEAD — a DAG fact, not
  a wall-clock one. On `nutshell-mvp` HEAD is minutes old while the newest
  *committed* memory change is three weeks back, so those edits sit
  somewhere in a three-week window that nothing can narrow.
  The empty timestamp needs a high sentinel in the sort key, because `''`
  sorts lowest and a reversed sort would otherwise sink them to the bottom.
- **`--since` is applied in Python, never pushed into SQL.** A
  `to_commit_date >= …` clause would drop every NULL-date row silently, i.e.
  exactly the newest events. `filter_since` keeps undated events
  unconditionally for the same reason.
- **Timestamps need normalizing.** Dolt returns UTC, space-separated, with
  microseconds (`2026-08-02 19:55:33.460000`); bd returns
  `2026-07-28T07:44:53Z`. The merged timeline sorts as plain strings and
  `--since` compares a bare `YYYY-MM-DD` as a prefix, so both spellings
  must be one spelling.
- **Merge commits can double-report** one logical change, so rows are taken
  once per `(key, to_commit)`. This repo has no merges; a repo that pulls
  does.
- **No actor.** Dolt's committer is `root`, and the real name appears only
  inside the commit *message* text (`bd: remember (auto-commit) by …`),
  which is too fragile to parse. `render` already omits an empty actor.
- `bdutils.read_metadata()` **exits the process** when `metadata.json` is
  missing — right for the dolt scripts, wrong here, since `bd-log` still has
  bead events to print. The file is checked before it is read.
Cost is not a reason to make this opt-in: the query runs in ~0.25s against a
3671-commit repo.
Not covered, and filed separately: `--only=change` shows memory revisions
but no bead *updates*, because `bd-log` doesn't read the `events` table —
where bd does record `updated` (and `reopened`, and an actor per row).

Since bd 1.3.0, `bd config list` no longer lists `kv.*` rows and `bd config
get kv.memory.<key>` returns empty, so neither can count or read memories
ad hoc; use `bd memories`. The `dolt_diff_config` query above reads the
table directly and is unaffected.

## Load-bearing tests

The `select_subtrees` tests in `tests/test_bd_log.py::TestSelectSubtreesBranches`
are load-bearing in a way the rest are not: they cover four `--children`
behaviors this repo's own bead data cannot reach (a scope filter severing the
chain to a deeper descendant, an all-non-dotted chain, a reparented bead that
must not appear under its former parent, a parent cycle). Two of the four
correspond to defects found only by an ad-hoc version of that check. Each was
verified by mutation — walking the scoped set instead of the topology, dropping
the cycle guard, or inferring parentage from dotted id text each breaks them.
The same three-level shape (open root, filtered middle, open leaf) is what
makes any "this filter runs *after* the walk" test discriminating — the
`--no-deferred` e2e test uses it. A two-level fixture with the filtered bead
as the *root* is inert: the walk seeds the named root unconditionally, so
both orderings keep the child, and a cold-eyes review found exactly that
fixture passing with the filter moved to the wrong side.

## Manual checks

Run against this repo, which is itself a beads project:

```bash
./bd-log                                       # All events, beads and memories
./bd-log --about=memories                      # Memory history alone
./bd-log --about=memories --only=end           # Memories that were forgotten
./bd-log --about=beads                         # Beads only (the pre-grid view)
./bd-log --only=create                         # Beads created + memories added
./bd-log --open                                # Events for beads still open
./bd-log --open --no-deferred                  # ...minus the currently deferred ones
./bd-log --open --no-blocked                   # ...minus the ones waiting on a blocker
./bd-log --open --no-deferred --no-blocked     # ...minus both
./bd-log --only=start --status=in_progress     # What's actively being worked
./bd-log --id beads-utils-s4s                  # One bead's whole history
./bd-log --id beads-utils-v9o --children       # That bead and its whole subtree
./bd-log -n 25 --since 2026-04-01              # 25 events on/after date
./bd-log --color=always | cat                  # Keep color through a pipe
./bd-log --color=never                         # Force plain (also: NO_COLOR=1)
./bd-log --oneline                             # One row per event
./bd-log --oneline -n 20                       # ...and columns sized to those 20
./bd-log --legend=always | cat                 # Keep the symbol key through a pipe
./bd-log --legend=never                        # Suppress it at a terminal
./bd-log --open --count-beads                  # ...and how many beads that is
./bd-log --count-events --count-memories       # One line per count, after the log
```
