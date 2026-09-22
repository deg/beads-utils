#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["rich", "resvg-py"]
# ///
"""Render each script's real terminal output to a PNG for the README.

Not a screen capture. Each command is run with ``--color=always`` into a
pipe, and the ANSI it emits is rendered deterministically: rich turns it
into an SVG, which resvg rasterizes. Nothing depends on anyone's terminal,
so the images are reproducible on any machine.

``resvg-py`` rather than ``cairosvg``: both rasterize correctly, but
cairosvg needs a system libcairo while resvg-py is a pure Rust binary
wheel. Same rule as bd-view's uv-cached deps — no global install, no
system prerequisite.

Run it through ``make screenshots`` rather than directly.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import resvg_py
from rich.console import Console
from rich.terminal_theme import TerminalTheme
from rich.text import Text

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "img"

# GitHub Dark. Chosen for visibility rather than fidelity to any one
# maintainer's terminal: the three hues bd-log uses (red/green/blue) stay
# well separated against a near-black ground, and the image sits naturally
# in a README viewed on github.com.
_PALETTE = [
    "#484f58", "#ff7b72", "#3fb950", "#d29922",
    "#58a6ff", "#bc8cff", "#39c5cf", "#b1bac4",
]


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _theme() -> TerminalTheme:
    shades = [_rgb(c) for c in _PALETTE]
    return TerminalTheme(_rgb("#0d1117"), _rgb("#c9d1d9"), shades, shades)


# Each entry is (filename stem, typed, command).
#
# `typed` is what a reader should type, and it is drawn as a prompt line at
# the top of the image — without it the image shows output with no way to
# tell what produced it. It deliberately omits the capture scaffolding in
# `command`: --color=always and --no-pager only exist because we render
# through a pipe, and at a real terminal both are the default.
#
# The commands run against this repo's own beads, so regenerating produces
# a fresh diff every time — that is expected, see CLAUDE.md.
SHOTS = [
    (
        "bd-log",
        "bd-log --oneline -n 10",
        "./bd-log --oneline --legend=always --color=always -n 10 --no-pager",
    ),
    (
        "bd-log-live",
        "bd-log --oneline --open --no-deferred --no-blocked -n 8",
        "./bd-log --oneline --open --about=beads --no-deferred --no-blocked"
        " --color=always --legend=never -n 8 --no-pager",
    ),
    (
        "claude-session-list",
        "claude-session-list --oneline -n 8",
        # -n 8 keeps the image short, and keeps the STARTED column
        # monotonic: the default sort is last-activity, so further down the
        # list STARTED legitimately goes out of order and reads as a bug in
        # a static image.
        "./claude-session-list --oneline -n 8 --no-pager",
    ),
    (
        "bd-dolt-check",
        "bd-dolt-check",
        "./bd-dolt-check .",
    ),
    (
        # A bead whose notes are actually Markdown, so the image shows the
        # bullets, bold headings and status color that are this script's
        # entire reason to exist. Most beads here are plain prose, which
        # renders as a wall of text and demonstrates nothing.
        "bd-view",
        "bd-view beads-utils-5lw",
        "./bd-view beads-utils-5lw --no-pager",
    ),
]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def capture(command: str) -> str:
    """Run one command in the repo and return the ANSI it printed."""
    done = subprocess.run(
        command, shell=True, cwd=REPO, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    out = done.stdout.rstrip("\n")
    if not out:
        sys.exit(f"error: no output from: {command}")
    return out


def prompt_line(typed: str) -> str:
    """A shell prompt showing *typed*, in green-$ / bold-command ANSI."""
    return f"\x1b[32m$\x1b[0m \x1b[1m{typed}\x1b[0m\n"


def render(ansi: str, title: str, dest: Path) -> None:
    """Render captured ANSI to a PNG at *dest*."""
    # rich wraps to the console width, which would break entries mid-title,
    # so size the console to the widest line with its escapes stripped.
    width = max(len(ANSI_RE.sub("", line)) for line in ansi.split("\n")) + 2
    console = Console(
        record=True, width=width, force_terminal=True,
        file=open("/dev/null", "w", encoding="utf-8"),
    )
    console.print(Text.from_ansi(ansi))
    svg = console.export_svg(title=title, theme=_theme(), font_aspect_ratio=0.6)

    # rich embeds no font data — it points @font-face at a CDN that GitHub's
    # CSP blocks, leaving the viewer's own monospace to shift the columns and
    # tofu the legend glyphs. Drop the remote fetch and name fonts that carry
    # the glyphs locally; resvg then resolves them at rasterize time, so the
    # PNG is pixel-exact for every viewer.
    svg = re.sub(r"@font-face \{.*?\}", "", svg, flags=re.S)
    svg = svg.replace(
        "font-family: Fira Code, monospace",
        "font-family: Menlo, 'DejaVu Sans Mono', monospace",
    )

    dest.write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=2.0)))
    print(f"{dest.relative_to(REPO)}  ({width} cols, {dest.stat().st_size // 1024} KB)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stem, typed, command in SHOTS:
        body = prompt_line(typed) + capture(command)
        render(body, stem, OUT / f"{stem}.png")


if __name__ == "__main__":
    main()
