"""Tests for bd-find-live, the live-work listing behind an end-of-session audit.

The thing that matters here is the exclusion: a bead parked behind a deferred
gate must be left out, a bead waiting on live work must stay in, and whatever
is left out must be named. An audit that silently dropped a bead, or silently
billed a parked one, would be worse than no filter at all.
"""
from __future__ import annotations

import json

from conftest import load_script

bd_find_live = load_script("bd-find-live")


def bead(iid, **fields):
    base = {"id": iid, "title": f"Title {iid}", "status": "open"}
    base.update(fields)
    return base


# --- parked_ids ------------------------------------------------------------


def test_a_bead_blocked_on_a_deferred_bead_is_parked():
    assert bd_find_live.parked_ids(["m"], {"gate"}, {"m": ["gate"]}) == {"m"}


def test_a_bead_blocked_through_its_parent_is_parked():
    """The batch-gate shape: the parent sits on the gate, the child on the parent."""
    parked = bd_find_live.parked_ids(
        ["parent", "child"], {"gate"}, {"parent": ["gate"], "child": ["parent"]},
    )
    assert parked == {"parent", "child"}


def test_a_bead_blocked_on_live_work_is_not_parked():
    """Waiting on an open bead is a dependency, not a parking."""
    assert bd_find_live.parked_ids(["b"], set(), {"b": ["a"]}) == set()


def test_an_unblocked_bead_is_not_parked():
    assert bd_find_live.parked_ids(["a"], {"gate"}, {}) == set()


def test_one_deferred_blocker_among_live_ones_still_parks():
    assert bd_find_live.parked_ids(["b"], {"gate"}, {"b": ["a", "gate"]}) == {"b"}


def test_a_dependency_cycle_terminates():
    """bd refuses cycles, but a walk that could hang on one is still a bug."""
    assert bd_find_live.parked_ids(["a", "b"], set(), {"a": ["b"], "b": ["a"]}) == set()


# --- lean ------------------------------------------------------------------


def test_lean_replaces_the_notes_log_with_its_length():
    out = bd_find_live.lean(bead("a", notes="x" * 37, description="kept"))
    assert "notes" not in out
    assert out["notes_len"] == 37
    assert out["description"] == "kept"


def test_lean_counts_missing_or_null_notes_as_zero():
    assert bd_find_live.lean(bead("a"))["notes_len"] == 0
    assert bd_find_live.lean(bead("a", notes=None))["notes_len"] == 0


# --- fetch -----------------------------------------------------------------


def test_fetch_never_lets_bd_page_the_listings(fake_bd, project):
    """bd list documents a default limit of 50; the audit must see every bead."""
    fake_bd.json_rule("blocked", payload=[])
    fake_bd.issues([])
    bd_find_live.fetch(project)
    list_calls = [argv for argv in fake_bd.calls if argv[0] == "list"]
    assert list_calls, fake_bd.calls
    for argv in list_calls:
        assert "--limit" in argv and argv[argv.index("--limit") + 1] == "0", argv


def test_fetch_separates_candidates_deferred_and_blockers(fake_bd, project):
    fake_bd.json_rule("blocked", payload=[{"id": "m", "blocked_by": ["gate"]}])
    fake_bd.json_rule("--status=deferred", payload=[bead("gate", status="deferred")])
    fake_bd.json_rule("--status=open,in_progress", payload=[bead("m"), bead("free")])
    beads, deferred, blocked_by = bd_find_live.fetch(project)
    assert [b["id"] for b in beads] == ["m", "free"]
    assert deferred == {"gate"}
    assert blocked_by == {"m": ["gate"]}


# --- end to end ------------------------------------------------------------


def program(fake_bd):
    fake_bd.json_rule("blocked", payload=[
        {"id": "parent", "blocked_by": ["gate"]},
        {"id": "child", "blocked_by": ["parent"]},
        {"id": "waiting", "blocked_by": ["free"]},
    ])
    fake_bd.json_rule("--status=deferred", payload=[bead("gate", status="deferred")])
    fake_bd.json_rule("--status=open,in_progress", payload=[
        bead("free", notes="a log"), bead("waiting"), bead("parent"), bead("child"),
    ])


def test_live_beads_are_printed_and_parked_ones_named(run_script, fake_bd, project):
    program(fake_bd)
    result = run_script("bd-find-live", str(project))
    assert result.returncode == 0, result.stderr
    assert [b["id"] for b in json.loads(result.stdout)] == ["free", "waiting"]
    assert result.stderr.startswith("bd-find-live: left out 2 parked beads (")
    assert result.stderr.rstrip().endswith("): child parent")


def test_lean_output_drops_notes(run_script, fake_bd, project):
    program(fake_bd)
    result = run_script("bd-find-live", "--lean", str(project))
    assert result.returncode == 0, result.stderr
    free = json.loads(result.stdout)[0]
    assert "notes" not in free and free["notes_len"] == 5


def test_nothing_on_stderr_when_nothing_is_parked(run_script, fake_bd, project):
    fake_bd.json_rule("blocked", payload=[])
    fake_bd.json_rule("--status=deferred", payload=[])
    fake_bd.json_rule("--status=open,in_progress", payload=[bead("a")])
    result = run_script("bd-find-live", str(project))
    assert result.returncode == 0
    assert result.stderr == ""


def test_a_failing_bd_is_reported_not_swallowed(run_script, fake_bd, project):
    fake_bd.default(stderr="boom\n", exit_code=2)
    result = run_script("bd-find-live", str(project))
    assert result.returncode != 0
    assert "boom" in result.stderr and "bd list failed" in result.stderr
