---
name: close-shop
description: Close out a SESSION (not a task) — audit every standing memory against what the code does now, correct what rotted, and only then record what this session learned. TRIGGER when the user says they are ending/wrapping up the session, that context is getting full, asks "anything we need to preserve for future sessions", or asks what to carry forward. Run once at session end; /finalize closes a task and runs per bead.
---

# Close shop — end-of-session memory audit

`/finalize` closes out a **task**. This closes out a **session**.

Its job is not to add notes. Its job is to **audit the notes that already exist**, because
this session's own work is the most likely thing to have invalidated them. A memory that
has gone false is worse than no memory at all — every future session will believe it.

**MANDATORY ORDERING: audit first, add last.** Do not write a single new memory until the
existing ones have been read and judged. Reversing this is the whole failure mode: an
agent that starts by adding never looks at what it is adding to, and the store silently
accumulates contradictions.

## 1. Gather this session's evidence

**First, ask the user which kind of close this is.** You cannot know, and the answer
changes step 4 and step 6:

- **Work complete** — this line of work is finished; the next session starts on something else.
- **Baton pass** — the work continues, but this context is exhausted and a successor picks it up.

The boundary is genuinely fuzzy and you will often be between the two. **When in doubt,
treat it as a baton pass.** The extra material goes into the in-progress bead, which closes
and takes the note with it, so a handoff you did not need costs one paragraph. A handoff
you needed and skipped costs your successor every dead end, rediscovered from scratch.

Then assemble what the audit will be judged against:

- `git log --oneline --since="6 hours ago"` (widen if the session ran longer) and
  `git diff` — what actually changed.
- The beads touched this session (`bd list --status=in_progress`, plus any closed today).
- What you learned that is **not** in the diff — dead ends, tests that looked green but
  could not fail, verification steps that were worthless because they reused a broken path.
  Hold this for step 6; it is the one input no subagent can reconstruct.

## 2. User- and project-specific setup

Extensions are read from two places, user first, then project, and both are followed
**now**, before the audit:

- `~/.claude/skill-extensions/close-shop.md` — the user's own: standing permissions
  (what they have said may be pushed), conventions, always-check documents that apply in
  every project.
- `.claude/skill-extensions/close-shop.md` in the project — that project's always-check
  documents and conventions.

If neither exists, skip this step. Where this skill says "ask", a standing permission
granted in the user's extension answers the question; nothing else does.

## 3. Audit every standing memory — and every open bead (delegate both)

There are **two** memory stores and both are audited:

| Store | List | Read | Update | Delete |
| --- | --- | --- | --- | --- |
| beads | `bd memories` | `bd recall <key>` | `bd remember --key <key> "..."` (in place) | `bd forget <key>` |
| Claude Code | the memory directory named in your system prompt | read the `.md` file | edit the file | delete file **and** its `MEMORY.md` pointer line |

Do not hardcode the Claude Code memory path — it is keyed by project directory and your
system prompt names the right one.

**First run the link checker** — it is mechanical, it takes a second, and it finds the one
kind of rot a reader never will:

```sh
claude-memory-check <the memory dir>
```

`ERROR` lines are links that were meant to resolve and silently do not (usually hyphens vs
underscores after a rename), plus `MEMORY.md` disagreeing with the directory. Fix those
here, before the audit — they are unambiguous and they need no judgment. `pending` lines
are links to memories not written yet, which the memory format explicitly permits; leave
them, but read them, because a forward link nobody ever cashed is often a memory worth
writing in step 6. The checker catches a link resolving to NOTHING; it cannot catch one
resolving to the WRONG memory, which is what the subagent below is for.

**Spawn one fresh subagent to do the reading.** Give it the memory files, the `bd memories`
output, and this session's diff and log. Two reasons, both real:

- Your context is nearly full — that is why this command is running at all.
- More importantly, you are **anchored**. The memories were invalidated by your own work,
  and you will read them through your own narration of that work. A subagent reads cold.

