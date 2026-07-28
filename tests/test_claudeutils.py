"""Tests for claudeutils.py — Claude Code session enumeration and resolution.

Everything here runs against synthetic JSONL trees under tmp_path, with
claudeutils.CLAUDE_PROJECTS monkeypatched by the `claude_home` fixture, so the
suite never reads the developer's real session history (and never varies with
it).
"""
from __future__ import annotations

import json
import os

import pytest

import claudeutils
from conftest import assistant_entry, user_entry, write_session


# --- mangle_cwd -----------------------------------------------------------


@pytest.mark.parametrize(
    "cwd,expected",
    [
        ("/Users/deg/Documents/degel", "-Users-deg-Documents-degel"),
        ("/a/b.c/d", "-a-b-c-d"),
        ("/", "-"),
        ("/x.y.z", "-x-y-z"),
    ],
)
def test_mangle_cwd_replaces_slashes_and_dots_with_dashes(cwd, expected, tmp_path):
    from pathlib import PurePosixPath

    assert claudeutils.mangle_cwd(PurePosixPath(cwd)) == expected


# --- first_cwd ------------------------------------------------------------


def test_first_cwd_returns_the_first_entry_carrying_one(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "summary"},
        {"type": "user", "cwd": "/work/one"},
        {"type": "user", "cwd": "/work/two"},
    ])
    assert claudeutils.first_cwd(path) == "/work/one"


def test_first_cwd_returns_none_when_no_entry_has_one(tmp_path):
    path = write_session(tmp_path / "p", "u1", [{"type": "user"}])
    assert claudeutils.first_cwd(path) is None


def test_first_cwd_skips_unparseable_lines(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{ broken\nnot json\n{"cwd": "/work/one"}\n')
    assert claudeutils.first_cwd(path) == "/work/one"


def test_first_cwd_returns_none_for_a_missing_file(tmp_path):
    assert claudeutils.first_cwd(tmp_path / "absent.jsonl") is None


# --- find_project_dir -----------------------------------------------------


def test_find_project_dir_uses_the_mangled_name_directly(claude_home, tmp_path):
    cwd = tmp_path / "myproj"
    target = claude_home / claudeutils.mangle_cwd(cwd)
    target.mkdir()
    assert claudeutils.find_project_dir(cwd) == target


def test_find_project_dir_falls_back_to_scanning_recorded_cwds(claude_home, tmp_path):
    """Belt and suspenders, in case Claude's encoding rules ever change."""
    cwd = tmp_path / "myproj"
    oddly_named = claude_home / "some-other-encoding"
    write_session(oddly_named, "u1", [{"type": "user", "cwd": str(cwd)}])
    assert claudeutils.find_project_dir(cwd) == oddly_named


def test_find_project_dir_returns_none_when_nothing_matches(claude_home, tmp_path):
    write_session(claude_home / "unrelated", "u1", [{"type": "user", "cwd": "/elsewhere"}])
    assert claudeutils.find_project_dir(tmp_path / "myproj") is None


def test_find_project_dir_returns_none_without_a_projects_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(claudeutils, "CLAUDE_PROJECTS", tmp_path / "absent")
    assert claudeutils.find_project_dir(tmp_path / "myproj") is None


# --- project_label --------------------------------------------------------


def test_project_label_uses_the_basename_of_the_recorded_cwd(tmp_path):
    path = tmp_path / "s.jsonl"
    assert claudeutils.project_label(path, cwd="/Users/deg/Documents/degel") == "degel"


def test_project_label_ignores_a_trailing_slash(tmp_path):
    path = tmp_path / "s.jsonl"
    assert claudeutils.project_label(path, cwd="/a/b/") == "b"


def test_project_label_reads_the_file_when_no_cwd_is_supplied(tmp_path):
    path = write_session(tmp_path / "p", "u1", [{"type": "user", "cwd": "/a/beads-utils"}])
    assert claudeutils.project_label(path) == "beads-utils"


def test_project_label_falls_back_to_the_project_dir_name(tmp_path):
    path = write_session(tmp_path / "-a-b-c", "u1", [{"type": "user"}])
    assert claudeutils.project_label(path) == "-a-b-c"


def test_project_label_handles_the_root_cwd(tmp_path):
    assert claudeutils.project_label(tmp_path / "s.jsonl", cwd="/") == "/"


# --- has_human_prose ------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        "just a question",
        "  padded  ",
        [{"type": "text", "text": "hello"}],
        [{"type": "image"}, {"type": "text", "text": "hello"}],
    ],
)
def test_has_human_prose_accepts_real_typed_text(content):
    assert claudeutils.has_human_prose(content) is True


