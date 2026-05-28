"""Shared Claude Code session helpers for beads-utils scripts.

Sits alongside bdutils.py at the repo root and is the single home for the
session enumeration/resolution logic that both claude-session-report and
claude-session-list need. Stdlib-only, like bdutils.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def mangle_cwd(cwd: Path) -> str:
    """Claude encodes a project cwd as the path with '/' and '.' replaced by '-'."""
    return re.sub(r"[/.]", "-", str(cwd))


def first_cwd(jsonl: Path) -> str | None:
    """Return the 'cwd' field from the first entry that carries one."""
    try:
        with jsonl.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "cwd" in obj:
                    return obj["cwd"]
    except OSError:
        return None
    return None


def find_project_dir(cwd: Path) -> Path | None:
    """Return ~/.claude/projects/<mangled> for cwd, or None if missing.

    Tries the direct mangled lookup first; on miss, scans every project dir
    and returns the one whose first-entry 'cwd' matches (belt-and-suspenders
    in case Claude's encoding rules change).
    """
    direct = CLAUDE_PROJECTS / mangle_cwd(cwd)
    if direct.is_dir():
        return direct
    if not CLAUDE_PROJECTS.is_dir():
        return None
    target = str(cwd)
    for pdir in CLAUDE_PROJECTS.iterdir():
        if not pdir.is_dir():
            continue
        for jsonl in pdir.glob("*.jsonl"):
            recorded = first_cwd(jsonl)
            if recorded and recorded == target:
                return pdir
            break  # one file is enough to identify the project
    return None


def project_label(jsonl: Path, cwd: str | None = None) -> str:
    """Short label for a session's project — prefer the recorded cwd's basename.

    Pass `cwd` (e.g. from a SessionMeta) to skip the file re-read; falls back
    to first_cwd(jsonl) when not provided. Returns the project-dir name if
    neither yields a cwd.
    """
    if cwd is None:
        cwd = first_cwd(jsonl)
    if cwd:
        base = os.path.basename(cwd.rstrip("/")) or cwd
        return base
    return jsonl.parent.name


# XML-style wrapper blocks that Claude Code injects into 'user' entries
# (slash commands, bash !-shortcuts, system reminders, local-command output,
# etc.). A user entry whose content is *only* these wrappers is not a human
# prompt — it's plumbing. Stripping them and checking what's left is the
# canonical "did the human actually type something?" test.
USER_WRAPPER_TAGS = (
    "local-command-caveat",
    "local-command-stdout",
    "command-name",
    "command-message",
    "command-args",
    "system-reminder",
    "task-notification",
    "bash-input",
    "bash-stdout",
    "bash-stderr",
)
_USER_WRAPPER_RE = re.compile(
    "|".join(rf"<{t}>.*?</{t}>" for t in USER_WRAPPER_TAGS),
    re.DOTALL,
)


def has_human_prose(content) -> bool:
    """True if a user message's content has non-wrapper, non-empty text.

    A `/clear` session contributes a user entry whose text is just
    '<command-name>/clear</command-name>...' — stripping the wrapper blocks
    leaves nothing, so the entry doesn't count as a real prompt.
    """
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        text = "\n".join(parts)
    else:
        return False
    return bool(_USER_WRAPPER_RE.sub("", text).strip())


@dataclass
class SessionMeta:
    """Per-session metadata gathered in a single pass over its JSONL."""
    jsonl: Path
    custom_title: str | None
    ai_title: str | None
    cwd: str | None
    first_ts: str | None
    last_ts: str | None
    human_prompts: int
    assistant_turns: int

    @property
    def title(self) -> str:
        return self.custom_title or self.ai_title or "(untitled)"

    @property
    def is_empty(self) -> bool:
        """True when neither side produced anything (e.g. /clear-ghost session)."""
        return self.human_prompts == 0 and self.assistant_turns == 0


def read_session_meta(jsonl: Path) -> SessionMeta:
    """One-pass scan: titles, cwd, first/last ts, human-prompt + assistant counts.

    'human_prompts' = type=='user' entries whose content has non-wrapper prose
    (excludes sidechain subagent turns and pure-plumbing entries like /clear).
    'assistant_turns' = type=='assistant' entries (excludes sidechains).
    All fields tolerate missing/unparseable input — a malformed session yields
    a SessionMeta with None/0 fields rather than raising.
    """
    custom = ai = cwd = first_ts = last_ts = None
    human_prompts = 0
    assistant_turns = 0
    try:
        with jsonl.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                t = obj.get("type")
                if t == "custom-title":
                    ct = obj.get("customTitle")
                    if isinstance(ct, str):
                        custom = ct
                elif t == "ai-title":
                    at = obj.get("aiTitle")
                    if isinstance(at, str):
                        ai = at
                elif t == "user" and not obj.get("isSidechain"):
                    msg = obj.get("message")
                    if isinstance(msg, dict) and has_human_prose(msg.get("content")):
                        human_prompts += 1
                elif t == "assistant" and not obj.get("isSidechain"):
                    assistant_turns += 1
                if cwd is None:
                    c = obj.get("cwd")
                    if isinstance(c, str):
                        cwd = c
                ts = obj.get("timestamp")
                if isinstance(ts, str) and ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
    except OSError:
        pass
    return SessionMeta(
        jsonl=jsonl, custom_title=custom, ai_title=ai, cwd=cwd,
        first_ts=first_ts, last_ts=last_ts,
        human_prompts=human_prompts, assistant_turns=assistant_turns,
    )


def iter_sessions(project_dir: Path | None = None):
    """Yield SessionMeta for every recorded session, or a single project's.

    project_dir=None walks every ~/.claude/projects/*/. Yields nothing if the
    projects directory is missing.
    """
    if project_dir is not None:
        roots = [project_dir]
    else:
        if not CLAUDE_PROJECTS.is_dir():
            return
        roots = [p for p in CLAUDE_PROJECTS.iterdir() if p.is_dir()]
    for pdir in roots:
        for jsonl in pdir.glob("*.jsonl"):
            yield read_session_meta(jsonl)


def list_sessions(project_dir: Path | None = None) -> list[SessionMeta]:
    """All sessions as SessionMeta, newest-first by file mtime."""
    out = list(iter_sessions(project_dir))
    out.sort(key=lambda m: m.jsonl.stat().st_mtime, reverse=True)
    return out


def resolve_session(arg: str) -> Path:
    """Resolve a user-supplied session identifier to a .jsonl path.

    Tries in order: (1) explicit .jsonl path, (2) UUID lookup as
    <arg>.jsonl under any project dir, (3) case-insensitive substring
    against custom-title or ai-title. Ambiguous matches print candidates
    and exit non-zero.
    """
    # 1. Path to a .jsonl file.
    p = Path(arg).expanduser()
    if p.suffix == ".jsonl" and p.is_file():
        return p

    if not CLAUDE_PROJECTS.is_dir():
        sys.exit(f"error: no such directory: {CLAUDE_PROJECTS}")

    # 2. UUID — `<arg>.jsonl` under any project dir.
    direct: list[Path] = []
    for pdir in CLAUDE_PROJECTS.iterdir():
        if not pdir.is_dir():
            continue
        candidate = pdir / f"{arg}.jsonl"
        if candidate.is_file():
            direct.append(candidate)
    if len(direct) == 1:
        return direct[0]
    if len(direct) > 1:
        sys.stderr.write(
            f"error: {len(direct)} sessions named {arg!r} found (unexpected):\n"
        )
        for c in direct:
            sys.stderr.write(f"  {c}\n")
        sys.exit(1)

    # 3. Title substring match.
    needle = arg.lower()
    matches: list[SessionMeta] = []
    for meta in iter_sessions():
        title = meta.custom_title or meta.ai_title
        if title and needle in title.lower():
            matches.append(meta)

    if not matches:
        sys.exit(f"error: no session found for {arg!r}")
    if len(matches) > 1:
        matches.sort(key=lambda m: m.jsonl.stat().st_mtime, reverse=True)
        sys.stderr.write(
            f"error: {len(matches)} sessions match {arg!r} — disambiguate "
            "with a UUID:\n"
        )
        for meta in matches[:25]:
            sys.stderr.write(f"  {meta.jsonl.stem}  {meta.title}\n")
        if len(matches) > 25:
            sys.stderr.write(f"  … and {len(matches) - 25} more\n")
        sys.exit(1)
    return matches[0].jsonl
