"""Tests for claude-session-find."""
from __future__ import annotations

import json

import pytest

from pathlib import Path

import claudeutils
from conftest import assistant_entry, load_script, user_entry, write_session

find = load_script("claude-session-find")


# --- extract_text ---------------------------------------------------------


def test_extract_text_returns_a_bare_string_unchanged():
    assert find.extract_text("hello", include_tool_content=False) == "hello"


def test_extract_text_joins_text_blocks():
    content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert find.extract_text(content, include_tool_content=False) == "a\nb"


def test_extract_text_ignores_tool_content_by_default():
    """The default search is human-typed prose only."""
    content = [
        {"type": "text", "text": "prose"},
        {"type": "thinking", "thinking": "secret"},
        {"type": "tool_use", "input": {"command": "ls"}},
        {"type": "tool_result", "content": "output"},
    ]
    assert find.extract_text(content, include_tool_content=False) == "prose"


def test_extract_text_includes_thinking_when_searching_everything():
    content = [{"type": "thinking", "thinking": "the reasoning"}]
    assert find.extract_text(content, include_tool_content=True) == "the reasoning"


def test_extract_text_serializes_tool_input_as_json():
    content = [{"type": "tool_use", "input": {"command": "bd list"}}]
    out = find.extract_text(content, include_tool_content=True)
    assert json.loads(out) == {"command": "bd list"}


def test_extract_text_keeps_non_ascii_readable_in_tool_input():
    """ensure_ascii=False, so a search for the literal character still matches."""
    content = [{"type": "tool_use", "input": {"note": "café"}}]
    assert "café" in find.extract_text(content, include_tool_content=True)


def test_extract_text_includes_a_string_tool_result():
    content = [{"type": "tool_result", "content": "the output"}]
    assert find.extract_text(content, include_tool_content=True) == "the output"


def test_extract_text_flattens_a_block_list_tool_result():
    content = [{"type": "tool_result", "content": [
        {"type": "text", "text": "one"}, {"type": "image"}, {"type": "text", "text": "two"},
    ]}]
    assert find.extract_text(content, include_tool_content=True) == "one\ntwo"


def test_extract_text_skips_unserializable_tool_input():
    content = [{"type": "tool_use", "input": {"bad": {1, 2}}}]
    assert find.extract_text(content, include_tool_content=True) == ""


@pytest.mark.parametrize("content", [None, 42, {}, [], ["raw"], [{"no": "type"}]])
def test_extract_text_tolerates_unexpected_shapes(content):
    assert find.extract_text(content, include_tool_content=True) == ""


def test_extract_text_ignores_a_non_string_text_field():
    assert find.extract_text([{"type": "text", "text": 42}], False) == ""


# --- find_snippets --------------------------------------------------------


def test_find_snippets_returns_the_match_with_surrounding_context():
    text = "the quick brown fox jumps over the lazy dog"
    (snip,) = find.find_snippets(text, "fox", 3, max_snips=1, context=5)
    assert "fox" in snip
    assert snip.startswith("…") and snip.endswith("…")


def test_find_snippets_omits_the_ellipsis_at_a_boundary():
    (snip,) = find.find_snippets("fox tail", "fox", 3, max_snips=1, context=10)
    assert not snip.startswith("…")
    assert not snip.endswith("…")


def test_find_snippets_collapses_whitespace_so_a_snippet_stays_on_one_line():
    text = "before\n\n   needle   \n\nafter"
    (snip,) = find.find_snippets(text, "needle", 6, max_snips=1, context=20)
    assert "\n" not in snip
    assert "needle" in snip


def test_find_snippets_stops_at_the_requested_maximum():
    text = "needle " * 10
    snips = find.find_snippets(text, "needle", 6, max_snips=3, context=2)
    assert len(snips) == 3


def test_find_snippets_does_not_return_overlapping_matches():
    snips = find.find_snippets("aaaa", "aa", 2, max_snips=5, context=0)
    assert len(snips) == 2


def test_find_snippets_returns_nothing_when_the_needle_is_absent():
    assert find.find_snippets("hello", "zzz", 3, max_snips=3, context=5) == []


# --- iter_session_text ----------------------------------------------------


def test_iter_session_text_reads_only_user_entries_by_default(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        user_entry("a question"),
        assistant_entry("an answer"),
    ])
    assert list(find.iter_session_text(path, search_all=False)) == ["a question"]


def test_iter_session_text_includes_assistant_entries_when_searching_all(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        user_entry("a question"),
        assistant_entry("an answer"),
    ])
    assert list(find.iter_session_text(path, search_all=True)) == ["a question", "an answer"]


def test_iter_session_text_skips_entries_that_are_not_conversation(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "summary", "message": {"content": "ignore"}},
        user_entry("keep"),
    ])
    assert list(find.iter_session_text(path, search_all=True)) == ["keep"]


