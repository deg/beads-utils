# Cut a release

Turn the accumulated `## Unreleased` notes into a numbered release of the
beads-utils script collection. Perform the steps **in order**; do not skip.

Nothing here is packaged or published — there is no `pyproject.toml`, no PyPI,
no installer. Users run the scripts in place. A "release" is purely a marker of
a known-good point: a CHANGELOG heading, a version string, and a git tag.

## 1. Preconditions

- `git status --short` — the tree must be clean. If it isn't, stop and ask the
  user whether to commit or stash first.
- Confirm the branch is `main` (`git branch --show-current`). If not, stop and ask.
- `./bd-dolt-check .` — the beads data must be pushed. If it reports OUT OF SYNC,
  stop and tell the user; `bd dolt push` is their call, not yours.

## 2. Run the quality gates

These mirror `.github/workflows/lint.yml`, so a release never ships something CI
would reject:

```bash
scripts="$(grep -lE -d skip '^#!' * 2>/dev/null)" || true
[ -n "$scripts" ] || { echo "shebang discovery found no scripts"; exit 1; }
printf '%s\n' "$scripts" | xargs uvx ruff@0.15.14 check bdutils.py
printf '%s\n' "$scripts" | while IFS= read -r s; do "./$s" --version; done
```

Keep the guards — they are the same ones CI carries, for the same reason. `-d
skip` makes `grep` ignore subdirectories like `completions/` instead of exiting
2 on them, `|| true` keeps a no-match (`grep` exit 1) from killing the step
before the explicit empty-check runs, and that check is what stops a silent
collapse to "ruff checked `bdutils.py` alone, all passed".

Both must pass. Fix anything that fails — or stop and report — before continuing.

## 3. Determine the change range

```bash
git describe --tags --abbrev=0        # last release tag
git log <that-tag>..HEAD --oneline
```

Show the user the range and the commit list before proceeding.

## 4. Audit `## Unreleased` for completeness

**This is the step that matters most.** Every user-visible commit in the range
must have a bullet. The 0.3.0 cycle drifted precisely here: `dc63e10` shipped
`bd-log --status/--open` and bumped the version but never added its entry, so
the release notes silently under-reported the release.

Walk the commit list against the bullets. For anything user-visible and missing,
draft a bullet in the file's existing voice (see `/changelog` for the category
conventions — `[feature]` / `[fix]` / `[cleanup]` / `[refactor]` / `[breaking]`).
Legitimately skip: CI/lint plumbing, `.gitignore` edits, bead-closing commits,
and fixes for bugs introduced within this same unreleased cycle.

Report what you added. If nothing was missing, say so.

## 5. Choose the version number

Read the assembled bullets and propose `X.Y.Z`. **Bump from the last release tag
found in step 3 — not from `bdutils.__version__`.** Pre-1.0 rules:

- any `[breaking]` or `[feature]` bullet → bump the **minor** (v0.2.0 → 0.3.0)
- only `[fix]` / `[cleanup]` / `[refactor]` → bump the **patch** (v0.2.0 → 0.2.1)

`bdutils.__version__` is a cross-check, not the base. It may already equal the
answer: `dc63e10` bumped it to 0.3.0 mid-cycle, so the first release run finds
tag `v0.2.0` + `[breaking]` bullets → **v0.3.0**, which `__version__` already
reads and step 7 leaves alone. Bumping from `__version__` instead would wrongly
yield 0.4.0 and skip a version. (Contributors no longer bump mid-cycle — see
CONTRIBUTING.md — so after this release the tag and `__version__` stay in step.)

**Confirm the number with the user before writing anything.**

## 6. Update CHANGELOG.md

- Rename `## Unreleased` to `## vX.Y.Z (DDMonYY)` — e.g. `## v0.3.0 (26Jul26)`.
  Get the date with `date +%d%b%y`; match the existing headings exactly.
- Insert a fresh, empty `## Unreleased` section above it, so the next cycle has
  somewhere to accumulate.

## 7. Set the version

Update `__version__` in `bdutils.py` to `X.Y.Z` if it isn't already. It is the
single source of truth — every script's `--version` reads it, and nothing else
in the repo hardcodes a version.

## 8. Verify

```bash
grep -lE -d skip '^#!' * | while IFS= read -r s; do "./$s" --version; done
```

Every script must report the new number. Then `git diff` and confirm the only
changes are `CHANGELOG.md` and `bdutils.py`.

## 9. Commit and tag

```bash
git add CHANGELOG.md bdutils.py
git commit -m "Release vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
```

Annotated tags for real releases. (`v0.2.0` is lightweight — it was backfilled
retroactively, and an annotated tag there would have stamped today's date on a
May release.)

## 10. Stop — do not push

Pushing is the user's call, never the agent's. Print the exact commands and wait:

```bash
git push && git push --tags
bd dolt push        # if bd-dolt-check flagged anything pending
```

Report: the version cut, the bullets added in step 4, and the tag created.
