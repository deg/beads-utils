"""Keep completions/ in sync with the scripts' argparse definitions.

The two completion files transcribe every flag by hand — that is deliberate
(see CLAUDE.md: dynamic *candidates* go through `bd-complete`, but the flag
lists are static glue). Nothing enforced the transcription, and it had already
drifted: `claude-session-report` grew `--prompts` / `--replies` /
`--slash-commands` alongside their `--no-` twins, and neither shell file
learned about them.

Two classes of check:

* **Coverage** — the long options argparse defines, the zsh `_arguments`
  specs, and the bash flag lists are the same set, per command.
* **Shape** — a zsh option that takes a value must be spelled with a trailing
  `=` (long) or `+` (short). This is the beads-utils-dk6 defect as an
  assertion: `_arguments` matches the option name literally, so `--id[...]`
  accepts only `--id VALUE` and completes nothing for `--id=VALUE`, which is
  the form the scripts' own help text and this repo's docs use throughout.

The parser is obtained by intercepting `parse_args`, not by parsing `--help`:
the help epilogs are full of example command lines, and every flag mentioned
in one would otherwise register as a defined option.
"""
from __future__ import annotations

import argparse
import re
import sys

import pytest
from conftest import ROOT, load_script

# Commands that have completion entries. bd-complete is deliberately absent —
# it is the completion back end, not something a user types.
COMMANDS = [
    "bd-view",
    "bd-log",
    "bd-export-csv",
    "bd-dolt-check",
    "bd-dolt-diff",
    "claude-session-find",
    "claude-session-list",
    "claude-session-report",
]

ZSH_FILE = ROOT / "completions" / "beads-utils.zsh"
BASH_FILE = ROOT / "completions" / "beads-utils.bash"


# --- the scripts' own argparse definitions --------------------------------


class _StopParsing(Exception):
    """Raised from the patched parse_args to unwind out of main()."""


def script_options(script: str, monkeypatch) -> dict[str, bool]:
    """Map every option string of `script` to whether it takes a value.

    Runs the script's main() with parse_args patched to hand back the parser
    it was called on, so the answer comes from argparse itself rather than
    from rendered help text. Every script builds its parser as the first thing
    main() does, so nothing else runs.
    """
    module = load_script(script)
    captured: dict[str, argparse.ArgumentParser] = {}

    def fake_parse_args(self, *args, **kwargs):
        captured["parser"] = self
        raise _StopParsing

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", fake_parse_args)
    monkeypatch.setattr(sys, "argv", [script])
    with pytest.raises(_StopParsing):
        module.main()

    valueless = (
        argparse._StoreTrueAction,
        argparse._StoreFalseAction,
        argparse._HelpAction,
        argparse._VersionAction,
    )
    options: dict[str, bool] = {}
    for action in captured["parser"]._actions:
        takes_value = not isinstance(action, valueless) and action.nargs != 0
        for name in action.option_strings:
            options[name] = takes_value
    return options


# --- what the completion files declare ------------------------------------

# One `_arguments` spec, e.g. `'(--status --open)--status=[desc]:msg:action'`.
# The name is whatever sits immediately before the `[` description, so the
# leading exclusion list can't be mistaken for it.
_ZSH_SPEC = re.compile(r"(?<![\w-])(--?[A-Za-z0-9][-A-Za-z0-9]*)([+=]?)\[")
# The `{-h,--help}` brace form, which is only ever used for valueless flags.
_ZSH_BRACE = re.compile(r"\{(-[^}]*)\}")


def zsh_specs() -> dict[str, dict[str, str]]:
    """Per command, map each option name to its value marker (``''``/``+``/``=``).

    Splits the file on the dispatcher's `case` labels, so a spec is attributed
    to the command whose branch it appears in.
    """
    text = ZSH_FILE.read_text()
    body = text.split("_beads_dispatch() {", 1)[1]
    specs: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in body.splitlines():
        label = re.match(r"\s*([a-z][-a-z0-9]*)\)\s*$", line)
        if label and label.group(1) in COMMANDS:
            current = specs.setdefault(label.group(1), {})
            continue
        if current is None:
            continue
        for group in _ZSH_BRACE.findall(line):
            for name in group.split(","):
                current[name.strip()] = ""
        for name, marker in _ZSH_SPEC.findall(line):
            current[name] = marker
    return specs


