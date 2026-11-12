---
name: review-titles
description: Review a project's bead titles against the title rules and retitle them one at a time, the user answering each in a word. Use for /review-titles, or when the user asks to review, audit, clean up or fix the titles of the open beads.
---

# Review bead titles, one at a time

Every title is judged against the rules in `title-rules.md`, beside this file. Read it
now. Those rules are the single source; do not restate or extend them here or in what
you show the user.

The user decides each title. Your part is to check, propose and apply what they approve.

## 1. User- and project-specific context

Extensions are read from two places, user first, then project, and both are followed:
`~/.claude/skill-extensions/review-titles.md`, then `.claude/skill-extensions/review-titles.md`
in the project. If neither exists, skip this step.

## 2. List the beads

The argument picks the set. Each source prints a JSON array of beads:

- **None**: the live beads, open or in progress and not parked behind a deferred bead.
  These are the titles read every day. `bd-find-live --lean` names the parked beads it
  left out on stderr; pass that on to the user.
- **A parent id**: its children, `bd list --parent <id> --status=open,in_progress --limit 0 --json`,
  run again for any child that has children of its own.
- **Several ids**: those beads, `bd show <id> <id> ... --json`.
- **`all`**: deferred and parked beads too,
  `bd list --status=open,in_progress,blocked,deferred --limit 0 --json`.

Pipe the source through one filter, which puts each title's length first:

```bash
jq -r '.[] | "\(.title|length)\t\(.id)\t\(.status)\t\(.title)"'
```

Take every length from a command, never by eye: the length is often what the user is
deciding on. For a proposed title, `jq -rn --arg t "<title>" '$t | length'`.

If the set holds more than about 25 beads, say how many, and offer to narrow it by
parent or priority before starting. Twenty-five one-word answers is already a long sitting.

## 3. Check every title before proposing anything

For each bead, read its description, not just its title (`bd show <id>`). Then check
the title's claims against the code and the project's design docs. A title can read
well and still be wrong about what the bead is: an "A/B test" that is an offline
comparison, a "library" for a page that already exists. This is where the review earns
its keep, so do it for every bead, including the ones whose titles look fine.

Then sort the beads in two groups: titles that meet the rules and are kept, and titles
to change.

## 4. Say up front what is kept

One list, id and title, so the user can object to a keep before the one-at-a-time part
starts. If they do, that bead joins the ones to change.

## 5. Show the rest one at a time

Before showing each bead, run `bd show <id>` again. If its status, assignee or title
changed since the listing (another session claimed it, closed it or retitled it), say
so, and ask whether to go on with it.

Show:

```
<id>  (<status>)
  now:      <current title>   (<length>)
  proposed: <new title>       (<length>)
  why:      <one short clause: which rule, or what the title gets wrong>
```

The user answers in a word:

- **ok**: run `bd show <id>` once more, then `bd update <id> --title="<new title>"`, then
  show the next.
- **change**, or a question about a word: offer two or three alternatives, each with
  its length, and say which you recommend and why. Apply the one the user picks.
- **skip**: leave it, and go on.

One bead per message. Do not batch them, and do not apply a title the user has not
seen in its final form.

## 6. When a bead's intent is unclear

Ask the user. If they are not sure either, pick the more likely reading and append a
note saying so: `bd update <id> --append-notes="Title review: intent unclear, read as
<reading> because <reason>."` Use `--append-notes`, never `--notes` or
`--description`; those replace the field, and the original text must stay.

## 7. Finish

Report the counts: kept, retitled, skipped. List any bead that changed under you
during the review, and any whose notes now record an unclear intent.

Retitling writes only beads data. This skill commits nothing and pushes nothing;
pushing the beads data is the user's call.
