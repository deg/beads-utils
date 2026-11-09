---
name: start-task
description: Start a task — load the beads context, interview the user before any code is touched, create and claim a bead, read the affected files, propose a plan, and wait for an explicit go-ahead. Use for /start-task, or when the user wants to begin a new piece of work and no bead is claimed yet.
---

**MANDATORY: Under NO circumstances should any code changes be made during this phase.**

## 1. Load Context
- Run `bd prime` to load complete workflow context
- Run `bd ready` to show available work
- If a bead ID is provided as an argument, claim it: `bd update <id> --claim` and skip to step 3.

## 2. Create a Bead (if none provided)
If no bead ID was given, interview the user first:
- Ask what they want to do and why
- Clarify scope, affected areas, and constraints
- Once you understand the task, create a bead with `bd create` and claim it
- Then continue to step 3.

## 3. Interview the User (DISCUSS ONLY)
Ask about:
- Task scope and goals
- Which parts of the system are affected
- Specific requirements and constraints
- Any related issues or dependencies

**Crucial**: Even if you think you understand the task, you MUST wait for "go ahead" / "implement" / explicit permission before touching any code.

## 4. User- and Project-Specific Context
Extensions are read from two places, user first, then project, and both are followed:
- `~/.claude/skill-extensions/start-task.md` — the user's own conventions, the same in every project.
- `.claude/skill-extensions/start-task.md` in the project — that project's.

If neither exists, skip this step.

## 5. Identify Source Files
- Find all components, endpoints, models, migrations, and tests related to the task
- Use Glob and Grep to locate relevant files

## 6. Read Source Files
- Read the identified files to understand existing patterns
- Do not skim -- understand before proposing
- State your key assumptions about how the existing code works (data flow, state management, naming conventions) so the user can catch misunderstandings early

## 7. Summarize and Discuss
- Include the bead ID (e.g., `[proj-abc123]`) in your summary for traceability
- Confirm your understanding of the task
- Describe what files will be changed and why
- Ask any remaining questions
- Propose your implementation plan
- **Suggest a session name**: end the summary by proposing a short, meaningful name (a few words) that captures this task, and remind the user to apply it with `/rename <name>`. Renaming is a user-only action — no agent tool can do it — so the user must run the command themselves.
- **Wait for explicit permission before starting implementation**

Implementation begins ONLY after the user says "go ahead", "implement", "do it", or equivalent.

## 8. Record Design Decisions
Once discussion is complete and the user has given permission to implement:
- Update the bead with any key design decisions, architectural choices, or non-obvious tradeoffs that emerged during the discussion (`bd update <id> --append-notes="..."`)
- This preserves context for future sessions, code reviews, and commit authoring
- Do this BEFORE writing code, so the decisions are captured even if the session is interrupted
