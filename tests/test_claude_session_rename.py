"""Tests for claude-session-rename.

The script has one job -- append what /rename would have appended -- so the
tests read the result back through claudeutils.read_session_meta, the same
reader every other session script uses. If that round trip holds, the picker
and the list/find/report scripts all see the new title.
"""
from __future__ import annotations

import json
import sys

import pytest

import claudeutils
from conftest import load_script, write_session

rename = load_script("claude-session-rename")


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    """An empty stand-in for ~/.claude/sessions, so no real process is 'live'."""
    d = tmp_path / "claude-sessions"
    d.mkdir()
    monkeypatch.setattr(claudeutils, "CLAUDE_SESSIONS", d)
    return d


@pytest.fixture
def session(claude_home):
    return write_session(claude_home / "-proj", "1111aaaa-bbbb-cccc", [
        {"type": "ai-title", "aiTitle": "Auto title"},
        {"type": "custom-title", "customTitle": "Old title"},
        {"type": "user", "message": {"role": "user", "content": "hi"}},
    ])


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["claude-session-rename", *argv])
    return rename.main()


def records(jsonl):
    return [json.loads(ln) for ln in jsonl.read_text().splitlines()]


# --- the records ----------------------------------------------------------


def test_title_records_mirror_what_rename_writes():
    """The two records, in this order, are what a real /rename appends.

    Pinned as data rather than behavior: if Claude Code ever changes the
    record shape, this is the one place the script's knowledge of it lives.
    """
    assert rename.title_records("u1", "New") == [
        {"type": "custom-title", "customTitle": "New", "sessionId": "u1"},
        {"type": "agent-name", "agentName": "New", "sessionId": "u1"},
    ]


def test_append_records_adds_one_line_per_record(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"type": "user"}\n')
    rename.append_records(path, [{"a": 1}, {"b": 2}])
    assert records(path) == [{"type": "user"}, {"a": 1}, {"b": 2}]


def test_append_records_starts_a_fresh_line_after_a_torn_tail(tmp_path):
    """A transcript missing its final newline must not swallow the record.

    Appending blindly would glue the new JSON onto the previous line, making
    both unparseable -- and read_session_meta silently skips bad lines, so
    the rename would look like it never happened.
    """
    path = tmp_path / "s.jsonl"
    path.write_text('{"type": "user"}')  # no trailing newline
    rename.append_records(path, [{"a": 1}])
    assert records(path) == [{"type": "user"}, {"a": 1}]


