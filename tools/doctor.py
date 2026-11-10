#!/usr/bin/env python3
"""Report the tools the scripts and hooks need, and offer to install the missing ones.

`make doctor`, `make install` and `make install-claude` call this. It never
installs anything without a `y` at a prompt, and it prompts only on a terminal
(`--offer`) unless told to read answers from stdin regardless (`--interactive`,
which the tests use). `--run PREFIX` puts a command in front of every install
command, so a test can pass `--run echo` and see what would have run.

    doctor.py [--for install|install-claude|all] [--offer|--interactive] [--run PREFIX]

Exit status is 0 except for `--for install-claude` with jq still missing at
the end, since the hooks cannot run without it: the target then stops before
linking anything.
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tool:
    name: str
    purpose: str                      # one line: what it unlocks
    more: str                         # a few lines for `?`
    brew: str                         # Homebrew package, or "" if none
    apt: str                          # Debian/Ubuntu package, or ""
    url: str = ""                     # where to get it when no package manager fits
    needed_by: frozenset[str] = field(default_factory=frozenset)   # targets that ask about it
    optional: bool = False
    alternates: tuple[str, ...] = ()  # other names that satisfy it (gtimeout for timeout)


TOOLS = (
    Tool("python3", "every script",
         "The scripts are Python 3 files; 3.10 or later.",
         brew="python", apt="python3", needed_by=frozenset({"install"})),
    Tool("git", "bd-verify-backup, claude-memory-setup and the memory hooks",
         "The memories repo is plain git; bd-verify-backup reads git state.",
         brew="git", apt="git", needed_by=frozenset({"install", "install-claude"})),
    Tool("bd", "bd-log, bd-view, bd-find-live, bd-export-csv, and the skills",
         "The beads issue tracker. The skills drive it; four scripts read beads through it.",
         brew="beads", apt="", url="https://github.com/gastownhall/beads",
         needed_by=frozenset({"install"})),
    Tool("jq", "the hooks; install-claude and claude-memory-setup refuse without it",
         "All four hooks parse the JSON Claude Code hands them with jq. Without it no hook runs.",
         brew="jq", apt="jq", needed_by=frozenset({"install-claude"})),
    Tool("uv", "bd-view (rich in a per-script venv) and make test",
         "bd-view's shebang is `uv run --script`, which resolves rich into a cached venv; "
         "the test suite runs through uv too.",
         brew="uv", apt="", url="https://docs.astral.sh/uv/", needed_by=frozenset({"install"})),
    Tool("dolt", "full answers from bd-dolt-check, bd-dolt-diff and bd-verify-backup; bd-log's memory history",
         "Beads stores its data in Dolt. Without the CLI, bd-dolt-check degrades, bd-verify-backup "
         "reports the beads as UNVERIFIABLE, and bd-log shows no memory events.",
         brew="dolt", apt="", url="https://github.com/dolthub/dolt", needed_by=frozenset({"install"}),
         optional=True),
    Tool("timeout", "lets claim-guard name the beads in progress",
         "claim-guard runs `bd list` under a 3-second timeout so a Dolt lock cannot stall a claim; "
         "without GNU timeout it skips that clause and still guards the claim.",
         brew="coreutils", apt="coreutils", needed_by=frozenset({"install-claude"}), optional=True,
         alternates=("gtimeout",)),
)


def present(tool: Tool) -> bool:
    return any(shutil.which(n) for n in (tool.name, *tool.alternates))


def package_manager() -> str | None:
    if shutil.which("brew"):
        return "brew"
    if shutil.which("apt-get"):
        return "apt"
    return None


def install_command(tool: Tool, manager: str | None) -> str | None:
    """The command that would install `tool` here, or None if there is no package for it."""
    if manager == "brew" and tool.brew:
        return f"brew install {tool.brew}"
    if manager == "apt" and tool.apt:
        return f"sudo apt-get install -y {tool.apt}"
    return None


def hint(tool: Tool, manager: str | None) -> str:
    cmd = install_command(tool, manager)
    if cmd:
        return f"install: {cmd}"
    return f"see {tool.url}" if tool.url else "no package known for this platform"


def report(tools, manager: str | None, out=sys.stdout) -> list[Tool]:
    """Print one line per tool and return the missing ones."""
    missing: list[Tool] = []
    for label, group in (("Required:", [t for t in tools if not t.optional]),
                         ("Optional:", [t for t in tools if t.optional])):
        if not group:
            continue
        print(label, file=out)
        for tool in group:
            if present(tool):
                print(f"  [ok]       {tool.name:<8} {tool.purpose}", file=out)
            else:
                print(f"  [missing]  {tool.name:<8} {tool.purpose} ({hint(tool, manager)})", file=out)
                missing.append(tool)
    return missing


def ask(prompt: str, inp=sys.stdin, out=sys.stdout) -> str:
    print(prompt, end="", file=out, flush=True)
    line = inp.readline()
    return line.strip().lower() if line else "n"


def offer(missing, manager: str | None, run_prefix: str, inp=sys.stdin, out=sys.stdout) -> list[Tool]:
    """Ask about each missing tool; return those still missing afterwards.

    `?` prints the longer explanation and asks again. An install command runs
    only after a `y`, through `run_prefix` when one is given (the tests pass
    `echo`, so nothing is installed and the command is visible).
    """
    still: list[Tool] = []
    for tool in missing:
        cmd = install_command(tool, manager)
        if not cmd:
            print(f"  {tool.name}: no package known here; {hint(tool, manager)}", file=out)
            still.append(tool)
            continue
        while True:
            answer = ask(f"Install {tool.name} ({cmd})? [y/N/?] ", inp, out)
            if answer == "?":
                print(f"  {tool.more}", file=out)
                continue
            break
        if answer != "y":
            still.append(tool)
            continue
        full = f"{run_prefix} {cmd}".strip() if run_prefix else cmd
        print(f"  running: {full}", file=out)
        try:
            rc = subprocess.call(shlex.split(full))   # inherits the terminal: sudo may prompt
        except OSError as exc:
            print(f"  {tool.name}: could not run {full.split()[0]}: {exc.strerror}", file=out)
            still.append(tool)
            continue
        if rc != 0 or (not run_prefix and not present(tool)):
            print(f"  {tool.name}: install did not succeed (exit {rc})", file=out)
            still.append(tool)
    return still


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--for", dest="target", choices=["install", "install-claude", "all"], default="all",
                        help="which target's tools to check (default: all)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offer", action="store_true", help="offer to install missing tools, if stdin is a terminal")
    mode.add_argument("--interactive", action="store_true", help="offer regardless, reading answers from stdin")
    parser.add_argument("--run", metavar="PREFIX", default="", help="prefix every install command with PREFIX")
    args = parser.parse_args()

    tools = [t for t in TOOLS if args.target == "all" or args.target in t.needed_by]
    manager = package_manager()
    missing = report(tools, manager)
    if missing and (args.interactive or (args.offer and sys.stdin.isatty())):
        missing = offer(missing, manager, args.run)

    if not missing:
        print("All present.")
    else:
        names = ", ".join(t.name for t in missing)
        print(f"{len(missing)} missing ({names}); nothing was installed without a yes.")
    if args.target == "install-claude" and any(t.name == "jq" for t in missing):
        print("error: the hooks need jq; nothing was linked", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
