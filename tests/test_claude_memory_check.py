"""Tests for claude-memory-check, the linter for Claude Code memory stores.

The line it must hold is between ERROR and pending: a link that was meant to
resolve and does not is an error, a link to a memory not written yet is
permitted by the memory format. A checker that failed on the second kind would
be one nobody runs, and a checker that passed the first kind would be the rot
this exists to catch.
"""
from __future__ import annotations

import pytest

from conftest import load_script

cmc = load_script("claude-memory-check")


def memory(mem_dir, filename, name, body=""):
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / filename).write_text(f"---\nname: {name}\n---\n\n{body}\n")


def index(mem_dir, *filenames):
    (mem_dir / "MEMORY.md").write_text(
        "".join(f"- [{f}]({f}) — hook\n" for f in filenames)
    )


# --- check -----------------------------------------------------------------


def test_a_resolving_link_is_fine(tmp_path):
    memory(tmp_path, "a.md", "a", "see [[b]]")
    memory(tmp_path, "b.md", "b")
    assert cmc.check(tmp_path) == ([], [])


def test_a_hyphen_underscore_slip_is_an_error_with_the_fix(tmp_path):
    memory(tmp_path, "a.md", "a", "see [[two_words]]")
    memory(tmp_path, "two-words.md", "two-words")
    errors, pending = cmc.check(tmp_path)
    assert errors == ["a.md: [[two_words]] is broken -- did you mean [[two-words]]?"]
    assert pending == []


def test_a_link_matching_a_filename_stem_is_meant_to_resolve(tmp_path):
    """The file is named after the slug it should carry; the slug drifted."""
    memory(tmp_path, "old-name.md", "new-name")
    memory(tmp_path, "a.md", "a", "see [[old-name]]")
    errors, _ = cmc.check(tmp_path)
    assert errors == ["a.md: [[old-name]] is broken -- did you mean [[new-name]]?"]


def test_a_link_to_nothing_is_pending_not_an_error(tmp_path):
    memory(tmp_path, "a.md", "a", "see [[not-written-yet]]")
    errors, pending = cmc.check(tmp_path)
    assert errors == []
    assert pending == ["a.md: [[not-written-yet]] has no memory yet"]


def test_a_non_kebab_slug_is_an_error(tmp_path):
    memory(tmp_path, "a.md", "Not_Kebab")
    errors, _ = cmc.check(tmp_path)
    assert errors == ["a.md: name `Not_Kebab` is not kebab-case"]


def test_a_missing_name_is_an_error(tmp_path):
    (tmp_path / "a.md").write_text("no frontmatter at all\n")
    errors, _ = cmc.check(tmp_path)
    assert errors == ["a.md: no `name:` in frontmatter"]


def test_two_memories_claiming_one_slug_is_an_error(tmp_path):
    memory(tmp_path, "a.md", "same")
    memory(tmp_path, "b.md", "same")
    errors, _ = cmc.check(tmp_path)
    assert errors == ["b.md: name `same` duplicates a.md"]


def test_the_index_must_match_the_directory_both_ways(tmp_path):
    memory(tmp_path, "listed.md", "listed")
    memory(tmp_path, "unlisted.md", "unlisted")
    index(tmp_path, "listed.md", "gone.md")
    errors, _ = cmc.check(tmp_path)
    assert errors == [
        "MEMORY.md: links to gone.md, which does not exist",
        "MEMORY.md: no index line for unlisted.md",
    ]


def test_an_empty_store_has_no_findings(tmp_path):
    assert cmc.check(tmp_path) == ([], [])
    index(tmp_path)
    assert cmc.check(tmp_path) == ([], [])


def test_an_emptied_store_still_has_its_index_checked(tmp_path):
    """Deleting the last memory but not its index line must not read as clean.

    A `return` on "no memory files" would skip the MEMORY.md check and print
    a clean bill for exactly the state that deletion leaves behind.
    """
    index(tmp_path, "gone.md")
    errors, _ = cmc.check(tmp_path)
    assert errors == ["MEMORY.md: links to gone.md, which does not exist"]


def test_a_name_in_the_body_is_not_the_slug(tmp_path):
    """Only the frontmatter names a memory; a `name:` line in the body does not.

    The body here quotes a frontmatter example at column 0, which is what a
    memory about the memory format itself contains.
    """
    (tmp_path / "a.md").write_text("---\ndescription: x\n---\n\nWrite it as:\nname: from-the-body\n")
    errors, _ = cmc.check(tmp_path)
    assert errors == ["a.md: no `name:` in frontmatter"]


def test_a_quoted_name_is_read_without_its_quotes(tmp_path):
    (tmp_path / "a.md").write_text('---\nname: "a-b"\n---\n')
    memory(tmp_path, "c.md", "c", "see [[a-b]]")
    assert cmc.check(tmp_path) == ([], [])


def test_a_byte_that_is_not_utf8_does_not_crash_the_run(tmp_path):
    memory(tmp_path, "a.md", "a")
    (tmp_path / "a.md").write_bytes((tmp_path / "a.md").read_bytes() + b"caf\xe9\n")
    assert cmc.check(tmp_path) == ([], [])


# --- default_dirs / main ---------------------------------------------------


def test_default_dirs_read_claudeutils_single_binding(claude_home):
    """Patching claudeutils.CLAUDE_PROJECTS must redirect the default scan."""
    memory(claude_home / "p1" / "memory", "a.md", "a")
    memory(claude_home / "p2" / "memory", "b.md", "b")
    (claude_home / "p3").mkdir()
    assert cmc.default_dirs() == [
        claude_home / "p1" / "memory", claude_home / "p2" / "memory",
    ]


def test_main_exits_1_on_an_error(tmp_path, monkeypatch, capsys):
    memory(tmp_path, "a.md", "a", "see [[b_c]]")
    memory(tmp_path, "b-c.md", "b-c")
    monkeypatch.setattr("sys.argv", ["claude-memory-check", str(tmp_path)])
    assert cmc.main() == 1
    out = capsys.readouterr().out
    assert "ERROR    a.md: [[b_c]] is broken" in out
    assert out.rstrip().endswith("1 broken link(s) or index problem(s).")


def test_main_exits_0_on_pending_only(tmp_path, monkeypatch, capsys):
    memory(tmp_path, "a.md", "a", "see [[later]]")
    monkeypatch.setattr("sys.argv", ["claude-memory-check", str(tmp_path)])
    assert cmc.main() == 0
    out = capsys.readouterr().out
    assert "pending  a.md: [[later]] has no memory yet" in out
    assert out.rstrip().endswith("No broken memory links.")


def test_main_refuses_a_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["claude-memory-check", str(tmp_path / "nope")])
    with pytest.raises(SystemExit) as excinfo:
        cmc.main()
    assert "no such directory" in str(excinfo.value.code)


def test_main_scans_every_store_by_default(claude_home, monkeypatch, capsys):
    memory(claude_home / "p1" / "memory", "a.md", "a", "see [[x_y]]")
    memory(claude_home / "p1" / "memory", "x-y.md", "x-y")
    memory(claude_home / "p2" / "memory", "b.md", "b")
    monkeypatch.setattr("sys.argv", ["claude-memory-check"])
    assert cmc.main() == 1
    out = capsys.readouterr().out
    assert str(claude_home / "p1" / "memory") in out
    assert str(claude_home / "p2" / "memory") not in out  # clean stores stay quiet
