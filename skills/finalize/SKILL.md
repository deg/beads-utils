---
name: finalize
description: Finalize work on one bead — self-review, refactor, add tests, run lint and tests until clean, get a senior review, then commit with the user's approval and close the bead. Use for /finalize, or when the user says a task's work is done. Runs once per bead; /close-shop closes the session.
---

# Finalize work on an issue

Perform the following steps **in order**. Do not skip steps.

## 1. Self-Review

Before changing anything, review your own work with a critical eye:

- Run `git diff` to see all changes made this session
- Check for **wrong-approach errors**: did you pick a strategy that's more complex than needed? Is there a simpler, more standard way to achieve the same thing?
- Check for **misread-code errors**: did you assume something about the existing codebase that isn't true? Verify key assumptions by re-reading the relevant code.
- Check for **logic inversions**: RTL/LTR swaps, off-by-one errors, flipped conditionals, wrong operator
- Check for **regressions**: did you break something that was working before?

If you find problems, fix them now before proceeding. Do not mention the self-review to the user unless you found and fixed something — then briefly note what you caught.

Then call `advisor()` for a transcript-aware second opinion — it sees your full session reasoning, so it catches wrong-approach and misread-code errors early, while changes are still small and cheap to undo. Surface any real findings to the user and fix what you both agree on before proceeding. (If no `advisor` tool is available in the session, say so once and go on.)

## 2. Refactor Session Code
- Review all code changes made in the current session
- Eliminate code duplication (DRY principle)
- Ensure callers appear before callees in each file (top-down organization)
- Fill in missing docstrings/comments -- focus on **"why"**, not "what"; audience is senior devs
- Ensure consistent patterns with the existing codebase
- **Do NOT make functional changes** -- refactoring only

## 3. Add Tests
- Add new tests covering the new code where appropriate
- Test docstrings must explain: why the test matters, what bug it prevents, what it covers
- Tests go in files mirroring source structure

## 4. User- and Project-Specific Steps
Extensions are read from two places, user first, then project, and both are followed:
- `~/.claude/skill-extensions/finalize.md` — the user's own conventions, the same in every project.
- `.claude/skill-extensions/finalize.md` in the project — that project's: API type regeneration, doc updates, and the like.

If neither exists, skip this step.

## 5. Run Linting
- Run `make lint` from the project root
- Fix ALL linting errors and warnings
- Minimize suppressing comments -- rewrite code to pass checks instead
- Ensure consistent formatting

## 6. Run Tests
- Run `make test` from the project root
- Fix any failing tests
- Ensure critical paths and new code are covered by tests

## 7. Iterate Until Stable
- If linting or tests fail, fix the issues and repeat steps 5-6
- Continue until both `make lint` and `make test` pass cleanly
- Only proceed when both commands succeed with zero errors

## 8. Senior Review

With the change complete, lint-clean, and tests passing, get a senior review **before** committing:

- Call `advisor()` on the finished change. It is transcript-aware: it knows your intent and what you tried, so it judges whether the whole change is sound.
- **Scale by change size.** For a non-trivial diff, *also* spawn one fresh subagent (`Explore` or `general-purpose`) given only the diff and a one-line scope. Because it has none of your reasoning, it reads the code cold — an independent fresh-eyes pass that isn't anchored to how you narrated your own work. For a trivial diff, `advisor()` alone is enough.
- **Surface every finding to the user**, each with your proposed response (fix / won't-fix / not-a-bug). The user decides what to act on — do not silently apply or dismiss findings.
- If the user opts to fix something, make the fix and re-run steps 5–6 (lint and test) before continuing. Only proceed to close once gates pass again.

## 9. Close Issue

**Close the bead last — after the commit is approved, not before.** The neighbour check
below can change what the commit message should say, and a commit the user declines or
sends back for a fix must not leave a closed bead behind it.

- **Check which *other* beads this work changed.** Closing your own bead is the easy
  half; the beads that quietly became done — or half-done — are the ones nobody looks at
  again. Cast a narrow net, scoped to this change: this is a task close, not the
  session-wide sweep `/close-shop` runs.
  - `bd show <id>` for what this bead hangs off, and `bd list --parent=<parent>` for its
    siblings if it has a parent.
  - `bd search <keyword>` on the files, subsystem, or symptom you just touched. An older
    bead filed against the same bug from a different angle is exactly what this catches and
    nothing else does.
  Then, per hit, one of:
  - **Now also done** — your change satisfies it. State the evidence and **ask before
    closing**; do not close someone else's bead on your own reading of the diff.
  - **Partially done** — `bd update <id> --append-notes=...` with what your change already
    covers and what is left, so the next agent does not redo the covered half.
  - **Now wrong** — its description assumes something your change made untrue. Correct the
    description.
  - **Superseded** — `bd supersede <old> --with=<new>`, not a silent close.

  A bead that is merely blocked or no longer wanted is **not** done: that is `/defer`'s job,
  and closing to park destroys discoverability.
- Create a git commit message with the bead ID parenthesized at the end of the first line, e.g.: `Add report lineage fields (proj-d3j.2)`
- Check the bead's notes for design decisions and context that should inform the commit message
- Ask the user for approval, then run `git commit`
- Only now, `bd close <id> --suggest-next`. What `--suggest-next` prints is work that just
  became *startable* — next-work, not beads to re-verdict against the bullet above.
- **DO NOT run `bd sync` or `git push`**
- **Then ask the user: was that the session's last bead?** If it was, `/close-shop` is next.
  You cannot know the answer — the session may well continue — so ask rather than guess, and
  ask rather than stay silent: `/close-shop` is the only thing that ever re-reads the
  standing memories and the still-open beads, and it only helps if it gets typed.
- Work on this bead is complete from the agent's perspective. Stop here.