The subagent is **read-only. It proposes; it writes nothing.** Require a verdict per memory
with concrete evidence (`file:line`, or a command and its output):

- **accurate** — still true, evidence cited.
- **wrong** — makes a claim the code now contradicts.
- **stale** — described a real hazard that this or a previous change removed.
- **duplicate of `<key>`** — covers ground another memory already covers.
- **unverifiable** — see the trap below.

**THE TRAP — read this before acting on any verdict.** Most memories are not claims about
code. They are claims about the *user*: how they want work done, what they dislike, what
counts as a go-signal. Those cannot be checked against a diff and **must never be deleted
for lack of code evidence**. Absence of evidence is `unverifiable`, and `unverifiable`
means **leave it alone**. Only a memory that the code actively *contradicts* is `wrong`.
Say this explicitly in the subagent's instructions — it is the way this command does damage.

**THE SECOND HALF OF THE TRAP — contradicting evidence is not falsifying evidence.** A
memory recording a user *instruction* cannot be falsified by the artifacts it governs. If
ten commits, letters, or files contradict it, the finding is that **the instruction is
being violated** — file that as work, not as a correction. Only the user can retire a
preference they stated. This is not hypothetical: an audit once marked a
signature-format instruction `wrong` because ten of ten outbound letters disagreed with
it, and softened it to "unresolved". The user then confirmed the instruction stood and
had simply been ignored for a month, by agents copying the previous letter instead of
reading the memory. The audit had used the bug as proof that the rule was stale.

Sweep **all** memories, every time. A sweep filtered to "things this session touched"
rebuilds the exact blind spot this command exists to fix: nobody re-reads a note that is
not yet causing trouble.

**Give the same subagent a second question: which open beads are already finished?** It
already has the diff, the log and the bead list in front of it, and it is the one reader
here who is not anchored by having done the work.

**Hand it the beads LEAN — but never silently.** Do not paste whole beads. Drop the
append-only log, keep everything else, and tell the subagent exactly how much it is not seeing:

```sh
bd-find-live --lean
```

That is open + in_progress minus parked beads (see "Bead hygiene" below). It names the parked
beads it leaves out on stderr; pass that line on to the subagent too.

`notes` is an append-only log of how a bead got here; the subagent is judging whether it is
DONE. But **do not assume the description carries current truth** — that is a convention beads
grow into, not a guarantee. Some beads have an empty or one-line description with everything
real in the notes, and `design`, where present, is usually a SPEC rather than history, so it
stays in.

`notes_len` is what makes the elision honest: a bead showing a 600-character description and
`notes_len: 37000` is one the subagent must open with `bd show <id>` before judging. Tell it to
expand any bead whose description is empty, thin, or small relative to `notes_len`, and to
report which ones it expanded and why — that list is itself a finding, because it names the
beads whose current truth is in the wrong field.

Ask it over that lean listing — **all** of them, not just the ones this session touched —
for a verdict per bead, held to the same standard of evidence as the memories:

- **done** — the description's stated deliverable or acceptance criteria is satisfied; cite
  the `file:line` or the commit that satisfies it.
- **not done** — name what is still missing.
- **superseded by `<id>`** — another bead has taken this one over.
- **abandoned** — nobody intends to do this any more.

`bd stale` is a prefilter, not the test. A bead can be freshly touched and complete, or
untouched for a month and still genuinely open.

## 4. Apply the verdicts

You apply them, not the subagent — the memory verdicts here, the bead verdicts in step 5.
The memory policy splits on **whether the change can be undone**:

- **Corrections — apply directly.** Rewriting a memory in place is safe in both stores.
  `bd remember --key <existing-key>` updates in place and each write is its own Dolt
  auto-commit, so the previous text stays recoverable.
- **Deletions and merges — ASK THE USER FIRST.** A merge is a delete plus a rewrite, so it
  lands here too. Show the memory, the verdict, and the evidence, and wait.

**On a baton pass, distrust every `stale` verdict.** Half-finished work makes memories look
stale when they are not: if you have torn out a mechanism you are only partway through
reinstating, the note describing it reads exactly like a note the code has outgrown. Ask of
each one — stale because the work is **done**, or because the work is **half-done**? If it
is half-done, keep the memory and say so in the handoff.