@pytest.mark.parametrize("tag", claudeutils.USER_WRAPPER_TAGS)
def test_has_human_prose_rejects_each_wrapper_tag_on_its_own(tag):
    """A `/clear` ghost is exactly this: wrappers and nothing else."""
    assert claudeutils.has_human_prose(f"<{tag}>anything at all</{tag}>") is False


def test_has_human_prose_rejects_a_stack_of_wrappers():
    text = (
        "<command-name>/clear</command-name>\n"
        "<command-message>clear</command-message>\n"
        "<command-args></command-args>\n"
        "<local-command-stdout></local-command-stdout>\n"
    )
    assert claudeutils.has_human_prose(text) is False


def test_has_human_prose_finds_prose_alongside_a_wrapper():
    text = "<system-reminder>ignore me</system-reminder>\nBut please do this."
    assert claudeutils.has_human_prose(text) is True


def test_has_human_prose_strips_wrappers_spanning_multiple_lines():
    assert claudeutils.has_human_prose("<system-reminder>a\nb\nc</system-reminder>") is False


@pytest.mark.parametrize("content", ["", "   \n\t", [], None, 42, {"type": "text"}])
def test_has_human_prose_rejects_empty_and_non_text_content(content):
    assert claudeutils.has_human_prose(content) is False


def test_has_human_prose_ignores_non_text_blocks_in_a_list():
    assert claudeutils.has_human_prose([{"type": "tool_result", "content": "x"}]) is False


def test_has_human_prose_ignores_a_non_string_text_field():
    assert claudeutils.has_human_prose([{"type": "text", "text": 42}]) is False


# --- SessionMeta ----------------------------------------------------------


def meta(**overrides) -> claudeutils.SessionMeta:
    base = dict(
        jsonl=None, custom_title=None, ai_title=None, cwd=None,
        first_ts=None, last_ts=None, human_prompts=0, assistant_turns=0,
    )
    base.update(overrides)
    return claudeutils.SessionMeta(**base)


def test_session_title_prefers_the_custom_title():
    assert meta(custom_title="Renamed", ai_title="Auto").title == "Renamed"


def test_session_title_falls_back_to_the_ai_title_then_to_untitled():
    assert meta(ai_title="Auto").title == "Auto"
    assert meta().title == "(untitled)"


@pytest.mark.parametrize(
    "prompts,turns,empty",
    [(0, 0, True), (1, 0, False), (0, 1, False), (3, 4, False)],
)
def test_session_is_empty_only_when_neither_side_produced_anything(prompts, turns, empty):
    assert meta(human_prompts=prompts, assistant_turns=turns).is_empty is empty


# --- read_session_meta ----------------------------------------------------


def test_read_session_meta_gathers_titles_cwd_timestamps_and_counts(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "ai-title", "aiTitle": "Auto name"},
        {"type": "custom-title", "customTitle": "Renamed"},
        dict(user_entry("first question"), cwd="/work", timestamp="2026-05-01T10:00:00Z"),
        dict(assistant_entry("an answer"), timestamp="2026-05-01T10:01:00Z"),
        dict(user_entry("second question"), timestamp="2026-05-01T11:30:00Z"),
    ])
    m = claudeutils.read_session_meta(path)
    assert m.custom_title == "Renamed"
    assert m.ai_title == "Auto name"
    assert m.cwd == "/work"
    assert m.first_ts == "2026-05-01T10:00:00Z"
    assert m.last_ts == "2026-05-01T11:30:00Z"
    assert m.human_prompts == 2
    assert m.assistant_turns == 1
    assert m.title == "Renamed"


def test_read_session_meta_does_not_count_wrapper_only_prompts(tmp_path):
    """This is what lets a `/clear` ghost register as 0p/0r."""
    path = write_session(tmp_path / "p", "u1", [
        user_entry("<command-name>/clear</command-name>"),
        user_entry("<system-reminder>context</system-reminder>"),
    ])
    m = claudeutils.read_session_meta(path)
    assert m.human_prompts == 0
    assert m.is_empty is True


