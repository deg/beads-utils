---
name: changelog
description: Generate a changelog entry for recent work and write it into CHANGELOG.md, matching the file's existing style, one terse user-facing line per change. Use for /changelog, or when the user asks to write up what changed since the last release or tag. Leaves the entry unstaged for review and never commits.
---

# Generate changelog entry

Generate a changelog entry for recent work and write it into CHANGELOG.md. Leave it unstaged for the user to review; never commit.

## 1. Determine the change range

- If the user specified a range (e.g., a tag, commit, or date), use that.
- Otherwise, auto-detect: find the most recent git tag with `git describe --tags --abbrev=0`.
- If no tags exist, use the first commit on the current branch diverging from main.
- Show the user what range you're using before proceeding.

## 2. Gather changes

- Run `git log <start>..HEAD --oneline` to list all commits in range.
- Also run `git diff --stat <start>..HEAD` to understand scope.
- Read the existing CHANGELOG.md (if one exists) to match its format and style.

## 3. Draft the entry

Categorize commits and draft the entry following the conventions below. Apply editorial judgment:

- **Collapse** related commits into a single line (e.g., "add feature X" + "fix feature X typo" = one entry).
- **Omit** commits that are not user-visible or architecturally significant (see "What NOT to Include").
- **Order** entries by significance within each category.
- If CHANGELOG.md already exists, match its heading format and style exactly — including its category names, if it has its own.
- If no CHANGELOG.md exists, use format: `## vX.Y.Z (DDMonYY)` with bullet points.

## 4. Write the entry

- Write the new entry directly into CHANGELOG.md, inserting it above the most recent version block (or at the top if no CHANGELOG.md exists yet).
- Tell the user it has been written and where, so they can review and amend it in the file.
- Do NOT `git add` or commit — leave the change unstaged until the user approves.

---

## Changelog Conventions

### Categories

The test is whether a **user could notice** the change. A user is anyone using the product from
outside the code: every page of the app (admin pages included), reports, emails and exports,
and the API. Logs, tests, scripts and the codebase itself are internal. Apply these in order:

1. **`[bug-fix]`** — the old behaviour was wrong: incorrect or bad output, a failure, a crash.
   This holds whether or not users could see it, and takes precedence over the other two.
2. **`[feature]`** — otherwise, a user can notice the difference: a new capability, an
   improvement to an existing one, a removal (prefix "Deprecation:" when it is one), a breaking
   change, or a visible change in output, wording, layout or speed.
3. **`[cleanup]`** — otherwise, the change is internal: refactoring, dependency updates, tests,
   docs, logging, or a speed-up nobody would notice.

A visible change too small to be worth a line (a relabel, a restyle, a shortened title) is not
filed as `[cleanup]`: it is dropped. A category says where a line goes, not whether it is
included: the rules in "What NOT to Include" still apply.

Group the bullets by category in that output order — all `[feature]`, then `[bug-fix]`, then
`[cleanup]` — never interleaved.

### Principles

1. **Significance only**: Major changes, not every small modification
2. **Order by impact**: Most important first within each category
3. **User-facing perspective**: Emphasize what affects users or architecture, in the names users
   see rather than internal or code terms ("Dashboard", not "dash-widget"), and say the outcome, not
   the mechanism
4. **One terse line per bullet**: `[category] verb object`. No em-dash elaboration, no parenthetical detail dumps (rate limits, file names, migration numbers, version-by-version lists). "Add CSV export to the reports page" — not "Reports export endpoint — streamed, rate-limited, with optional column selection and a notification email". Multi-line entries are reserved for genuinely sprawling changes (e.g. a multi-finding security audit, a months-long overhaul) — ask before expanding.
5. **Prune hard**: cut secondary clauses, and whole niche changes few readers care about

### What NOT to Include

- Minor bug fixes that don't affect functionality
- Bug fixes for issues introduced in the same release
- Internal refactoring that doesn't change behavior
- Implementation details
- Every small UI tweak
- Routine maintenance (unless significant)