def test_iter_session_text_skips_malformed_lines(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{ broken\n' + json.dumps(user_entry("keep")) + "\n")
    assert list(find.iter_session_text(path, search_all=False)) == ["keep"]


def test_iter_session_text_skips_entries_with_no_message(tmp_path):
    path = write_session(tmp_path / "p", "u1", [{"type": "user"}, user_entry("keep")])
    assert list(find.iter_session_text(path, search_all=False)) == ["keep"]


def test_iter_session_text_warns_and_yields_nothing_for_an_unreadable_file(
        tmp_path, capsys):
    assert list(find.iter_session_text(tmp_path / "absent.jsonl", False)) == []
    assert "could not open" in capsys.readouterr().err


# --- scan_session ---------------------------------------------------------


def test_scan_session_counts_every_hit_and_returns_snippets(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        user_entry("pager here and pager again"),
        user_entry("one more pager"),
    ])
    total, snips = find.scan_session(path, "pager", search_all=False,
                                     max_snips=3, context=5)
    assert total == 3
    assert len(snips) == 3


def test_scan_session_counts_beyond_the_snippet_cap(tmp_path):
    """The count is the full total; only the shown snippets are capped."""
    path = write_session(tmp_path / "p", "u1", [user_entry("x " * 20 + "hit " * 10)])
    total, snips = find.scan_session(path, "hit", search_all=False,
                                     max_snips=2, context=3)
    assert total == 10
    assert len(snips) == 2


def test_scan_session_is_case_insensitive(tmp_path):
    path = write_session(tmp_path / "p", "u1", [user_entry("PAGER and Pager")])
    total, _ = find.scan_session(path, "pager", False, 3, 5)
    assert total == 2


def test_scan_session_reports_no_hits(tmp_path):
    path = write_session(tmp_path / "p", "u1", [user_entry("nothing here")])
    assert find.scan_session(path, "zzz", False, 3, 5) == (0, [])


def test_scan_session_does_not_see_tool_content_by_default(tmp_path):
    path = write_session(tmp_path / "p", "u1", [{
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "input": {"cmd": "needle"}}]},
    }])
    assert find.scan_session(path, "needle", False, 3, 5)[0] == 0
    assert find.scan_session(path, "needle", True, 3, 5)[0] == 1


# --- Delegation to claudeutils --------------------------------------------
#
# claude-session-find used to carry its own copies of mangle_cwd, first_cwd,
# find_project_dir and project_label. They drifted -- only the claudeutils
# copy ever got the missing-directory guard -- which was beads-utils-8ju.
#
# The drift was latent, not user-visible: main() checked the same directory
# before calling find_project_dir, so the CLI exited cleanly and only a direct
# caller could have seen the raise. The copies are gone now, so what needs
# testing here is that the delegation is real; the behavior itself is covered
# once, in test_claudeutils.py.


@pytest.mark.parametrize("name", ["find_project_dir", "project_label"])
def test_the_helpers_are_claudeutils_own_functions(name):
    """Identity, not equivalence.

    Two independent implementations that merely agree today are exactly what
    produced 8ju. Asserting the same function object means they cannot drift
    apart again without this failing.
    """
    assert getattr(find, name) is getattr(claudeutils, name)


def test_no_local_copy_of_the_helpers_survives():
    """A re-introduced local copy is the regression, so name them explicitly.

    mangle_cwd and first_cwd were only ever used by find_project_dir, so they
    should have no module-level presence here at all.
    """
    source = Path(find.__file__).read_text()
    for helper in ("mangle_cwd", "first_cwd", "find_project_dir", "project_label"):
        assert f"def {helper}" not in source


def test_the_projects_path_is_read_through_the_module():
    """One binding, so patching claudeutils reaches every reader.

    A `from claudeutils import CLAUDE_PROJECTS` here would bind a second name
    to the same path while the imported functions kept reading claudeutils'
    global -- patch one, miss the other, silently. Verified by behavior:
    redirecting claudeutils alone must change what this script resolves.
    """
    assert not hasattr(find, "CLAUDE_PROJECTS")
    assert "claudeutils.CLAUDE_PROJECTS" in Path(find.__file__).read_text()


def test_find_project_dir_now_returns_none_on_a_missing_projects_dir(
        tmp_path, monkeypatch):
    """The 8ju fix: the function now honors its own docstring ("or None if
    missing") instead of raising. Patching claudeutils, not `find`, is what
    reaches the delegated function -- and that it must be is the point."""
    monkeypatch.setattr(claudeutils, "CLAUDE_PROJECTS", tmp_path / "absent")
    assert find.find_project_dir(tmp_path / "myproj") is None


def test_find_project_dir_locates_the_mangled_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(claudeutils, "CLAUDE_PROJECTS", tmp_path)
    cwd = tmp_path / "myproj"
    target = tmp_path / claudeutils.mangle_cwd(cwd)
    target.mkdir()
    assert find.find_project_dir(cwd) == target


def test_project_label_still_reads_a_label_from_a_session(tmp_path):
    """The delegated project_label takes an optional `cwd` the old copy did
    not, but defaulted it produces identical output -- so the one call site in
    this script needed no change."""
    path = write_session(tmp_path / "p", "u1", [{"type": "user", "cwd": "/a/beads-utils"}])
    assert find.project_label(path) == "beads-utils"


# --- format_mtime ---------------------------------------------------------


def test_format_mtime_renders_to_the_minute():
    from datetime import datetime, timezone

    stamp = datetime(2026, 5, 27, 9, 11, tzinfo=timezone.utc).timestamp()
    assert find.format_mtime(stamp) == "2026-05-27 09:11"
