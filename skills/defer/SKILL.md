---
name: defer
description: Defer (park) a bead — set it aside without closing it. TRIGGER whenever the user asks to defer, park, shelve, postpone, snooze, sideline, punt, set aside, or push off a bead/issue/task, or says "not now" / "later" / "revisit after X". NEVER `bd close` to park — closing destroys discoverability.
---

# Defer (park) a bead

Set a bead aside so it leaves `bd ready` but stays discoverable, recording **why** and (optionally) **when to revisit**. This is the standard "parking" mechanism.

**MANDATORY: Deferring is the ONLY park mechanism. NEVER use `bd close` to park a task** — closing is destructive to discoverability and hides priority. Only close if the user *explicitly* asks to close (not "park", "shelve", "set aside", or "defer"). When in doubt, defer.

## 1. Identify the bead

- The argument may be a bead ID, optionally followed by free-text context (a reason, a date). Parse what you can from it.
- If no bead ID is given, ask which bead to defer.
- Run `bd show <id>` to load its current state. If it is already closed, confirm the user wants it reopened-and-deferred before proceeding.

## 2. Gather the two inputs (DISCUSS ONLY — no writes yet)

- **Reason** — why set it aside *now*, and the concrete trigger/condition that would justify reviving it. Write it **self-contained**: it must make sense months later, read cold, without this conversation. This becomes the `defer_reason` metadata field. Keep it to one or two sentences: the gate for revisiting, not the plan for what to do then — that belongs in the bead's body.
- **Wake date** — either a specific calendar date, or none:
  - If the trigger is a point in time ("next quarter", "after the credit review"), convert it to a concrete `YYYY-MM-DD` for `--until`.
  - If the trigger is an *evidence condition* with no timeline ("if profiling shows X"), use **no date** — capture the condition in the reason instead.

## 3. Confirm before writing

- Show the proposed `defer_reason` wording and the wake date (or "no date").
- Wait for explicit go. Do not write until the user approves.

## 4. Apply (only after go)

- `bd defer <id> [--until=YYYY-MM-DD]`
- `bd update <id> --set-metadata defer_reason="<the approved reason>"`
- **Single source of truth:** the reason lives ONLY in `defer_reason` metadata. Do **not** also pass `--reason` / append it to notes — that duplicates it and drifts.

## 5. Verify + user- and project-specific steps

- Extensions are read from two places, user first, then project, and both are followed: `~/.claude/skill-extensions/defer.md`, then `.claude/skill-extensions/defer.md` in the project.
- Otherwise, verify with `bd show <id>`: status should be `deferred`, and the `METADATA` section should show `defer_reason`.
