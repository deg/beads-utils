---
name: status
description: Project status overview — branch and tree state, recent commits, open and in-progress beads, running dev servers, in under twenty lines. Use for /status, or when the user asks where things stand in the current project.
---

# Project status overview

Give a concise orientation for the current project. Run these in parallel and present a short summary:

## Gather

- `git status` — uncommitted changes, current branch
- `git log --oneline -10` — recent commits
- `bd ready` — available work (if beads is configured; skip silently if `bd` not found)
- `bd list --status=in_progress` — active work (same caveat)
- Check for dev servers: look for port numbers in `.env`, `Makefile`, `docker-compose*.yml`, or `vite.config.*`, then check if anything is listening on those ports

## Present

Summarize in this order, skipping sections that are empty:

1. **Branch & state** — current branch, clean/dirty, commits ahead/behind remote
2. **Recent work** — 2-3 sentence summary of what the last few commits did
3. **Open work** — in-progress and ready beads issues, if any
4. **Dev servers** — what's running, on which ports
5. **Uncommitted changes** — brief description if dirty

Keep the whole summary under 20 lines. No preamble.
