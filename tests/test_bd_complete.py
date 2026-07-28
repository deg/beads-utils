"""Tests for bd-complete, the single front door for dynamic shell completion.

The governing rule: a lookup that fails must produce no output and exit 0. A
completion helper that errors, or prints a traceback, garbles the user's
command line -- so every failure mode here asserts silence, not a message.
"""
from __future__ import annotations

import json
import os

import pytest

from conftest import load_script, write_session

bd_complete = load_script("bd-complete")


# --- emit -----------------------------------------------------------------


def test_emit_writes_value_tab_description(capsys):
    bd_complete.emit("beads-utils-v9o", "Some title")
    assert capsys.readouterr().out == "beads-utils-v9o\tSome title\n"


def test_emit_still_writes_the_tab_with_no_description(capsys):
    """The shells split on the tab, so the separator must always be there."""
    bd_complete.emit("beads-utils-v9o")
    assert capsys.readouterr().out == "beads-utils-v9o\t\n"


# --- complete_ids ---------------------------------------------------------


def test_complete_ids_emits_full_ids_with_titles(fake_bd, capsys):
    fake_bd.issues([
        {"id": "beads-utils-v9o", "title": "First"},
        {"id": "beads-utils-v9o.4", "title": "Second"},
    ])
    bd_complete.complete_ids()
    assert capsys.readouterr().out == (
        "beads-utils-v9o\tFirst\n"
        "beads-utils-v9o.4\tSecond\n"
    )


def test_complete_ids_asks_bd_for_every_status_unlimited(fake_bd, capsys):
    """Completion must offer closed beads too, and never be page-limited."""
    fake_bd.issues([])
    bd_complete.complete_ids()
    (argv,) = fake_bd.calls
    assert argv == ["list", "--status=all", "--limit", "0", "--json"]


def test_complete_ids_tolerates_a_missing_title(fake_bd, capsys):
    fake_bd.issues([{"id": "b-1"}, {"id": "b-2", "title": None}])
    bd_complete.complete_ids()
    assert capsys.readouterr().out == "b-1\t\nb-2\t\n"


def test_complete_ids_skips_rows_with_no_id(fake_bd, capsys):
    fake_bd.issues([{"title": "orphan"}, {"id": "", "title": "blank"}, {"id": "b-1"}])
    bd_complete.complete_ids()
    assert capsys.readouterr().out == "b-1\t\n"


def test_complete_ids_skips_non_dict_rows(fake_bd, capsys):
    fake_bd.issues(["a string", 42, {"id": "b-1"}])
    bd_complete.complete_ids()
    assert capsys.readouterr().out == "b-1\t\n"


def test_complete_ids_is_silent_when_bd_fails(fake_bd, capsys):
    fake_bd.default(stderr="database locked\n", exit_code=1)
    bd_complete.complete_ids()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_complete_ids_is_silent_when_bd_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    bd_complete.complete_ids()
    assert capsys.readouterr().out == ""


def test_complete_ids_is_silent_on_unparseable_json(fake_bd, capsys):
    fake_bd.default(stdout="{not json")
    bd_complete.complete_ids()
    assert capsys.readouterr().out == ""


def test_complete_ids_is_silent_when_bd_returns_a_non_list(fake_bd, capsys):
    fake_bd.default(stdout=json.dumps({"issues": []}))
    bd_complete.complete_ids()
    assert capsys.readouterr().out == ""


def test_complete_ids_treats_empty_output_as_no_candidates(fake_bd, capsys):
    fake_bd.default(stdout="")
    bd_complete.complete_ids()
    assert capsys.readouterr().out == ""


# --- complete_sessions ----------------------------------------------------


def test_complete_sessions_emits_uuid_and_title(claude_home, capsys):
    write_session(claude_home / "proj", "uuid-one", [
        {"type": "custom-title", "customTitle": "Test Suite"},
    ])
    bd_complete.complete_sessions()
    assert capsys.readouterr().out == "uuid-one\tTest Suite\n"


def test_complete_sessions_labels_an_untitled_session(claude_home, capsys):
    write_session(claude_home / "proj", "uuid-one", [{"type": "user"}])
    bd_complete.complete_sessions()
    assert capsys.readouterr().out == "uuid-one\t(untitled)\n"


def test_complete_sessions_is_silent_when_there_are_none(claude_home, capsys):
    bd_complete.complete_sessions()
    assert capsys.readouterr().out == ""


def test_complete_sessions_orders_newest_first(claude_home, capsys):
    pdir = claude_home / "proj"
    older = write_session(pdir, "older", [{"type": "custom-title", "customTitle": "A"}])
    newer = write_session(pdir, "newer", [{"type": "custom-title", "customTitle": "B"}])
    os.utime(older, (1_600_000_000, 1_600_000_000))
    os.utime(newer, (1_700_000_000, 1_700_000_000))
    bd_complete.complete_sessions()
    assert capsys.readouterr().out == "newer\tB\nolder\tA\n"


# --- Argument parsing -----------------------------------------------------


def test_main_requires_a_candidate_kind(monkeypatch):
    monkeypatch.setattr(bd_complete.sys, "argv", ["bd-complete"])
    with pytest.raises(SystemExit) as excinfo:
        bd_complete.main()
    assert excinfo.value.code == 2


def test_main_rejects_an_unknown_candidate_kind(monkeypatch):
    monkeypatch.setattr(bd_complete.sys, "argv", ["bd-complete", "nonsense"])
    with pytest.raises(SystemExit) as excinfo:
        bd_complete.main()
    assert excinfo.value.code == 2


def test_main_dispatches_ids_and_exits_zero(monkeypatch, fake_bd, capsys):
    fake_bd.issues([{"id": "b-1", "title": "T"}])
    monkeypatch.setattr(bd_complete.sys, "argv", ["bd-complete", "ids"])
    assert bd_complete.main() == 0
    assert capsys.readouterr().out == "b-1\tT\n"


def test_main_dispatches_sessions_and_exits_zero(monkeypatch, claude_home, capsys):
    write_session(claude_home / "proj", "u1", [
        {"type": "custom-title", "customTitle": "T"},
    ])
    monkeypatch.setattr(bd_complete.sys, "argv", ["bd-complete", "sessions"])
    assert bd_complete.main() == 0
    assert capsys.readouterr().out == "u1\tT\n"
