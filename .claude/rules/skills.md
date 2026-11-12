---
paths:
  - "skills/**"
  - "tests/test_skills.py"
---

# Beads-workflow skills design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

Seven Claude Code skills, one directory each under `skills/<name>/SKILL.md`.
Six moved here from the owner's private dotfiles (beads-utils-3bf.2), where
they had run as `~/.claude/commands/*.md` since 2026-03; `/review-titles` was
written here (beads-utils-wnb). They divide the work of a session and are not
interchangeable:

| Skill | Scope | When |
| --- | --- | --- |
| `/start-task` | one task | Before writing code. Interviews first, then creates and claims a bead, and waits for a go-ahead. |
| `/finalize` | one task | When a bead's work is done. Self-review, tests, gates, a senior review, a commit the user approves, then `bd close`. Runs per bead. |
| `/close-shop` | the **session** | Once, at the end. Audits every standing memory and every open bead before adding anything new. |
| `/defer` | one bead | Parks a bead without closing it, recording the gate for revisiting. The hook `defer-hint.sh` points at it. |
| `/review-titles` | the open beads | Checks each title against `title-rules.md` and the code, says which are kept, then retitles the rest one at a time on a one-word answer. |
| `/status` | the project | A twenty-line orientation. |
| `/changelog` | the repo | A changelog entry for the range since the last tag, in the file's own style. |

## Why skills, linked by directory, and not a plugin

Plugin commands are always typed `/<plugin>:<name>`; the docs give no alias
mechanism. These are typed many times a day, so they stay bare. A personal
skill in `~/.claude/skills/<name>/SKILL.md` answers to `/<name>`, and a
*symlinked* skill directory loads the same way (verified 2026-11-09 with a
throwaway `/zz-probe` skill, linked and then removed). So `make
install-claude` links each `skills/<name>` directory into
`~/.claude/skills/`, refusing to replace anything that is not already a
symlink, as `install` does for scripts. The repo stays the single source;
an edit takes effect at the next session with no reinstall.

## Extensions: two places, user first

`/start-task`, `/finalize`, `/defer`, `/close-shop` and `/review-titles` read
an extension file and follow it, from two places in order:

1. `~/.claude/skill-extensions/<name>.md`, the user's own: standing
   permissions and conventions that hold in every project.
2. `.claude/skill-extensions/<name>.md` in the project: that project's steps
   (type regeneration, always-check documents).

The user level exists because of the port: the dotfiles `/close-shop`
carried the owner's standing permission to push beads data and memory
commits without asking. A public skill cannot grant that, so it now says
"pushing is the user's call" and defers to the user's extension, where the
owner's carve-out lives. `tests/test_skills.py` holds the line: the public
`/close-shop` grants itself nothing. The one push it makes without asking is
the memories repo's, through `commit-memories.sh`: that is the push the
SessionEnd hook makes anyway whenever the repo has an upstream, so the
upstream the user configured is the consent, and the skill says so rather
than pretending it never pushes.

## The title rules are a file, not a section of the skill

The rules a title is judged by live in `skills/review-titles/title-rules.md`,
not in `SKILL.md`, because they are needed at two moments. `/review-titles`
reads them when it runs. But a title is written far more often than it is
reviewed, at every `bd create`, and a skill is not in context then. So a
user's global `CLAUDE.md` imports the file
(`@~/.claude/skills/review-titles/title-rules.md`), through the same link
`make install-claude` makes, and the rules apply in every session.

The rules first stood in the owner's global `CLAUDE.md`, and the bead asked
the skill to point there. That is the pointer this port scrubbed once already
(below), and `test_nothing_personal_is_in_the_public_text` refuses one. Two
copies were rejected because they drift. Keeping the rules in the user's
extension file would leave the public skill with none. With the import there is
one copy, and it is public. The leak check covers every file under `skills/`,
not just `SKILL.md`, for this file's sake.

`/review-titles` takes every length from `jq`, never by eye: an agent
counting characters gets them wrong, and the length is often the thing the
user is deciding on. No script does a mechanical pre-pass: length is one
`jq` filter, and milestone codes and design-doc coinages need judgment.

## What was scrubbed, and what deliberately was not

Gone: every path into the private dotfiles (the skills now call
`bd-find-live`, `claude-memory-check` and `~/.claude/hooks/commit-memories.sh`
by their installed names), a client project's bead id in `/finalize`'s
commit-message example, a client's domain in `/changelog`'s example, the
owner's name, the dates on two anecdotes, and a pointer to a rule in the
owner's global `CLAUDE.md` (the rule is stated in full where it was cited).
Kept, anonymised: the signature-format incident in `/close-shop`, because
the point it makes (contradicting evidence is not falsifying evidence) is
the one that stops the audit doing damage. The test's leak check uses
generic markers only; client names are never written into this repo, and
the sweep for them is a manual grep before each commit.

`/changelog`'s category vocabulary (`[bug-fix]`, `[feature]`, `[cleanup]`)
is not this repo's (`[breaking]`, `[feature]`, `[fix]`, `[refactor]`,
`[cleanup]`); the skill reads the existing CHANGELOG and matches its style,
so both are right where they are used.

## Manual checks

```bash
make install-claude CLAUDE_HOME=/tmp/claude-home && ls -l /tmp/claude-home/skills   # links, not copies
head -4 skills/*/SKILL.md                                                           # every frontmatter
grep -rn 'skill-extensions' skills/                                                 # the two-place lookup, user first
/review-titles                         # in a real beads project: kept list first, then one bead per message
```
