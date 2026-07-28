"""Tests for bd-export-csv."""
from __future__ import annotations

import csv
import io

import pytest

from conftest import load_script

bd_export_csv = load_script("bd-export-csv")


# --- format_labels / format_dependencies ---------------------------------


def test_format_labels_joins_sorted_labels_with_a_pipe():
    assert bd_export_csv.format_labels(["zeta", "alpha", "mid"]) == "alpha|mid|zeta"


@pytest.mark.parametrize("labels", [None, [], ()])
def test_format_labels_renders_nothing_for_no_labels(labels):
    assert bd_export_csv.format_labels(labels) == ""


def test_format_dependencies_renders_type_and_target():
    deps = [
        {"type": "blocks", "depends_on_id": "b-2"},
        {"type": "parent-child", "depends_on_id": "b-3"},
    ]
    assert bd_export_csv.format_dependencies(deps) == "blocks:b-2|parent-child:b-3"


def test_format_dependencies_marks_missing_pieces_rather_than_dropping_the_edge():
    assert bd_export_csv.format_dependencies([{}]) == "?:?"


@pytest.mark.parametrize("deps", [None, []])
def test_format_dependencies_renders_nothing_for_no_dependencies(deps):
    assert bd_export_csv.format_dependencies(deps) == ""


# --- issue_to_row ---------------------------------------------------------


def test_issue_to_row_maps_every_declared_column():
    """The row and the CSV header must not drift apart."""
    assert set(bd_export_csv.issue_to_row({})) == set(bd_export_csv.COLUMNS)


def test_issue_to_row_renames_issue_type_to_type():
    row = bd_export_csv.issue_to_row({"issue_type": "bug"})
    assert row["type"] == "bug"


def test_issue_to_row_defaults_every_absent_field_to_empty():
    row = bd_export_csv.issue_to_row({})
    assert set(row.values()) == {""}


def test_issue_to_row_carries_the_scalar_fields_through():
    issue = {
        "id": "b-1", "title": "Fix", "status": "open", "priority": 2,
        "assignee": "ann", "owner": "bob", "created_at": "2026-01-01T00:00:00Z",
        "close_reason": "done", "description": "d", "notes": "n",
        "design": "de", "acceptance_criteria": "ac", "spec_id": "s",
        "defer_until": "2026-02-01", "external_ref": "GH-1",
        "dependency_count": 2, "dependent_count": 1, "comment_count": 3,
    }
    row = bd_export_csv.issue_to_row(issue)
    for key, value in issue.items():
        if key == "id":
            assert row["id"] == value
    assert row["priority"] == 2
    assert row["dependency_count"] == 2
    assert row["external_ref"] == "GH-1"


def test_issue_to_row_formats_the_nested_label_and_dependency_fields():
    row = bd_export_csv.issue_to_row({
        "labels": ["b", "a"],
        "dependencies": [{"type": "blocks", "depends_on_id": "x-9"}],
    })
    assert row["labels"] == "a|b"
    assert row["dependencies"] == "blocks:x-9"


# --- derive_prefix --------------------------------------------------------


def test_derive_prefix_takes_the_segment_before_the_first_dash():
    issues = [{"id": "beads-utils-v9o"}]
    assert bd_export_csv.derive_prefix(issues, "fallback") == "beads"


def test_derive_prefix_skips_ids_without_a_dash():
    issues = [{"id": "nodash"}, {"id": "proj-1"}]
    assert bd_export_csv.derive_prefix(issues, "fallback") == "proj"


@pytest.mark.parametrize("issues", [[], [{}], [{"id": ""}], [{"id": "nodash"}]])
def test_derive_prefix_falls_back_when_no_id_carries_one(issues):
    assert bd_export_csv.derive_prefix(issues, "fallback") == "fallback"


# --- parse_sort -----------------------------------------------------------


def test_parse_sort_reads_keys_and_descending_prefixes():
    assert bd_export_csv.parse_sort("priority,-created_at") == [
        ("priority", False), ("created_at", True),
    ]


def test_parse_sort_accepts_an_explicit_ascending_plus():
    assert bd_export_csv.parse_sort("+title") == [("title", False)]


def test_parse_sort_ignores_blank_tokens_and_surrounding_space():
    assert bd_export_csv.parse_sort(" id , , -status ") == [("id", False), ("status", True)]


