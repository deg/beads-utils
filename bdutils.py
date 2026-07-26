"""Shared helpers for beads-utils scripts.

This module lives alongside the scripts in the repo root. Python places the
script's directory on sys.path[0] when executing, so `from bdutils import ...`
resolves the sibling module without any prelude.
"""
from __future__ import annotations

import contextlib
import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn

__version__ = "0.3.0"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def add_version_arg(parser) -> None:
    """Add a standard '--version' flag that prints '<prog> <__version__>'.

    Keeps the version string identical across every beads-utils script so the
    whole collection versions as one unit (see __version__ above)."""
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )


def error(msg: str) -> NoReturn:
    """Exit with a lowercase 'error: ...' message on stderr."""
    sys.exit(f"error: {msg}")


def warn(msg: str) -> None:
    """Write a 'warning: ...' line to stderr without exiting."""
    sys.stderr.write(f"warning: {msg}\n")


def format_ts(iso: str) -> str:
    """Format an ISO-8601 (UTC, 'Z'-suffixed) timestamp as 'YYYY-MM-DD HH:MM' in
    local time. Empty input returns ''; unparseable input is returned as-is."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def format_priority(p) -> str:
    """Render a beads priority value as 'P0'..'P4'. None/'' becomes 'P?'."""
    if p is None or p == "":
        return "P?"
    try:
        return f"P{int(p)}"
    except (TypeError, ValueError):
        return str(p)


def resolve_project_path(arg: str) -> Path:
    """Resolve a user-supplied project path and verify it has a .beads/ dir.

    Exits with error() if the path is missing the .beads/ marker.
    """
    project_path = Path(arg).expanduser().resolve()
    if not (project_path / ".beads").is_dir():
        error(f"no .beads/ directory at {project_path}")
    return project_path


# --- Dolt / git plumbing -------------------------------------------------
#
# Shared by the Dolt-aware scripts (bd-dolt-check, bd-dolt-diff). Every
# helper here is read-only and degrades to a None/empty result rather than
# raising, so callers can report "not verifiable" instead of crashing when
# the dolt CLI is absent or a ref doesn't resolve.


def strip_ansi(s: str) -> str:
    """Remove ANSI SGR escapes (the dolt CLI colorizes even when piped)."""
    return ANSI_RE.sub("", s)


def run(cmd: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Capture-output subprocess run rooted at `cwd` (never os.chdir)."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


@functools.cache
def have_dolt() -> bool:
    """True if the `dolt` CLI is on PATH."""
    return shutil.which("dolt") is not None


def read_metadata(beads_dir: Path) -> tuple[str, str]:
    """Return (dolt_database, dolt_mode) from .beads/metadata.json."""
    path = beads_dir / "metadata.json"
    if not path.is_file():
        error(f"no metadata.json in {beads_dir}")
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        error(f"could not read {path}: {exc}")
    return data.get("dolt_database", "unknown"), data.get("dolt_mode", "unknown")


def locate_dolt_db(beads_dir: Path, db_name: str) -> Path | None:
    """Find the Dolt database dir, covering both embedded and server layouts."""
    for candidate in (beads_dir / "embeddeddolt" / db_name, beads_dir / "dolt" / db_name):
        if (candidate / ".dolt").is_dir():
            return candidate
    return None


def read_repo_state(dolt_db_dir: Path) -> dict:
    """Parse .dolt/repo_state.json, or {} if unreadable."""
    path = dolt_db_dir / ".dolt" / "repo_state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def get_head_branch(dolt_db_dir: Path) -> str:
    """Current Dolt branch name from repo_state.json (default 'main')."""
    head = read_repo_state(dolt_db_dir).get("head", "")
    prefix = "refs/heads/"
    return head[len(prefix):] if head.startswith(prefix) else "main"


def read_dolt_remotes(dolt_db_dir: Path) -> dict[str, str]:
    """Map of Dolt remote name -> url from repo_state.json."""
    remotes = read_repo_state(dolt_db_dir).get("remotes", {}) or {}
    return {name: r.get("url", "?") for name, r in remotes.items()}


def get_git_remote_url(project_path: Path) -> str:
    """URL of git remote 'origin', or '(no remote)'."""
    url = run(["git", "remote", "get-url", "origin"], cwd=project_path).stdout.strip()
    return url if url else "(no remote)"


def dolt_fetch(dolt_db_dir: Path, remote: str) -> bool:
    """Best-effort `dolt fetch <remote>` to refresh remote-tracking refs.

    Returns True on success. Used so a remote that moved ahead (e.g. pushed
    from another machine) is reflected in remotes/<remote>/<branch> before we
    compare against it.
    """
    if not have_dolt():
        return False
    return run(["dolt", "fetch", remote], cwd=dolt_db_dir).returncode == 0


def dolt_rev(dolt_db_dir: Path, ref: str) -> str | None:
    """Commit hash at `ref`, or None if dolt is missing or `ref` doesn't resolve."""
    if not have_dolt():
        return None
    result = run(["dolt", "log", "--oneline", "-n", "1", ref], cwd=dolt_db_dir)
    if result.returncode != 0:
        return None
    lines = strip_ansi(result.stdout).strip().splitlines()
    return lines[0].split()[0] if lines and lines[0] else None