def test_read_session_meta_excludes_subagent_sidechains_from_both_counts(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        user_entry("main prompt"),
        dict(user_entry("subagent prompt"), isSidechain=True),
        assistant_entry("main reply"),
        dict(assistant_entry("subagent reply"), isSidechain=True),
    ])
    m = claudeutils.read_session_meta(path)
    assert (m.human_prompts, m.assistant_turns) == (1, 1)


def test_read_session_meta_keeps_the_last_of_repeated_titles(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "custom-title", "customTitle": "First"},
        {"type": "custom-title", "customTitle": "Second"},
    ])
    assert claudeutils.read_session_meta(path).custom_title == "Second"


def test_read_session_meta_ignores_non_string_titles(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "custom-title", "customTitle": 42},
        {"type": "ai-title", "aiTitle": None},
    ])
    m = claudeutils.read_session_meta(path)
    assert m.custom_title is None and m.ai_title is None
    assert m.title == "(untitled)"


def test_read_session_meta_keeps_the_first_cwd_it_sees(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "user", "cwd": "/first"},
        {"type": "user", "cwd": "/second"},
    ])
    assert claudeutils.read_session_meta(path).cwd == "/first"


def test_read_session_meta_ignores_blank_timestamps(tmp_path):
    path = write_session(tmp_path / "p", "u1", [
        {"type": "user", "timestamp": ""},
        {"type": "user", "timestamp": "2026-05-01T10:00:00Z"},
    ])
    m = claudeutils.read_session_meta(path)
    assert m.first_ts == m.last_ts == "2026-05-01T10:00:00Z"