# `__beads_flags "..."` carries the flag list, possibly over continued lines.
_BASH_FLAGS = re.compile(r'__beads_flags\s+"(.*?)"', re.DOTALL)


def bash_flags() -> dict[str, set[str]]:
    """Per command, the set of flags its bash completer offers."""
    text = BASH_FILE.read_text()
    flags: dict[str, set[str]] = {}
    for command in COMMANDS:
        function = "_beads_" + command.replace("-", "_")
        start = text.index(f"{function}() {{")
        end = text.index("\n}\n", start)
        names: set[str] = set()
        for block in _BASH_FLAGS.findall(text[start:end]):
            names.update(block.replace("\\\n", " ").split())
        flags[command] = names
    return flags


# --- the checks -----------------------------------------------------------


def test_command_list_matches_registrations():
    """COMMANDS covers exactly the commands both files register.

    That list is hand-maintained, so a script wired up with `compdef` /
    `complete -F` but left out of it would go unchecked by everything below —
    the same drift this module exists to catch, one level up. All three
    registration points (zsh's `#compdef` header and its `compdef` call, plus
    bash's `complete -F` lines) have to agree with it.
    """
    zsh_text = ZSH_FILE.read_text()
    header = set(zsh_text.splitlines()[0].removeprefix("#compdef").split())
    compdef = zsh_text.split("\ncompdef _beads_dispatch", 1)[1]
    registered = set(compdef.replace("\\\n", " ").split())
    bash = set(re.findall(r"^complete -F \S+ (\S+)$", BASH_FILE.read_text(), re.M))

    assert header == set(COMMANDS), "zsh #compdef header"
    assert registered == set(COMMANDS), "zsh compdef call"
    assert bash == set(COMMANDS), "bash complete -F lines"


@pytest.mark.parametrize("command", COMMANDS)
def test_zsh_covers_every_option(command, monkeypatch):
    """Every option argparse defines is in the zsh specs, and vice versa."""
    defined = set(script_options(command, monkeypatch))
    completed = set(zsh_specs()[command])
    assert completed == defined, (
        f"completions/beads-utils.zsh is out of sync with {command}: "
        f"missing {sorted(defined - completed)}, stale {sorted(completed - defined)}"
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_bash_covers_every_option(command, monkeypatch):
    """Same for the bash flag lists, which are a separate transcription."""
    defined = set(script_options(command, monkeypatch))
    completed = bash_flags()[command]
    assert completed == defined, (
        f"completions/beads-utils.bash is out of sync with {command}: "
        f"missing {sorted(defined - completed)}, stale {sorted(completed - defined)}"
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_zsh_marks_value_taking_options(command, monkeypatch):
    """Value-taking options carry the marker that makes `--opt=value` complete.

    Long options need `=`, short options `+`. Without the marker `_arguments`
    only recognizes the space-separated form; `--id=bea` matches no spec at
    all and falls through to the positional, which is what beads-utils-dk6
    reported as "completion does nothing".
    """
    options = script_options(command, monkeypatch)
    markers = zsh_specs()[command]
    wrong = {
        name: markers.get(name)
        for name, takes_value in options.items()
        if takes_value and markers.get(name) != ("=" if name.startswith("--") else "+")
    }
    assert not wrong, (
        f"{command}: these options take a value but their zsh spec lacks the "
        f"marker that lets the joined form complete: {sorted(wrong)}"
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_zsh_does_not_mark_valueless_flags(command, monkeypatch):
    """The converse: a bare flag must not claim to take a value.

    `--open=[...]` would make zsh sit waiting for an argument that argparse
    would reject.
    """
    options = script_options(command, monkeypatch)
    markers = zsh_specs()[command]
    wrong = [
        name
        for name, takes_value in options.items()
        if not takes_value and markers.get(name)
    ]
    assert not wrong, f"{command}: valueless flags marked as taking one: {sorted(wrong)}"