def test_parse_sort_accepts_an_empty_spec_as_no_keys():
    assert bd_export_csv.parse_sort("") == []


def test_parse_sort_rejects_an_unknown_key_and_lists_the_valid_ones():
    with pytest.raises(SystemExit) as excinfo:
        bd_export_csv.parse_sort("nonsense")
    message = str(excinfo.value.code)
    assert "'nonsense'" in message
    assert "created_at" in message  # the valid-key list is shown


def test_parse_sort_rejects_a_column_that_is_not_a_sort_key():
    """COLUMNS is wider than SORT_KEYS on purpose (free text doesn't sort)."""
    assert "description" in bd_export_csv.COLUMNS
    with pytest.raises(SystemExit):
        bd_export_csv.parse_sort("description")


def test_every_sort_key_is_also_an_exported_column():
    assert bd_export_csv.SORT_KEYS <= set(bd_export_csv.COLUMNS)


# --- apply_sort -----------------------------------------------------------


def rows(*specs):
    return [dict(zip(("id", "priority", "status"), s)) for s in specs]


def test_apply_sort_orders_ascending_by_a_single_key():
    data = rows(("c", 1, "open"), ("a", 3, "open"), ("b", 2, "open"))
    bd_export_csv.apply_sort(data, [("id", False)])
    assert [r["id"] for r in data] == ["a", "b", "c"]


def test_apply_sort_orders_descending_when_asked():
    data = rows(("a", 1, "open"), ("b", 2, "open"))
    bd_export_csv.apply_sort(data, [("id", True)])
    assert [r["id"] for r in data] == ["b", "a"]


def test_apply_sort_treats_the_first_key_as_primary():
    data = rows(("a", 2, "open"), ("b", 1, "open"), ("c", 1, "closed"))
    bd_export_csv.apply_sort(data, [("priority", False), ("id", True)])
    assert [r["id"] for r in data] == ["c", "b", "a"]


def test_apply_sort_compares_as_strings_so_mixed_types_do_not_raise():
    """Sorting is lexical by design -- bd hands back ints and strings alike."""
    data = [{"priority": 10}, {"priority": "2"}, {"priority": 1}]
    bd_export_csv.apply_sort(data, [("priority", False)])
    assert [r["priority"] for r in data] == [1, 10, "2"]


def test_apply_sort_sorts_in_place_and_returns_none():
    data = rows(("b", 1, "open"), ("a", 1, "open"))
    assert bd_export_csv.apply_sort(data, [("id", False)]) is None
    assert data[0]["id"] == "a"


def test_apply_sort_with_no_keys_leaves_the_order_alone():
    data = rows(("c", 1, "open"), ("a", 1, "open"))
    bd_export_csv.apply_sort(data, [])
    assert [r["id"] for r in data] == ["c", "a"]


# --- run_bd_export --------------------------------------------------------


def test_run_bd_export_asks_bd_for_everything_except_memories(fake_bd, project):
    fake_bd.default(stdout='{"id": "b-1"}\n')
    assert bd_export_csv.run_bd_export(project) == '{"id": "b-1"}\n'
    (argv,) = fake_bd.calls
    assert argv == ["export", "--all", "--no-memories"]


def test_run_bd_export_reports_a_failure_without_a_traceback(fake_bd, project):
    fake_bd.default(stderr="nope\n", exit_code=2)
    with pytest.raises(SystemExit) as excinfo:
        bd_export_csv.run_bd_export(project)
    assert "exit 2" in str(excinfo.value.code)


def test_run_bd_export_reports_a_missing_bd_binary(project, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SystemExit) as excinfo:
        bd_export_csv.run_bd_export(project)
    assert "not found on PATH" in str(excinfo.value.code)


# --- Whole-file shape -----------------------------------------------------


def test_the_written_csv_round_trips_through_the_reader():
    """Free text with commas, quotes and newlines must survive the export."""
    row = bd_export_csv.issue_to_row({
        "id": "b-1",
        "title": 'A "quoted", comma-laden title',
        "description": "line one\nline two",
    })
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=bd_export_csv.COLUMNS)
    writer.writeheader()
    writer.writerow(row)
    buf.seek(0)
    (parsed,) = list(csv.DictReader(buf))
    assert parsed["title"] == 'A "quoted", comma-laden title'
    assert parsed["description"] == "line one\nline two"
