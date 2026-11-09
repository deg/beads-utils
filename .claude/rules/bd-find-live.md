---
paths:
  - "bd-find-live"
  - "tests/test_bd_find_live.py"
---

# bd-find-live design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bd-find-live` — The open and in-progress beads minus the *parked* ones,
as a JSON array of `bd list --json` records. It exists for the
`/close-shop` skill's bead audit, which hands the listing to a reviewing
subagent (`--lean`, which swaps each `notes` log for `notes_len`) and
reports its size as the "open payload" (`| wc -c`). It was
`audited-beads.py` in the owner's dotfiles before it moved here
(beads-utils-3bf.1).

**Parked** means the bead's chain of blockers reaches a deferred bead.
That is the batch-gate convention: a group is parked by blocking each
member on a deferred gate bead, or on a parent that is, while the members
keep status `open`. `bd list --status=open,in_progress` filters on status
alone, so without this step every gated member is audited, and billed in
full, as if it were live work. A bead blocked on *live* work (an open or
in-progress blocker) is not parked: the walk follows blockers that are
themselves blocked and stops at one that is merely open.

Two things it does on purpose:

- **Names what it leaves out, on stderr.** The exclusion must never be
  silent; the skill passes that line to the subagent so the audit knows
  what it is not seeing.
- **Passes `--limit 0` to both `bd list` calls**, as `bd-log` and
  `bd-complete` do. `bd list --help` documents a default limit of 50, and
  the dotfiles script never passed one. Checked on 2026-11-07 against a
  repo with 184 live beads: bd 1.3.2's JSON output ignores the default, so
  nothing was ever truncated. The flag is there because an audit must see
  every bead, and the JSON exemption is not a documented promise.

The blocker edges come from `bd blocked --json` (`blocked_by`), delegated
rather than computed from `bd list`'s dependency fields for the reason
`bd-log`'s `blocked_ids` gives: bd owns which dependency types block.

## Manual checks

```bash
./bd-find-live .                              # Live beads of this repo, as JSON
./bd-find-live --lean . | head -20            # Without the notes logs
./bd-find-live . | wc -c                      # The open payload
```
