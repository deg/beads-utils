"""Tests for bd-dolt-diff.

The interesting logic is `diff_table`, which has to survive two things real
Dolt data does to it: surrogate `id` columns that differ per-clone for the
same logical row, and schema migrations that leave the two revisions with
different column sets (selecting a column absent on one side is a hard error).
"""
from __future__ import annotations

import io
import json

import pytest

from conftest import load_script

bd_dolt_diff = load_script("bd-dolt-diff")


# --- shorten --------------------------------------------------------------


@pytest.mark.parametrize("value", [None, ""])
def test_shorten_labels_an_empty_cell(value):
    assert bd_dolt_diff.shorten(value, full=False) == "(empty)"


def test_shorten_collapses_newlines_so_a_cell_stays_on_one_line():
    assert bd_dolt_diff.shorten("a\nb\r\nc", full=False) == "a b  c"


def test_shorten_truncates_past_the_limit_and_marks_it():
    text = "x" * (bd_dolt_diff.TRUNCATE_AT + 50)
    out = bd_dolt_diff.shorten(text, full=False)
    assert out == "x" * bd_dolt_diff.TRUNCATE_AT + "..."


def test_shorten_leaves_a_value_at_exactly_the_limit_alone():
    text = "x" * bd_dolt_diff.TRUNCATE_AT
    assert bd_dolt_diff.shorten(text, full=False) == text


def test_shorten_keeps_everything_when_full_is_requested():
    text = "x" * 500
    assert bd_dolt_diff.shorten(text, full=True) == text


def test_shorten_stringifies_non_text_values():
    assert bd_dolt_diff.shorten(42, full=False) == "42"
    assert bd_dolt_diff.shorten(0, full=False) == "0"


# --- row_key --------------------------------------------------------------


def test_row_key_builds_a_tuple_in_column_order():
    row = {"issue_id": "b-1", "label": "urgent"}
    assert bd_dolt_diff.row_key(row, ("issue_id", "label")) == ("b-1", "urgent")


def test_row_key_uses_none_for_a_column_the_row_lacks():
    """Dolt's JSON output omits NULL columns entirely, so .get() is required."""
    assert bd_dolt_diff.row_key({"issue_id": "b-1"}, ("issue_id", "label")) == ("b-1", None)


# --- TableSpec ------------------------------------------------------------


def test_dependency_key_excludes_the_surrogate_id():
    """Dolt mints a fresh uuid() per insert, so the same logical edge on two
    clones would otherwise read as a spurious add + remove pair."""
    spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "dependencies")
    assert "id" not in spec.key
    assert "id" in spec.ignore


def test_comment_key_excludes_the_surrogate_id():
    spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "comments")
    assert "id" not in spec.key
    assert "id" in spec.ignore


def test_issue_spec_ignores_the_derived_content_hash():
    spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "issues")
    assert spec.ignore == {"content_hash"}


# --- diff_table -----------------------------------------------------------


class FakeDoltDb:
    """Stands in for the dolt plumbing: columns and rows per revision."""

    def __init__(self, columns: dict[str, list[str]], rows: dict[str, list[dict]]):
        self.columns = columns
        self.rows = rows
        self.queries: list[str] = []

    def install(self, monkeypatch):
        # bd-dolt-diff does `from bdutils import ...`, so the patch target is
        # the attribute on the *script* module, not on bdutils.
        monkeypatch.setattr(
            bd_dolt_diff, "dolt_table_columns",
            lambda db, table, rev=None: list(self.columns.get(rev, [])),
        )
        monkeypatch.setattr(bd_dolt_diff, "dolt_sql_json", self._sql)
        return self

    def _sql(self, db, query):
        self.queries.append(query)
        for rev, rows in self.rows.items():
            if f"as of '{rev}'" in query:
                return [dict(r) for r in rows]
        return None


def spec(name="issues", key=("id",), ignore=()):
    return bd_dolt_diff.TableSpec(name, key=key, ignore=ignore)


def test_diff_table_reports_added_removed_and_changed_rows(monkeypatch):
    db = FakeDoltDb(
        columns={"base": ["id", "status", "title"], "head": ["id", "status", "title"]},
        rows={
            "base": [
                {"id": "b-1", "status": "open", "title": "One"},
                {"id": "b-2", "status": "open", "title": "Two"},
            ],
            "head": [
                {"id": "b-1", "status": "closed", "title": "One"},
                {"id": "b-3", "status": "open", "title": "Three"},
            ],
        },
    ).install(monkeypatch)
    added, removed, changed, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert [r["id"] for r in added] == ["b-3"]
    assert [r["id"] for r in removed] == ["b-2"]
    assert len(changed) == 1
    key, row, deltas = changed[0]
    assert key == ("b-1",)
    assert deltas == {"status": ("open", "closed")}
    assert note is None


