#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["rich", "resvg-py"]
# ///
"""Render each script's real terminal output to a PNG for the README.

Not a screen capture. Each command is run with ``--color=always`` into a
pipe, and the ANSI it emits is rendered deterministically: rich turns it
into an SVG, which resvg rasterizes. Nothing depends on anyone's terminal
settings, and every viewer sees the same finished raster.

Layout is machine-independent (rich lays out from font_aspect_ratio, not from
font metrics), but the pixels are not: the font stack below prefers Menlo,
which ships only on macOS, so a Linux run rasterizes with DejaVu Sans Mono.
Same columns, different glyph shapes — regenerate on one machine or expect a
cosmetic diff.

``resvg-py`` rather than ``cairosvg``: both rasterize correctly, but
cairosvg needs a system libcairo while resvg-py is a pure Rust binary
wheel. Same rule as bd-view's uv-cached deps — no global install, no
system prerequisite.

Run it through ``make screenshots`` rather than directly.
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

import resvg_py
from rich.cells import cell_len
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
        "bd-log --oneline --open --about=beads --no-deferred --no-blocked"
        " --legend=never -n 8",
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
    """Run one command in the repo and return the ANSI it printed.

    stderr is kept rather than discarded so a failure names its own cause.
    The day a bead in SHOTS is renamed, bd-view writes its complaint there and
    prints nothing to stdout, and "no output from ..." alone would leave you
    guessing. A blanket check=True would be wrong: bd-dolt-check exits 1 by
    design when the repo is unpushed, which is the state its shot depicts.
    """
    done = subprocess.run(
        command, shell=True, cwd=REPO, text=True, errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    out = done.stdout.rstrip("\n")
    if not out:
        why = (done.stderr or "").strip() or f"exit {done.returncode}, no stderr"
        sys.exit(f"error: no output from: {command}\n  {why}")
    return out


# Arguments that exist only because we capture through a pipe, and that a real
# terminal supplies anyway: color is automatic on a tty, so is paging, so is
# the legend, and the project path defaults to the current directory. These may
# be absent from the prompt line. Anything else changes the output, so hiding
# it would make the prompt a lie about what produced the image.
SCAFFOLDING = frozenset({"--color=always", "--no-pager", "--legend=always", "."})


def check_typed(typed: str, command: str) -> None:
    """Fail unless the prompt line is the command minus capture scaffolding.

    Compares whole tokens, not substrings: `-n` is a substring of `--no-pager`,
    so a looser check silently passes. Guards a drift that already happened —
    bd-log-live's prompt omitted --about=beads, so anyone typing it would have
    got memory events the image does not show.
    """
    expected = [
        word for word in command.replace("./", "", 1).split()
        if word not in SCAFFOLDING
    ]
    if typed.split() != expected:
        sys.exit(
            f"error: prompt line does not match the command\n"
            f"  shown: {typed}\n"
            f"  runs:  {' '.join(expected)}"
        )


def prompt_line(typed: str) -> str:
    """A shell prompt showing *typed*, in green-$ / bold-command ANSI."""
    return f"\x1b[32m$\x1b[0m \x1b[1m{typed}\x1b[0m\n"


def _require_change(after: str, before: str, what: str) -> str:
    """Return *after*, or exit if the substitution matched nothing."""
    if after == before:
        sys.exit(f"error: no {what} found in rich's SVG — its template changed")
    return after


def render(ansi: str, title: str, dest: Path) -> None:
    """Render captured ANSI to a PNG at *dest*."""
    # rich wraps to the console width, which would break entries mid-title, so
    # size the console to the widest line with its escapes stripped. cell_len,
    # not len: they agree on everything captured today, but the first
    # double-width glyph or tab would make len under-count and rich would wrap
    # exactly what this line exists to prevent.
    width = max(cell_len(ANSI_RE.sub("", line)) for line in ansi.split("\n")) + 2
    # Console needs somewhere to write; we only ever want the recording, so
    # give it an in-memory sink rather than leaking a /dev/null handle.
    console = Console(
        record=True, width=width, force_terminal=True, file=io.StringIO(),
    )
    console.print(Text.from_ansi(ansi))
    svg = console.export_svg(title=title, theme=_theme(), font_aspect_ratio=0.6)

    # rich points @font-face at a CDN. resvg does not fetch remote fonts, so
    # left alone it would fall back to whatever it finds and tofu the legend
    # glyphs. Drop the remote fetch and name fonts that carry them locally.
    #
    # (The CSP argument belongs to the PNG-over-SVG decision, not here: a
    # viewer receives a finished raster and fetches no fonts at all.)
    #
    # Both rewrites are string surgery on a template this script does not own,
    # and `re.sub`/`str.replace` return the input unchanged when they match
    # nothing — so a rich release that restyles the template would silently
    # degrade every PNG. Fail loudly instead; `rich` is unpinned by design,
    # matching bd-view.
    svg = _require_change(
        re.sub(r"@font-face \{.*?\}", "", svg, flags=re.S), svg, "@font-face block",
    )
    svg = _require_change(
        svg.replace(
            "font-family: Fira Code, monospace",
            "font-family: Menlo, 'DejaVu Sans Mono', monospace",
        ),
        svg,
        "font-family declaration",
    )

    dest.write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=2.0)))
    print(f"{dest.relative_to(REPO)}  ({width} cols, {dest.stat().st_size // 1024} KB)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stem, typed, command in SHOTS:
        check_typed(typed, command)
        body = prompt_line(typed) + capture(command)
        render(body, stem, OUT / f"{stem}.png")


if __name__ == "__main__":
    main()