Both stores are recoverable, but not equally. `bd forget` is undone from Dolt, which keeps
every write. Claude Code memory files have history only if the memories repo is set up
(`claude-memory-setup`, with `commit-memories.sh` committing at every session end); then a
delete is undone from git — but only back to the **last session-end snapshot**. A memory
written and deleted inside one session has no commit to recover from, which is why the
confirmation still stands. Without that repo, a deleted memory file is simply gone.

To recover a deleted Claude Code memory from the memories repo:

```sh
G=${CLAUDE_MEMORIES_GIT:-$HOME/claude-memories.git}
git -C ~/.claude/projects --git-dir=$G log --oneline -- <slug>/memory/<file>.md   # last commit holding it
git -C ~/.claude/projects --git-dir=$G checkout <commit> -- <slug>/memory/<file>.md
```

To recover a forgotten beads memory, read the `config` table at the commit before the
`bd: forget` auto-commit — memories are stored there as `kv.memory.<key>` rows:

```sh
cd .beads/embeddeddolt/*/          # the DB dir, named for the issue prefix
dolt log --oneline                 # find the commit just before "bd: forget"
dolt sql -q "select value from config as of '<commit>' \
             where \`key\` = 'kv.memory.<key>'"
```

`dolt log` must run from that inner directory; from `.beads/embeddeddolt` itself it reports
"not a valid dolt repository".

When two memories cover one topic and one is false, folding them together beats leaving
both: two memories on one topic where one is false is worse than either alone.

**Deleting a Claude Code memory means deleting the file AND removing its line from
`MEMORY.md`.** Skip the second half and the index is left pointing at nothing.

## 5. Refresh long-lived beads and documentation

- **Beads that are done but still open.** Work from the subagent's verdicts, and
  **propose — do not close.** Show the bead, the verdict and the evidence, and wait, exactly
  as for a memory deletion: "I'm pretty sure we finished that" is the same anchoring this
  command distrusts everywhere else. Two exemptions are absolute:
  - **The handoff target.** On a baton pass, step 6b is about to append `HANDOFF` to the
    in-progress bead. That bead stays open however done it looks.
  - **Done is not abandoned.** A bead nobody intends to finish gets `bd supersede` (below)
    or `/defer` — never `bd close`. Closing to park destroys discoverability, which is the
    whole reason `/defer` exists.

  Carry step 4's baton-pass question across too: finished because the work is **done**, or
  finished-*looking* because it is **half-torn-out**? On a baton pass, keep it open.
- **Long-lived beads**, especially epics: if a bead has accreted append-notes until its
  current focus is buried, or its description states something this session made untrue,
  refresh it — by PREPENDING a `## CURRENT STATE` header to the description under Tier 2 of
  **Bead hygiene** below, which is draft-and-ask and never rewrites the notes log. Where one
  bead has genuinely been replaced by another, `bd supersede <old> --with <new>` closes it with
  a pointer rather than losing the thread.

### Bead hygiene

Where beads have grown long, they are often the biggest input to this command — but the fix is
almost never to make a bead smaller. It is to take it out of the audit.

**Closed and deferred beads cost this command nothing.** `bd list --status=open` returns only
status `open`; deferred is a separate status, and this step reads open + in_progress. Confirm
it in any project with `bd list --status=open --json | jq -r '[.[].status]|unique'`. So a
bead's length stops mattering the moment it is closed or deferred, and both preserve its
history in full.

**Neither do parked beads.** A batch gate parks a group by blocking each member on a deferred
gate bead, or on a parent that is, and the members keep status `open`. `bd-find-live`
leaves out any bead whose chain of blockers reaches a deferred bead, so a gated member costs
nothing either. A bead waiting on live work is not parked and stays in the audit.