def dolt_count_range(dolt_db_dir: Path, rev_range: str) -> int | None:
    """Number of commits in a Dolt `A..B` range; None if dolt is missing or it errors."""
    if not have_dolt():
        return None
    result = run(["dolt", "log", "--oneline", rev_range], cwd=dolt_db_dir)
    if result.returncode != 0:
        return None
    return sum(1 for ln in result.stdout.splitlines() if ln.strip())


def dolt_log_range(dolt_db_dir: Path, rev_range: str) -> list[str]:
    """One-line commit summaries for a Dolt `A..B` range, oldest last."""
    if not have_dolt():
        return []
    result = run(["dolt", "log", "--oneline", rev_range], cwd=dolt_db_dir)
    if result.returncode != 0:
        return []
    return [strip_ansi(ln) for ln in result.stdout.splitlines() if ln.strip()]


def dolt_sql_json(dolt_db_dir: Path, query: str) -> list[dict] | None:
    """Run a read-only query and return its rows, or None on any failure.

    Dolt emits `{"rows": [...]}`. Note that JSON output omits NULL columns
    entirely, so callers must use `.get()` rather than indexing.
    """
    if not have_dolt():
        return None
    result = run(["dolt", "sql", "-r", "json", "-q", query], cwd=dolt_db_dir)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout).get("rows", [])
    except (json.JSONDecodeError, AttributeError):
        return None


def dolt_table_columns(dolt_db_dir: Path, table: str, rev: str | None = None) -> list[str]:
    """Column names of `table`, optionally at revision `rev`.

    Needed because a schema migration can add columns, so two revisions of
    the same table may not share a column set — selecting a column that only
    exists on one side is a hard error in Dolt. Callers that compare across
    revisions should intersect the two results.
    """
    if rev:
        # `'` is legal in ref names and `dolt sql -q` runs `;`-separated
        # statements, so an unescaped rev could break out of the literal.
        safe_rev = rev.replace("'", "''")
        target = f"{table} as of '{safe_rev}'"
    else:
        target = table
    rows = dolt_sql_json(dolt_db_dir, f"describe {target};")
    if rows is None:
        return []
    return [r["Field"] for r in rows if "Field" in r]


def _open_pager() -> subprocess.Popen[str] | None:
    if not sys.stdout.isatty():
        return None
    pager_env = os.environ.get("PAGER", "").strip()
    if pager_env:
        cmd = shlex.split(pager_env)
    elif shutil.which("less"):
        cmd = ["less", "-FRX"]
    else:
        return None
    env = os.environ.copy()
    env.setdefault("LESS", "FRX")
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True, env=env)
    except OSError:
        return None


@contextlib.contextmanager
def paged_output(no_pager: bool = False):
    """Yield a writable stream piped through $PAGER (or 'less -FRX') when
    stdout is a tty; otherwise yield sys.stdout.

    '-F' makes less exit immediately when content fits one screen, so short
    output is indistinguishable from direct-to-stdout. BrokenPipeError is
    swallowed so Ctrl-C / quitting the pager is clean — and on the direct
    stdout path, sys.stdout is redirected to /dev/null afterwards so Python's
    atexit flush can't re-raise when the consumer (e.g. `… | head -1`)
    closed the pipe before we finished writing.
    """
    pager = None if no_pager else _open_pager()
    out = pager.stdin if pager else sys.stdout
    try:
        yield out
    except BrokenPipeError:
        if pager is None:
            try:
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, sys.stdout.fileno())
            except OSError:
                pass
    finally:
        if pager is not None:
            with contextlib.suppress(BrokenPipeError):
                pager.stdin.close()
            pager.wait()
