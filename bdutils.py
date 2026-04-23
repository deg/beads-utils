"""Shared helpers for beads-utils scripts.

This module lives alongside the scripts in the repo root. Python places the
script's directory on sys.path[0] when executing, so `from bdutils import ...`
resolves the sibling module without any prelude.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NoReturn


def error(msg: str) -> NoReturn:
    """Exit with a lowercase 'error: ...' message on stderr."""
    sys.exit(f"error: {msg}")


def warn(msg: str) -> None:
    """Write a 'warning: ...' line to stderr without exiting."""
    sys.stderr.write(f"warning: {msg}\n")


def resolve_project_path(arg: str) -> Path:
    """Resolve a user-supplied project path and verify it has a .beads/ dir.

    Exits with error() if the path is missing the .beads/ marker.
    """
    project_path = Path(arg).expanduser().resolve()
    if not (project_path / ".beads").is_dir():
        error(f"no .beads/ directory at {project_path}")
    return project_path
