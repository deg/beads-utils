---
paths:
  - "hooks/claim-guard.sh"
  - "hooks/defer-hint.sh"
  - "tests/test_workflow_hooks.py"
---

# Beads-workflow hooks design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there. The two
memory hooks have their own notes in `claude-memory.md`.

Both hooks are bash under `hooks/`, installed by `make install-claude`,
wired into `settings.json` by hand (the README has the snippet), and built
to be **silent almost always**: a hook that fires on ordinary commands or
ordinary English costs context in every session. Both need `jq`. They moved
here from the owner's private dotfiles (beads-utils-3bf.3).

## claim-guard.sh (PreToolUse, matcher Bash)

The house rule is one bead, one commit, at the boundary. The failure it
catches is an agent that reaches green on one bead and starts the next
without committing; it was seen once as six beads and thirty files
uncommitted at the end of a session. Claiming the next bead (`bd update
<id> --claim`) is the one deterministic step on that path, so the tripwire
sits there: if the git tree holds uncommitted work, the claim becomes a
permission **ask**, with the same text as a `systemMessage` so the user
sees it even in a mode that auto-approves asks.

- **Ask, not deny.** Several agents may share a repo; a dirty tree may be
  another agent's work. The user decides, the agent cannot.
- **`.beads/` is not dirt.** bd's own export goes dirty from closing or
  filing beads and rides along in the next work commit by house rule.
- **A prerequisite is not the next bead** (beads-utils-n5w). When finalize's
  review of a bead turns up a fix that must land first, the dirty tree is
  the in-progress bead's work and cannot be committed before the fix, so
  the ask's advice would be wrong. The relation is recorded in beads as a
  `blocks` dependency (`bd dep add <in-progress> <new>`). If any id that
  blocks a non-epic in-progress bead (`bd show <those> --json`, the
  `dependencies` of type `blocks`) is a whole word of the command, the
  claim passes silently. Words are split on blanks, quotes and shell
  separators, so the check needs no command parsing, and `x-1` never
  matches `x-1.2`. Parent-child links do not count, and neither does
  blocking an epic, which is always in progress. The ask's text ends by
  naming the `bd dep add` step, so an agent claiming a needed fix knows how
  to say so. Both `bd` calls share the `timeout 3`; if either fails, the
  claim asks as before.
- **Known gap: the root is the session's, not the claim's.** A claim run as
  `cd <other-repo> && bd update … --claim` is checked against
  `$CLAUDE_PROJECT_DIR`, so another repo's dirty tree can draw an ask.
  Seen 2026-11-17 (noted in beads-utils-n5w); left alone, because fixing it
  means parsing `cd` out of the command.
- **In-progress beads are named as candidates, never as owners**: every
  agent claims under one assignee, so a match cannot be proven. Epics are
  dropped (always in progress), the list is capped at four, and `bd list`
  runs under `timeout 3` so a Dolt lock cannot stall every claim; a missing
  `timeout`, a missing `bd`, or a failure just omits the clause.
- The claim regex wants `bd` at a word start, then `update` and `--claim`
  as whole words in that order, with anything between (a global flag before
  the subcommand, the id on either side) and any non-word character after
  `--claim` (space, end, `;`, `&`, `)`). Newlines are folded first, so a
  command continued with `\` is one line. `mybd update --claim` and
  `--claimed` do not match. A command that merely *quotes* a claim does
  match: one needless prompt, which an ask can afford, where a quote-aware
  pattern could not be trusted. Review found the shell-separator and
  global-flag cases silent in the owner's original (beads-utils-3bf.3).
- An "ask" reason and the `systemMessage` go to the user; the agent sees
  only `additionalContext`, so the same text is sent there too.
- `git status` runs with `--no-optional-locks`, so the check never takes
  `index.lock` under another agent's commit.
- The root is `$CLAUDE_PROJECT_DIR`, else the payload's `cwd`; no root, or
  not a git work tree, is silence.

## defer-hint.sh (UserPromptSubmit)

When the user asks to park a bead in their own words, inject one line
pointing at the `/defer` skill, because the failure mode is an agent that
"parks" with `bd close` and destroys discoverability. It fires only when
the prompt holds **both** a park-ish verb (defer, park, shelve, postpone,
snooze, sideline, punt, set aside, push off, put off, with their -ing and
-ed forms) **and** a task-ish noun (bead, bd, issue, ticket, task, singular
or plural), so "park the car" stays silent. `deferred` is deliberately not a
verb: Claude Code's own "deferred tools are now available" notices arrive in
the same turn as task-notification blocks, so `deferred` + `task` would
fire on ordinary turns. Known edge, kept in the tests as such: "the parking
lot issue" does fire; the regex has no notion of a noun phrase, and one
stray hint costs a line, where a missed park costs a bead.

The hook sees a slash command **as typed**: since Claude Code 2.1.299,
UserPromptSubmit runs before the command expands (UserPromptExpansion comes
after it). Keep it that way. The expanded `/close-shop` and `/finalize` text
holds both a park verb and a task noun, so before 2.1.299 every run of those
two drew a stray hint; typed, `/close-shop`, `/finalize <id>` and
`/defer <id>` are silent, and a test holds that.

## Manual checks

```bash
echo '{"tool_input":{"command":"bd update x --claim"},"cwd":"'$PWD'"}' | bash hooks/claim-guard.sh   # ask JSON if the tree is dirty, else nothing
echo '{"prompt":"please park this bead"}' | bash hooks/defer-hint.sh                           # the one-line hint
echo '{"prompt":"park the car"}' | bash hooks/defer-hint.sh                                     # nothing
```
