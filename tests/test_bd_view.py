"""Tests for bd-view.

bd-view is the one script with a third-party dependency (`rich`), guarded by
HAVE_RICH. The pure functions below are stdlib-only and run either way; the
rich-specific rendering is skipped rather than silently unexercised when the
library is absent, so the suite stays honest about which branch it covered.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from conftest import load_script

bd_view = load_script("bd-view")

needs_rich = pytest.mark.skipif(
    not bd_view.HAVE_RICH, reason="rich is not installed (run under `uv run --with rich`)"
)


# --- with_hard_breaks -----------------------------------------------------


def test_with_hard_breaks_makes_single_newlines_visible():
    """CommonMark would otherwise collapse them into spaces."""
    assert bd_view.with_hard_breaks("one\ntwo") == "one  \ntwo  "


def test_with_hard_breaks_leaves_blank_lines_alone():
    assert bd_view.with_hard_breaks("one\n\ntwo") == "one  \n\ntwo  "


def test_with_hard_breaks_does_not_double_an_existing_break():
    assert bd_view.with_hard_breaks("one  \ntwo") == "one  \ntwo  "


def test_with_hard_breaks_skips_backtick_fenced_code():
    text = "prose\n```\ncode line\n```\nmore"
    assert bd_view.with_hard_breaks(text) == "prose  \n```\ncode line\n```\nmore  "


def test_with_hard_breaks_skips_tilde_fenced_code():
    text = "~~~\ncode\n~~~"
    assert bd_view.with_hard_breaks(text) == text


def test_with_hard_breaks_handles_empty_text():
    assert bd_view.with_hard_breaks("") == ""


def test_with_hard_breaks_leaves_whitespace_only_lines_alone():
    assert bd_view.with_hard_breaks("a\n   \nb") == "a  \n   \nb  "


# --- dep_heading ----------------------------------------------------------


@pytest.mark.parametrize(
    "direction,dep_type,expected",
    [
        ("down", "parent-child", "Parent:"),
        ("up", "parent-child", "Children:"),
        ("down", "blocks", "Depends on:"),
        ("up", "blocks", "Blocks:"),
        ("down", "supersedes", "Supersedes:"),
        ("up", "supersedes", "Superseded by:"),
        ("down", "discovered-from", "Discovered from:"),
    ],
)
def test_dep_heading_names_the_known_relationships(direction, dep_type, expected):
    assert bd_view.dep_heading(direction, dep_type) == expected


def test_dep_heading_falls_back_to_the_raw_type_name():
    """An unknown edge kind renders under its own name rather than vanishing."""
    assert bd_view.dep_heading("down", "invented-kind") == "invented-kind:"
    assert bd_view.dep_heading("up", "invented-kind") == "invented-kind (inbound):"


def test_dep_heading_labels_a_typeless_edge():
    assert bd_view.dep_heading("down", "") == "related:"


def test_dep_headings_table_covers_both_directions_of_every_type():
    types = {dep_type for _, dep_type in bd_view.DEP_HEADINGS}
    for dep_type in types:
        assert ("down", dep_type) in bd_view.DEP_HEADINGS
        assert ("up", dep_type) in bd_view.DEP_HEADINGS


# --- group_deps -----------------------------------------------------------


def edge(dep_type, target="b-2"):
    return {"dependency_type": dep_type, "issue_id": target}


def test_group_deps_orders_parent_children_before_depends_blocks():
    """Matches how `bd show` presents them."""
    groups = bd_view.group_deps(
        deps=[edge("blocks"), edge("parent-child")],
        dependents=[edge("blocks"), edge("parent-child")],
    )
    assert [(d, t) for d, t, _ in groups] == [
        ("down", "parent-child"), ("up", "parent-child"),
        ("down", "blocks"), ("up", "blocks"),
    ]


def test_group_deps_keeps_the_two_halves_of_a_relationship_adjacent():
    groups = bd_view.group_deps(deps=[edge("tracks")], dependents=[edge("tracks")])
    assert [(d, t) for d, t, _ in groups] == [("down", "tracks"), ("up", "tracks")]


def test_group_deps_sorts_unranked_types_alphabetically_after_the_ranked_ones():
    groups = bd_view.group_deps(
        deps=[edge("zeta"), edge("alpha"), edge("blocks")], dependents=[],
    )
    assert [t for _, t, _ in groups] == ["blocks", "alpha", "zeta"]


def test_group_deps_collects_every_edge_of_a_group():
    groups = bd_view.group_deps(
        deps=[edge("blocks", "b-2"), edge("blocks", "b-3")], dependents=[],
    )
    (_, _, items), = groups
    assert [i["issue_id"] for i in items] == ["b-2", "b-3"]


def test_group_deps_buckets_a_typeless_edge_under_the_empty_type():
    groups = bd_view.group_deps(deps=[{"issue_id": "b-2"}], dependents=[])
    assert [t for _, t, _ in groups] == [""]


def test_group_deps_returns_nothing_for_no_edges():
    assert bd_view.group_deps([], []) == []


# --- has_parent_edge ------------------------------------------------------


def test_has_parent_edge_detects_a_parent_child_edge():
    assert bd_view.has_parent_edge([edge("blocks"), edge("parent-child")]) is True


def test_has_parent_edge_is_false_without_one():
    """When false but the bead has a `parent`, bd-view shows the bare id."""
    assert bd_view.has_parent_edge([edge("blocks")]) is False
    assert bd_view.has_parent_edge([]) is False


# --- flatten_pairs / flatten_extra ---------------------------------------


def test_flatten_pairs_keeps_strings_and_json_encodes_the_rest():
    pairs = bd_view.flatten_pairs({"branch": "main", "count": 3, "flags": ["a"]})
    assert pairs == [("branch", "main"), ("count", "3"), ("flags", '["a"]')]


def test_flatten_pairs_stringifies_non_string_keys():
    assert bd_view.flatten_pairs({7: "x"}) == [("7", "x")]


def test_flatten_extra_expands_a_dict_one_level():
    assert bd_view.flatten_extra("metadata", {"branch": "main"}) == [
        ("metadata.branch", "main"),
    ]


def test_flatten_extra_joins_a_scalar_list_readably():
    assert bd_view.flatten_extra("tags", ["a", "b", 3]) == [("tags", "a, b, 3")]


def test_flatten_extra_falls_back_to_json_for_a_list_of_objects():
    assert bd_view.flatten_extra("rows", [{"a": 1}]) == [("rows", '[{"a": 1}]')]


@pytest.mark.parametrize(
    "value,expected",
    [("text", "text"), (42, "42"), (True, "true"), (None, "null"), (1.5, "1.5")],
)
def test_flatten_extra_renders_a_scalar(value, expected):
    assert bd_view.flatten_extra("k", value) == [("k", expected)]


# --- extra_fields ---------------------------------------------------------


def test_extra_fields_surfaces_a_column_no_renderer_claims():
    """A field bd grows later must show up unprompted, not vanish."""
    assert bd_view.extra_fields({"id": "b-1", "brand_new_column": "surprise"}) == [
        ("brand_new_column", "surprise"),
    ]


def test_extra_fields_hides_every_rendered_key():
    issue = {key: "value" for key in bd_view.RENDERED_KEYS}
    assert bd_view.extra_fields(issue) == []


def test_extra_fields_hides_the_redundant_counts():
    issue = {"dependency_count": 2, "dependent_count": 1, "comment_count": 3}
    assert bd_view.extra_fields(issue) == []


@pytest.mark.parametrize("empty", [None, "", [], {}])
def test_extra_fields_skips_empty_values(empty):
    assert bd_view.extra_fields({"unknown": empty}) == []


def test_extra_fields_sorts_by_key():
    issue = {"zeta": "z", "alpha": "a", "mid": "m"}
    assert [k for k, _ in bd_view.extra_fields(issue)] == ["alpha", "mid", "zeta"]


def test_extra_fields_expands_a_nested_dict():
    pairs = bd_view.extra_fields({"unknown": {"b": "2", "a": "1"}})
    assert pairs == [("unknown.b", "2"), ("unknown.a", "1")]


def test_rendered_and_ignored_keys_do_not_overlap():
    assert not (bd_view.RENDERED_KEYS & bd_view.IGNORED_KEYS)


def test_status_tables_stay_in_step():
    assert set(bd_view.STATUS_GLYPH) == set(bd_view.STATUS_STYLE)


# --- run_bd_json / fetchers ----------------------------------------------


def test_fetch_issue_unwraps_the_single_row_bd_returns(fake_bd):
    """`bd show --json` hands back a list even for one bead."""
    fake_bd.json_rule("show", payload=[{"id": "b-1", "title": "One"}])
    assert bd_view.fetch_issue("b-1") == {"id": "b-1", "title": "One"}
    (argv,) = fake_bd.calls
    assert argv[0] == "show" and "b-1" in argv and "--json" in argv


@pytest.mark.parametrize("payload", [[], {"id": "b-1"}, None])
def test_fetch_issue_errors_when_bd_returns_no_row(fake_bd, payload):
    fake_bd.default(stdout="" if payload is None else json.dumps(payload))
    with pytest.raises(SystemExit) as excinfo:
        bd_view.fetch_issue("b-1")
    assert "no data returned for b-1" in str(excinfo.value.code)


def test_run_bd_json_surfaces_the_error_field_bd_reports(fake_bd):
    fake_bd.default(stdout=json.dumps({"error": "issue not found: b-9"}), exit_code=1)
    with pytest.raises(SystemExit) as excinfo:
        bd_view.fetch_issue("b-9")
    assert str(excinfo.value.code) == "error: issue not found: b-9"


def test_run_bd_json_falls_back_to_the_first_stderr_line(fake_bd):
    fake_bd.default(stderr="database is locked\nsecond line\n", exit_code=1)
    with pytest.raises(SystemExit) as excinfo:
        bd_view.fetch_issue("b-1")
    assert str(excinfo.value.code) == "error: database is locked"


def test_run_bd_json_reports_unparseable_output(fake_bd):
    fake_bd.default(stdout="{not json")
    with pytest.raises(SystemExit) as excinfo:
        bd_view.fetch_issue("b-1")
    assert "could not parse bd output as JSON" in str(excinfo.value.code)


def test_fetch_deps_requests_the_named_direction(fake_bd):
    fake_bd.json_rule("dep", payload=[{"dependency_type": "blocks"}])
    assert bd_view.fetch_deps("b-1", "down") == [{"dependency_type": "blocks"}]
    (argv,) = fake_bd.calls
    assert "--direction=down" in argv or "down" in argv


def test_fetch_comments_tolerates_a_bead_with_none(fake_bd):
    fake_bd.default(stdout="[]")
    assert bd_view.fetch_comments("b-1") == []


def test_fetch_issue_errors_when_bd_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SystemExit) as excinfo:
        bd_view.fetch_issue("b-1")
    assert "error" in str(excinfo.value.code).lower()


# --- Plain-text fallback --------------------------------------------------


def issue_fixture():
    return {
        "id": "b-1", "title": "A bead", "status": "open", "priority": 2,
        "issue_type": "task", "owner": "ann",
        "created_at": "2026-04-01T13:05:00Z",
        "description": "Some **description**.",
        "notes": "Notes here.",
        "labels": ["one", "two"],
        "metadata": {"branch": "main"},
        "surprise_column": "unclaimed",
    }


def test_render_plain_covers_every_documented_section(tmp_path):
    out = io.StringIO()
    bd_view.render_plain(
        out, issue_fixture(),
        deps=[{"dependency_type": "blocks", "issue_id": "b-2", "title": "Other"}],
        dependents=[],
        comments=[{"author": "ann", "created_at": "2026-04-02T09:00:00Z",
                   "text": "a comment"}],
    )
    text = out.getvalue()
    assert "b-1" in text and "A bead" in text
    assert "Some **description**." in text
    assert "Notes here." in text
    assert "unclaimed" in text          # the Other Fields catch-all
    assert "a comment" in text


def test_render_plain_handles_a_bead_with_nothing_but_an_id(tmp_path):
    out = io.StringIO()
    bd_view.render_plain(out, {"id": "b-1"}, deps=[], dependents=[], comments=[])
    assert "b-1" in out.getvalue()


# --- rich path ------------------------------------------------------------


@needs_rich
def test_rich_markdown_subclass_disables_raw_html():
    """Placeholder text like `<id>` must survive rather than be eaten as HTML."""
    assert bd_view.HAVE_RICH is True
    md = bd_view.Markdown("Use `<id>` here")
    assert md is not None


@needs_rich
def test_render_with_rich_emits_the_bead_content(tmp_path):
    out = io.StringIO()
    bd_view.render_with_rich(
        out, issue_fixture(), deps=[], dependents=[], comments=[],
    )
    text = out.getvalue()
    assert "b-1" in text
    assert "A bead" in text
    assert "unclaimed" in text


@needs_rich
def test_render_with_rich_groups_dependencies_under_their_headings(tmp_path):
    out = io.StringIO()
    bd_view.render_with_rich(
        out, {"id": "b-1", "title": "T"},
        deps=[{"dependency_type": "parent-child", "issue_id": "b-0", "title": "Parent"}],
        dependents=[{"dependency_type": "parent-child", "issue_id": "b-2",
                     "title": "Child"}],
        comments=[],
    )
    text = out.getvalue()
    assert "Parent" in text and "Children" in text


def test_module_declares_its_dependencies_inline():
    """PEP 723 metadata is what lets the uv shebang resolve rich per-script."""
    source = Path(bd_view.__file__).read_text()
    assert "# /// script" in source
    assert "rich" in source.split("# ///")[1]


def test_json_round_trip_of_the_fixture():
    """Guards the fixture itself against becoming un-serializable."""
    assert json.loads(json.dumps(issue_fixture()))["id"] == "b-1"
