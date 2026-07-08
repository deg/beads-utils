"""Shared helpers for beads-utils scripts.

This module lives alongside the scripts in the repo root. Python places the
script's directory on sys.path[0] when executing, so `from bdutils import ...`
resolves the sibling module without any prelude.
"""
from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn

__version__ = "0.3.0"


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