def test_append_records_handles_an_empty_file(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text("")
    rename.append_records(path, [{"a": 1}])
    assert records(path) == [{"a": 1}]


def test_append_records_keeps_non_ascii_titles_readable(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text("")
    rename.append_records(path, [{"customTitle": "Café → résumé"}])
    assert "Café → résumé" in path.read_text(encoding="utf-8")


# --- main -----------------------------------------------------------------


def test_main_renames_by_uuid_and_the_readers_see_it(monkeypatch, capsys,
                                                    sessions_dir, session):
    """The round trip that matters: what the script writes, the readers see.

    Reads back through claudeutils.read_session_meta, the reader behind
    claude-session-list/find/report, and checks the ai-title survives, since
    a rename must only add a custom-title, never disturb the auto title.
    """
    assert run(monkeypatch, "1111aaaa-bbbb-cccc", "New title") == 0
    meta = claudeutils.read_session_meta(session)
    assert meta.custom_title == "New title"
    assert meta.ai_title == "Auto title"  # untouched
    tail = records(session)[-2:]
    assert tail == [
        {"type": "custom-title", "customTitle": "New title",
         "sessionId": "1111aaaa-bbbb-cccc"},
        {"type": "agent-name", "agentName": "New title",
         "sessionId": "1111aaaa-bbbb-cccc"},
    ]
    assert capsys.readouterr().out == "1111aaaa-bbbb-cccc: Old title -> New title\n"


def test_main_renames_by_title_substring(monkeypatch, sessions_dir, session):
    assert run(monkeypatch, "old tit", "Renamed") == 0
    assert claudeutils.read_session_meta(session).custom_title == "Renamed"


def test_main_renames_by_path(monkeypatch, sessions_dir, session):
    assert run(monkeypatch, str(session), "Renamed") == 0
    assert claudeutils.read_session_meta(session).custom_title == "Renamed"


def test_main_reports_untitled_when_the_session_had_no_title(monkeypatch, capsys,
                                                            sessions_dir, claude_home):
    write_session(claude_home / "-proj", "2222aaaa-bbbb-cccc", [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
    ])
    assert run(monkeypatch, "2222aaaa-bbbb-cccc", "Named") == 0
    assert capsys.readouterr().out == "2222aaaa-bbbb-cccc: (untitled) -> Named\n"


def test_main_strips_the_title(monkeypatch, sessions_dir, session):
    assert run(monkeypatch, "1111aaaa-bbbb-cccc", "  padded  ") == 0
    assert claudeutils.read_session_meta(session).custom_title == "padded"


@pytest.mark.parametrize("bad", ["", "   ", "\t"])
def test_main_rejects_an_empty_title(monkeypatch, sessions_dir, session, bad):
    with pytest.raises(SystemExit) as excinfo:
        run(monkeypatch, "1111aaaa-bbbb-cccc", bad)
    assert excinfo.value.code == "error: title must be non-empty"
    assert claudeutils.read_session_meta(session).custom_title == "Old title"


def test_main_rejects_a_multiline_title(monkeypatch, sessions_dir, session):
    with pytest.raises(SystemExit) as excinfo:
        run(monkeypatch, "1111aaaa-bbbb-cccc", "two\nlines")
    assert excinfo.value.code == "error: title must be a single line"


def test_main_refuses_a_running_session(monkeypatch, sessions_dir, session):
    """A running session is refused, and its transcript is left untouched.

    The live process re-emits its own title on later turns, so an appended
    rename would be silently undone; refusing is the only honest answer.
    The probe itself is covered in test_claudeutils; here it is stubbed.
    """
    monkeypatch.setattr(claudeutils, "live_session_pid", lambda sid: 4242)
    with pytest.raises(SystemExit) as excinfo:
        run(monkeypatch, "1111aaaa-bbbb-cccc", "New title")
    assert excinfo.value.code == (
        "error: session 1111aaaa-bbbb-cccc is running (pid 4242); "
        "use /rename inside it instead"
    )
    assert claudeutils.read_session_meta(session).custom_title == "Old title"


def test_main_proceeds_past_a_stale_live_file(monkeypatch, sessions_dir, session):
    """A sessions/ entry whose pid is gone is a crash leftover, not a live session."""
    (sessions_dir / "99.json").write_text(json.dumps({
        "pid": 2 ** 22 - 1,  # unreachable on macOS; never reached on fresh Linux CI
        "sessionId": "1111aaaa-bbbb-cccc",
    }))
    assert run(monkeypatch, "1111aaaa-bbbb-cccc", "New title") == 0
    assert claudeutils.read_session_meta(session).custom_title == "New title"


def test_main_lists_candidates_for_an_ambiguous_session(monkeypatch, capsys,
                                                       sessions_dir, claude_home):
    """A substring that matches two sessions must rename neither.

    Delegated to resolve_session, but asserted here because a rename is a
    write: the cost of guessing wrong is a mislabelled session, not a wrong
    listing.
    """
    for uuid in ("aaaa-1", "aaaa-2"):
        write_session(claude_home / "-proj", uuid, [
            {"type": "custom-title", "customTitle": "Pager work"},
        ])
    with pytest.raises(SystemExit) as excinfo:
        run(monkeypatch, "pager", "New")
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "2 sessions match 'pager'" in err
    assert "aaaa-1" in err and "aaaa-2" in err


def test_main_fails_cleanly_for_an_unknown_session(monkeypatch, sessions_dir,
                                                  claude_home):
    with pytest.raises(SystemExit) as excinfo:
        run(monkeypatch, "nothing-like-this", "New")
    assert excinfo.value.code == "error: no session found for 'nothing-like-this'"


def test_main_reports_an_unwritable_transcript(monkeypatch, sessions_dir, session):
    def boom(jsonl, recs):
        raise PermissionError("nope")

    monkeypatch.setattr(rename, "append_records", boom)
    with pytest.raises(SystemExit) as excinfo:
        run(monkeypatch, "1111aaaa-bbbb-cccc", "New")
    assert str(excinfo.value.code).startswith(f"error: cannot write {session}")