def test_diff_table_reports_nothing_when_the_revisions_agree(monkeypatch):
    rows = [{"id": "b-1", "status": "open"}]
    db = FakeDoltDb(
        columns={"base": ["id", "status"], "head": ["id", "status"]},
        rows={"base": rows, "head": rows},
    ).install(monkeypatch)
    added, removed, changed, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert (added, removed, changed, note) == ([], [], [], None)


def test_diff_table_ignores_the_columns_the_spec_excludes(monkeypatch):
    db = FakeDoltDb(
        columns={"base": ["id", "content_hash"], "head": ["id", "content_hash"]},
        rows={
            "base": [{"id": "b-1", "content_hash": "aaa"}],
            "head": [{"id": "b-1", "content_hash": "bbb"}],
        },
    ).install(monkeypatch)
    _, _, changed, note = bd_dolt_diff.diff_table(
        db, spec(ignore=("content_hash",)), "base", "head",
    )
    assert changed == []
    assert note is None


def test_diff_table_compares_the_column_intersection_after_a_migration(monkeypatch):
    """Selecting a column absent from one revision is a hard error in Dolt."""
    db = FakeDoltDb(
        columns={"base": ["id", "status"], "head": ["id", "status", "new_col"]},
        rows={
            "base": [{"id": "b-1", "status": "open"}],
            "head": [{"id": "b-1", "status": "closed", "new_col": "x"}],
        },
    ).install(monkeypatch)
    _, _, changed, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert changed[0][2] == {"status": ("open", "closed")}
    assert note == "schema differs between revisions; not compared: new_col"
    assert all("new_col" not in q for q in db.queries)


def test_diff_table_names_every_skipped_column(monkeypatch):
    db = FakeDoltDb(
        columns={"base": ["id", "gone"], "head": ["id", "added"]},
        rows={"base": [], "head": []},
    ).install(monkeypatch)
    *_, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert note.endswith("added, gone")


def test_diff_table_reports_a_table_missing_from_both_revisions(monkeypatch):
    db = FakeDoltDb(columns={}, rows={}).install(monkeypatch)
    added, removed, changed, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert (added, removed, changed) == (None, None, None)
    assert note == "table not present at either revision"


def test_diff_table_names_the_revision_a_table_is_missing_from(monkeypatch):
    db = FakeDoltDb(columns={"head": ["id"]}, rows={"head": []}).install(monkeypatch)
    *_, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert "missing at base" in note


def test_diff_table_gives_up_when_no_key_column_survives(monkeypatch):
    db = FakeDoltDb(
        columns={"base": ["other"], "head": ["other"]},
        rows={"base": [], "head": []},
    ).install(monkeypatch)
    *_, note = bd_dolt_diff.diff_table(db, spec(key=("id",)), "base", "head")
    assert note == "no usable key column at both revisions"


def test_diff_table_reports_a_failed_query(monkeypatch):
    db = FakeDoltDb(
        columns={"base": ["id"], "head": ["id"]},
        rows={"base": [{"id": "b-1"}]},  # no rows registered for head -> None
    ).install(monkeypatch)
    added, removed, changed, note = bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert (added, removed, changed) == (None, None, None)
    assert note == "query failed"


def test_diff_table_treats_a_same_edge_with_a_different_surrogate_id_as_unchanged(
        monkeypatch):
    """The whole reason dependencies key on their semantic tuple."""
    dep_spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "dependencies")
    cols = ["id", "issue_id", "type", "depends_on_issue_id",
            "depends_on_wisp_id", "depends_on_external"]
    edge = {
        "issue_id": "b-1", "type": "blocks", "depends_on_issue_id": "b-2",
        "depends_on_wisp_id": None, "depends_on_external": None,
    }
    db = FakeDoltDb(
        columns={"base": cols, "head": cols},
        rows={
            "base": [dict(edge, id="uuid-from-clone-a")],
            "head": [dict(edge, id="uuid-from-clone-b")],
        },
    ).install(monkeypatch)
    added, removed, changed, _ = bd_dolt_diff.diff_table(db, dep_spec, "base", "head")
    assert (added, removed, changed) == ([], [], [])


def test_diff_table_escapes_a_quote_in_the_revision_name(monkeypatch):
    db = FakeDoltDb(
        columns={"it's": ["id"], "head": ["id"]},
        rows={"it's": [], "head": []},
    ).install(monkeypatch)
    bd_dolt_diff.diff_table(db, spec(), "it's", "head")
    assert any("as of 'it''s'" in q for q in db.queries)


def test_diff_table_backquotes_column_and_table_names(monkeypatch):
    db = FakeDoltDb(
        columns={"base": ["id"], "head": ["id"]},
        rows={"base": [], "head": []},
    ).install(monkeypatch)
    bd_dolt_diff.diff_table(db, spec(), "base", "head")
    assert any("select `id` from `issues`" in q for q in db.queries)