**Propose closing or deferring, not rewriting.** Close and defer remove all of a bead's cost
and lose nothing. Trying to shorten a bead in place tends to take decisions, traps, file paths,
undo instructions and number qualifiers along with the narrative, so it buys little and risks
a lot.

Two tiers, and do not blur them:

- **Tier 1, do it yourself: DIAGNOSE.** Report oversized open/in_progress beads with their SIZE
  and their AGE, plus the total open payload. Pure reporting, no writes. Size says what a bead
  costs; age says whether it should still be open at all. A large, long-untouched bead is a
  triage question — resume, defer or close — not a rewrite target.
- **Tier 2, DRAFT AND ASK: the CURRENT STATE header**, for a bead that must stay open and whose
  focus is genuinely buried. Never write one unprompted — a wrong header is worse than none,
  because it renders first in `bd show` and reads as authoritative. Mechanics: `--body-file`
  writes the DESCRIPTION only, so build the file as new-header + the existing RAW description
  from `bd show <id> --json`, then verify the `notes` and `design` byte-lengths are unchanged
  before and after. Size the header to what it summarizes; any fixed line-count target is
  wrong. A header does not shrink the payload: it reorders truth, it removes nothing.

**Append to the notes log by default; rewrite only with the user's yes.** `bd update --notes`
and `--description` REPLACE the whole field, and the log's ORDER carries meaning — a
"superseded" marker only means anything positioned after what it supersedes. Append with
`bd update <id> --append-notes="..."` and correct by appending. A rewrite is fine when it loses
nothing a reader needs (notes that are only one session's design talk, or text fully superseded
and captured elsewhere in the bead): offer it, say why it is safe, and wait for a yes.

**Report the open payload as a number every session** — it is what makes drift visible before
it becomes a crisis:

```sh
bd-find-live | wc -c
```

Say what it is and whether it moved. Every close and every defer needs the user's explicit
approval, per bead. Park with `/defer`, never `bd close`.

- **Documentation: scope this to the diff**, unlike memories. Docs live in the repo and turn
  up in greps — they have adjacency, which is exactly what memories lack. Check the docs
  this session's changes bear on, plus anything step 2 named. Do not sweep all of `docs/`.

## 6. Only now, record what this session learned

With the store honest, add what is worth carrying forward — the material from step 1 that
exists nowhere but your own context. Be selective: most of what a session learns is
throwaway, and this session is the only moment anyone can tell the difference.

### 6a. Both cases — memories and follow-up beads

- Generalizes beyond this task, and will still be true next month -> a memory.
- Concrete follow-up work -> a bead (`bd create`), not a memory.
- True only of the change you just made -> neither. Let it go.

Prefer updating an existing memory over adding a near-duplicate beside it.

### 6b. Baton pass only — write the handoff

Append a `HANDOFF` block to the in-progress bead (`bd update <id> --append-notes=...`).

**It goes in the bead, never in a memory.** Handoff material is task-scoped — it dies when
the task closes, and a bead dies with it. The same text in the memory store would be false
within days and nothing would ever re-read it, which is the precise failure this whole
command exists to prevent. Beads have a lifetime; memories do not. Match the store to the
lifetime.

Cover:

- **State** — what is done, what is in flight, what is next.
- **Working tree** — branch, uncommitted files, whether lint and tests currently pass.
- **Dead ends, with the reason each was abandoned.** The most valuable item here and the
  one most reliably lost. Without it your successor repeats the entire search, and it is
  invisible in the diff because failed attempts leave no trace in the code.
- **Open decisions** — anything waiting on the user, quoted closely enough to act on.
- **Anything the user said that is not written down anywhere yet.**

Write it to be read **cold**, by an agent holding none of your context. Name files and
beads explicitly; "the fix we discussed" means nothing to your successor.

## 7. Commit and push

- Report what changed: memories corrected, deleted, merged, added; beads and docs touched.
- **`git push` does NOT carry your memory edits. You must also run `bd dolt push`.**
  Beads memories live only as `kv.memory.*` rows in the Dolt DB at `.beads/embeddeddolt/`,
  which is **gitignored** (`.beads/.gitignore`) and absent from `issues.jsonl`. Beads
  syncs them through `refs/dolt/data` on the git remote, which no ordinary `git push`
  updates. Skip `bd dolt push` and every correction you just made is stranded on this
  machine — the command silently fails at the one job it exists to do.
