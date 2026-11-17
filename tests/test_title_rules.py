"""Tests for tools/title_rules.py, the prompt behind install-claude's title rules.

The property that matters: the rules land in CLAUDE_HOME/rules, where they
change every session, only after a yes. `--interactive` makes the script ask
on a pipe, so each answer can be fed on stdin. The Makefile side (TITLE_RULES,
the refusal before linking, uninstall) is in test_makefile.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from conftest import ROOT

SCRIPT = ROOT / "tools" / "title_rules.py"


def run(tmp_path: Path, *args: str, answers: str = "") -> tuple[subprocess.CompletedProcess, Path, Path]:
    source = tmp_path / "title-rules.md"
    if not source.exists():
        source.write_text("# Rules\n\n- RULE-TEXT-MARKER\n")
    link = tmp_path / "home" / "rules" / "bead-titles.md"
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(source), "--link", str(link), *args],
        input=answers, text=True, capture_output=True, check=False,
    )
    return done, source, link


def test_yes_links_after_showing_what_it_does(tmp_path):
    done, source, link = run(tmp_path, "--interactive", answers="y\n")
    assert done.returncode == 0
    assert "at the start of every session, in every" in done.stdout
    assert "3-line set of rules" in done.stdout
    assert "make uninstall-claude" in done.stdout
    assert Path(os.readlink(link)) == source


def test_anything_but_yes_links_nothing(tmp_path):
    for answer in ("n\n", "\n", "yes please\n", ""):   # "" is end of input
        done, _, link = run(tmp_path, "--interactive", answers=answer)
        assert done.returncode == 0
        assert "Title rules not linked." in done.stdout
        assert not link.parent.exists()


def test_question_mark_shows_the_rules_and_asks_again(tmp_path):
    done, _, link = run(tmp_path, "--interactive", answers="?\ny\n")
    assert "RULE-TEXT-MARKER" in done.stdout
    assert done.stdout.count("[y/N, ? shows them]") == 2
    assert link.is_symlink()


def test_a_pipe_is_never_asked(tmp_path):
    done, _, link = run(tmp_path, answers="y\n")
    assert "no terminal to ask on" in done.stdout
    assert "[y/N, ? shows them]" not in done.stdout
    assert not link.parent.exists()


def test_answer_yes_links_without_asking(tmp_path):
    done, source, link = run(tmp_path, "--answer", "yes")
    assert "[y/N, ? shows them]" not in done.stdout
    assert Path(os.readlink(link)) == source


def test_answer_no_skips_without_asking(tmp_path):
    done, _, link = run(tmp_path, "--answer", "no", "--interactive", answers="y\n")
    assert "[y/N, ? shows them]" not in done.stdout
    assert not link.parent.exists()


def test_already_linked_is_left_alone_and_not_asked(tmp_path):
    run(tmp_path, "--answer", "yes")
    done, source, link = run(tmp_path, "--interactive", answers="n\n")
    assert "Title rules already linked" in done.stdout
    assert "[y/N, ? shows them]" not in done.stdout
    assert Path(os.readlink(link)) == source


def test_someone_elses_link_is_replaced_only_on_yes(tmp_path):
    link = tmp_path / "home" / "rules" / "bead-titles.md"
    link.parent.mkdir(parents=True)
    link.symlink_to("/elsewhere/rules.md")
    run(tmp_path, "--interactive", answers="n\n")
    assert os.readlink(link) == "/elsewhere/rules.md"
    _, source, _ = run(tmp_path, "--interactive", answers="y\n")
    assert Path(os.readlink(link)) == source


def test_a_real_file_is_refused(tmp_path):
    link = tmp_path / "home" / "rules" / "bead-titles.md"
    link.parent.mkdir(parents=True)
    link.write_text("precious\n")
    done, _, _ = run(tmp_path, "--answer", "yes")
    assert done.returncode == 1
    assert "refusing to replace non-symlink" in done.stdout
    assert link.read_text() == "precious\n"