# --- fetch_rows -----------------------------------------------------------


def test_fetch_rows_keys_rows_by_the_key_columns(monkeypatch):
    db = FakeDoltDb(
        columns={"r": ["id"]},
        rows={"r": [{"id": "b-1", "status": "open"}, {"id": "b-2", "status": "closed"}]},
    ).install(monkeypatch)
    out = bd_dolt_diff.fetch_rows(db, "issues", "r", ["id", "status"], ("id",))
    assert set(out) == {("b-1",), ("b-2",)}


def test_fetch_rows_collapses_rows_that_share_a_key(monkeypatch):
    """Last one wins -- acceptable for a push preview, documented in the source."""
    db = FakeDoltDb(
        columns={"r": ["id"]},
        rows={"r": [{"id": "b-1", "status": "open"}, {"id": "b-1", "status": "closed"}]},
    ).install(monkeypatch)
    out = bd_dolt_diff.fetch_rows(db, "issues", "r", ["id", "status"], ("id",))
    assert out[("b-1",)]["status"] == "closed"


def test_fetch_rows_returns_none_when_the_query_fails(monkeypatch):
    db = FakeDoltDb(columns={}, rows={}).install(monkeypatch)
    assert bd_dolt_diff.fetch_rows(db, "issues", "nope", ["id"], ("id",)) is None


# --- Rendering ------------------------------------------------------------


def test_describe_issue_pads_the_status_column():
    assert bd_dolt_diff.describe_issue({"status": "open", "title": "T"}) == "open    T"


def test_describe_issue_marks_absent_fields():
    assert bd_dolt_diff.describe_issue({}).startswith("?")


def test_render_issues_marks_adds_removes_and_changes():
    out = io.StringIO()
    bd_dolt_diff.render_issues(
        out,
        added=[{"id": "b-3", "status": "open", "title": "New"}],
        removed=[{"id": "b-2", "status": "open", "title": "Gone"}],
        changed=[(("b-1",), {"id": "b-1", "status": "closed", "title": "One"},
                  {"status": ("open", "closed")})],
        full=False,
    )
    text = out.getvalue()
    assert "  + b-3" in text
    assert "  - b-2" in text
    assert "  ~ b-1" in text
    assert "was: open" in text and "now: closed" in text


def test_render_issues_sorts_each_section_by_id():
    out = io.StringIO()
    bd_dolt_diff.render_issues(
        out,
        added=[{"id": "b-9"}, {"id": "b-1"}],
        removed=[], changed=[], full=False,
    )
    lines = out.getvalue().splitlines()
    assert lines[0].split()[1] == "b-1"


def test_render_generic_identifies_rows_by_their_key_tuple():
    out = io.StringIO()
    label_spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "labels")
    bd_dolt_diff.render_generic(
        out, label_spec,
        added=[{"issue_id": "b-1", "label": "urgent"}],
        removed=[], changed=[], full=False,
    )
    assert out.getvalue() == "  + issue_id=b-1  label=urgent\n"


def test_render_generic_omits_empty_key_components():
    """A dependency key has three mutually exclusive target columns."""
    out = io.StringIO()
    dep_spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "dependencies")
    bd_dolt_diff.render_generic(
        out, dep_spec,
        added=[{"issue_id": "b-1", "type": "blocks", "depends_on_issue_id": "b-2",
                "depends_on_wisp_id": None, "depends_on_external": ""}],
        removed=[], changed=[], full=False,
    )
    line = out.getvalue()
    assert "depends_on_wisp_id" not in line
    assert "depends_on_external" not in line
    assert "depends_on_issue_id=b-2" in line


def test_render_generic_shows_a_change_as_before_arrow_after():
    out = io.StringIO()
    label_spec = next(s for s in bd_dolt_diff.TABLE_SPECS if s.name == "labels")
    bd_dolt_diff.render_generic(
        out, label_spec, added=[], removed=[],
        changed=[(("b-1", "x"), {"issue_id": "b-1", "label": "x"},
                  {"note": ("before", "after")})],
        full=False,
    )
    assert "note: before -> after" in out.getvalue()


def test_table_specs_cover_the_four_beads_tables():
    assert [s.name for s in bd_dolt_diff.TABLE_SPECS] == [
        "issues", "dependencies", "labels", "comments",
    ]


def test_json_module_is_not_needed_to_read_a_spec():
    """Guard against a spec accidentally becoming JSON-encoded config."""
    assert isinstance(bd_dolt_diff.TABLE_SPECS[0].key, tuple)
    assert json.dumps(list(bd_dolt_diff.TABLE_SPECS[0].key)) == '["id"]'