- **Pushing is the user's call.** Ask for `bd dolt push` and `git push` unless the user's
  extension (step 2) grants a standing permission for exactly that; then say you are using it.
- **Commit the Claude Code memory edits now, with a message that says what the audit
  did**, if the memories repo is set up (`claude-memory-setup`). The SessionEnd hook
  (`~/.claude/hooks/commit-memories.sh`) would snapshot them anyway, but its message is
  generic; this is the one commit that can say *why* a memory changed. Call the hook script
  with the message, so the commit goes through the same fail-closed guard as the automatic
  one (a bare `git add` would bypass it). It commits to the memories repo, and pushes only
  if the user has given the branch an upstream; report whether it did:

  ```sh
  bash ~/.claude/hooks/commit-memories.sh \
       "<what the audit corrected/removed/added>" </dev/null
  ```

  It is silent either way; with `G=${CLAUDE_MEMORIES_GIT:-$HOME/claude-memories.git}`,
  check `git --git-dir=$G log --oneline -1`. If no commit appeared and memory files did
  change, the guard refused: a non-memory file is visible under `~/.claude/projects/` (find
  it with `git -C ~/.claude/projects --git-dir=$G status -uall`), or more than 20 memory
  files were deleted at once (commit those by hand). The hook records why in
  `$G/last-refusal`, and the SessionStart hook shows it. The push runs in the background;
  its output is in `$G/last-push.log`.
- **Working-tree CODE changes are NOT covered by any standing permission.** If the tree
  holds code, ask for `commit?` and `push?` as separate confirmations, exactly as always.
- **Stage explicitly. Never `git commit -a`** — the tree may hold unrelated changes the
  user has not decided about.
- Finish what was approved: `git pull --rebase && git push`, then `bd dolt push`. Confirm
  `git status` is clean and the `bd dolt push` reported "Push complete."

## 8. Name the session

Last, because only now is the whole session's work known. A name chosen here can sum it
up; a name chosen at the start describes the first task at best. Keep it a step of its
own — folded into step 7's report it gets skipped.

A user-given name is what makes a session findable later in `/resume` history. Look it up
in this session's own transcript, located exactly through `$CLAUDE_CODE_SESSION_ID` (never
"the newest file" — parallel sessions make that wrong):

```sh
t=$(find ~/.claude/projects/ -maxdepth 2 -name "$CLAUDE_CODE_SESSION_ID.jsonl" | head -1)
[ -n "$CLAUDE_CODE_SESSION_ID" ] && [ -f "$t" ] || echo "transcript NOT FOUND -> cannot tell"
echo "custom: $(grep -h '"type":"custom-title"' "$t" | tail -1 | jq -r .customTitle)"
echo "ai:     $(grep -h '"type":"ai-title"'     "$t" | tail -1 | jq -r .aiTitle)"
```

`custom-title` is written by `/rename` and is the only user-given name. `ai-title` is
Claude Code's own auto-generated title and does **not** count. The last record of each
wins.

**Always print the current name on its own line** — the GUI does not always show it:

- **Named** -> `Session name: "<name>"`. If it clearly undersells what the session did
  (typically `/start-task` named it after the first of several tasks), also suggest a
  broader one. Otherwise just confirm it. A name spanning several lines is a prompt pasted
  into `/rename` (it happens): show its first line and suggest a clean one.
- **Only an auto title** -> say there is no user-given name, show the `ai-title`, and
  suggest one.
- **Cannot tell** (variable unset, no transcript, records not found in the expected
  shape) -> say so, and suggest one. Uncertain counts as unnamed.

A suggestion is a few words naming what the session **accomplished**, written for someone
scanning a history list months from now. End it with a reminder to run
`/rename <name>` — renaming is a user-only action and no agent tool can do it.