def test_read_session_meta_tolerates_malformed_lines_and_bare_values(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('not json\n[1,2,3]\n"a string"\n{"type": "user", "cwd": "/ok"}\n')
    assert claudeutils.read_session_meta(path).cwd == "/ok"


def test_read_session_meta_returns_blank_metadata_for_an_unreadable_file(tmp_path):
    """A missing session yields empty fields rather than raising."""
    m = claudeutils.read_session_meta(tmp_path / "absent.jsonl")
    assert m.is_empty and m.title == "(untitled)" and m.cwd is None


def test_read_session_meta_ignores_a_non_dict_message(tmp_path):
    path = write_session(tmp_path / "p", "u1", [{"type": "user", "message": "raw"}])
    assert claudeutils.read_session_meta(path).human_prompts == 0


# --- iter_sessions / list_sessions ----------------------------------------


def test_iter_sessions_walks_every_project_when_given_none(claude_home):
    write_session(claude_home / "proj-a", "u1", [user_entry("a")])
    write_session(claude_home / "proj-b", "u2", [user_entry("b")])
    assert {m.jsonl.stem for m in claudeutils.iter_sessions()} == {"u1", "u2"}


def test_iter_sessions_can_be_scoped_to_one_project(claude_home):
    write_session(claude_home / "proj-a", "u1", [user_entry("a")])
    write_session(claude_home / "proj-b", "u2", [user_entry("b")])
    scoped = list(claudeutils.iter_sessions(claude_home / "proj-a"))
    assert [m.jsonl.stem for m in scoped] == ["u1"]


def test_iter_sessions_yields_nothing_without_a_projects_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(claudeutils, "CLAUDE_PROJECTS", tmp_path / "absent")
    assert list(claudeutils.iter_sessions()) == []


def test_iter_sessions_ignores_stray_non_jsonl_files(claude_home):
    pdir = claude_home / "proj-a"
    write_session(pdir, "u1", [user_entry("a")])
    (pdir / "notes.txt").write_text("ignore me")
    assert [m.jsonl.stem for m in claudeutils.iter_sessions()] == ["u1"]


def test_list_sessions_orders_newest_first_by_mtime(claude_home):
    pdir = claude_home / "proj"
    older = write_session(pdir, "old", [user_entry("a")])
    newer = write_session(pdir, "new", [user_entry("b")])
    os.utime(older, (1_600_000_000, 1_600_000_000))
    os.utime(newer, (1_700_000_000, 1_700_000_000))
    assert [m.jsonl.stem for m in claudeutils.list_sessions()] == ["new", "old"]


# --- resolve_session ------------------------------------------------------


def test_resolve_session_accepts_an_explicit_jsonl_path(claude_home, tmp_path):
    path = write_session(tmp_path / "anywhere", "u1", [user_entry("a")])
    assert claudeutils.resolve_session(str(path)) == path


def test_resolve_session_finds_a_uuid_under_any_project(claude_home):
    path = write_session(claude_home / "proj-b", "abc-123", [user_entry("a")])
    assert claudeutils.resolve_session("abc-123") == path


def test_resolve_session_matches_a_title_substring_case_insensitively(claude_home):
    path = write_session(claude_home / "proj", "u1", [
        {"type": "custom-title", "customTitle": "Test Suite Work"},
    ])
    assert claudeutils.resolve_session("test suite") == path


def test_resolve_session_matches_against_the_ai_title_too(claude_home):
    path = write_session(claude_home / "proj", "u1", [
        {"type": "ai-title", "aiTitle": "Refactor the pager"},
    ])
    assert claudeutils.resolve_session("pager") == path


def test_resolve_session_prefers_a_uuid_over_a_title_match(claude_home):
    by_uuid = write_session(claude_home / "proj", "target", [user_entry("a")])
    write_session(claude_home / "proj", "other", [
        {"type": "custom-title", "customTitle": "target practice"},
    ])
    assert claudeutils.resolve_session("target") == by_uuid


def test_resolve_session_exits_when_nothing_matches(claude_home):
    write_session(claude_home / "proj", "u1", [user_entry("a")])
    with pytest.raises(SystemExit) as excinfo:
        claudeutils.resolve_session("no-such-thing")
    assert "no session found" in str(excinfo.value.code)


def test_resolve_session_lists_candidates_when_a_title_is_ambiguous(claude_home, capsys):
    for uuid in ("u1", "u2"):
        write_session(claude_home / "proj", uuid, [
            {"type": "custom-title", "customTitle": f"shared name {uuid}"},
        ])
    with pytest.raises(SystemExit) as excinfo:
        claudeutils.resolve_session("shared name")
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "2 sessions match" in err
    assert "u1" in err and "u2" in err


def test_resolve_session_reports_a_duplicated_uuid_across_projects(claude_home, capsys):
    for proj in ("proj-a", "proj-b"):
        write_session(claude_home / proj, "dupe", [user_entry("a")])
    with pytest.raises(SystemExit) as excinfo:
        claudeutils.resolve_session("dupe")
    assert excinfo.value.code == 1
    assert "unexpected" in capsys.readouterr().err


def test_resolve_session_truncates_a_very_long_candidate_list(claude_home, capsys):
    for i in range(30):
        write_session(claude_home / "proj", f"u{i:02d}", [
            {"type": "custom-title", "customTitle": f"common {i}"},
        ])
    with pytest.raises(SystemExit):
        claudeutils.resolve_session("common")
    err = capsys.readouterr().err
    assert "and 5 more" in err


def test_resolve_session_exits_without_a_projects_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(claudeutils, "CLAUDE_PROJECTS", tmp_path / "absent")
    with pytest.raises(SystemExit) as excinfo:
        claudeutils.resolve_session("anything")
    assert "no such directory" in str(excinfo.value.code)


def test_resolve_session_ignores_a_jsonl_suffix_that_is_not_a_file(claude_home):
    """A path-looking argument that doesn't exist falls through to lookup."""
    path = write_session(claude_home / "proj", "missing.jsonl", [user_entry("a")])
    assert path.name == "missing.jsonl.jsonl"
    with pytest.raises(SystemExit):
        claudeutils.resolve_session("/nowhere/missing.jsonl")


def test_wrapper_tag_regex_covers_every_declared_tag():
    """The tag list and the compiled pattern must not drift apart."""
    for tag in claudeutils.USER_WRAPPER_TAGS:
        assert f"<{tag}>" in claudeutils._USER_WRAPPER_RE.pattern


def test_claude_projects_points_under_the_home_directory():
    assert claudeutils.CLAUDE_PROJECTS.parts[-2:] == (".claude", "projects")


def test_write_session_helper_produces_one_json_object_per_line(tmp_path):
    """Guards the fixture helper the rest of these tests depend on."""
    path = write_session(tmp_path / "p", "u1", [user_entry("a"), assistant_entry("b")])
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert [json.loads(ln)["type"] for ln in lines] == ["user", "assistant"]
