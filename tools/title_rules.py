#!/usr/bin/env python3
"""Link the bead-title rules into Claude Code's user rules, after asking.

`make install-claude` calls this once the skills and hooks are linked. The
rules file goes in as CLAUDE_HOME/rules/<name>.md, a directory Claude Code
loads into every session in every project. Unlike a skill (run on demand) or
a hook (inert until wired into settings.json), that changes every session the
moment it lands, so it is never done without a yes: on a terminal the user is
shown what it does and asked, and from a pipe it is linked only with
`--answer yes` (the Makefile's TITLE_RULES=yes).

    title_rules.py --source FILE --link PATH [--answer ask|yes|no] [--interactive]

`--interactive` asks even when stdin is not a terminal, which the tests use.
Exit status is 0 unless something that is not a symlink sits at PATH and the
answer was not `no`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def details(source: Path, link: Path) -> str:
    lines = len(source.read_text().splitlines())
    return (
        "\n"
        "Optional: bead-title rules for Claude\n"
        f"  beads-utils includes a {lines}-line set of rules for writing a bead's title.\n"
        "  The /review-titles skill checks existing titles against them. If you add\n"
        "  them to Claude Code's standing instructions, Claude also follows them\n"
        "  whenever it creates a bead, in any project.\n"
        f"  Adding them puts a link at {link}.\n"
        "  Claude Code reads that folder at the start of every session, in every\n"
        f"  project, so those {lines} lines are in every session from the next one on,\n"
        "  even in projects that do not use beads.\n"
        "  To remove them later: make uninstall-claude\n"
    )


def ask(prompt: str, inp=sys.stdin, out=sys.stdout) -> str:
    print(prompt, end="", file=out, flush=True)
    line = inp.readline()
    return line.strip().lower() if line else "n"


def confirm(source: Path, link: Path, inp=sys.stdin, out=sys.stdout) -> bool:
    """Show what linking does and ask; `?` prints the rules themselves."""
    print(details(source, link), end="", file=out)
    while True:
        answer = ask("Add the bead-title rules to every Claude Code session? [y/N, ? shows them] ", inp, out)
        if answer != "?":
            return answer == "y"
        print(source.read_text(), file=out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True, help="the rules file to link to")
    parser.add_argument("--link", type=Path, required=True, help="where the link goes")
    parser.add_argument("--answer", choices=["ask", "yes", "no"], default="ask",
                        help="ask on a terminal (default), or link / skip without asking")
    parser.add_argument("--interactive", action="store_true", help="ask even when stdin is not a terminal")
    args = parser.parse_args()
    source, link = args.source, args.link

    if link.is_symlink() and os.readlink(link) == str(source):
        print(f"Title rules already linked: {link}")
        return 0
    if args.answer == "no":   # before the refusal: a file of the user's own there is fine then
        print("Title rules not linked (TITLE_RULES=no).")
        return 0
    if link.exists() and not link.is_symlink():
        print(f"refusing to replace non-symlink: {link}")
        return 1
    if args.answer == "ask":
        if not (args.interactive or sys.stdin.isatty()):
            print("Title rules not linked: no terminal to ask on. "
                  "To link them, run 'make install-claude TITLE_RULES=yes'.")
            return 0
        if not confirm(source, link):
            print("Title rules not linked.")
            return 0

    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():   # someone else's link at that name: the yes covers replacing it
        link.unlink()
    link.symlink_to(source)
    print(f"Linked the title rules: {link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
