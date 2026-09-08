"""Tests for bd-log.

The first class here is the reason the suite exists (bead beads-utils-86m):
four `select_subtrees` behaviors that this repo's own bead data cannot
exercise, because it has exactly one dotted hierarchy, no reparented beads and
no non-dotted children. Two of the four correspond to defects that were found
only by an ad-hoc check during beads-utils-52x, so the coverage is
load-bearing rather than decorative.
"""
from __future__ import annotations

import json
import threading

import pytest

import bdutils

from conftest import load_script

bd_log = load_script("bd-log")


def issue(iid, parent=None, **fields):
    """A minimal `bd list --json` row: an id, an optional parent, extras."""
    row = {"id": iid}
    if parent is not None:
        row["parent"] = parent
    row.update(fields)
    return row


# --- The four checks live data can't reach --------------------------------


class TestSelectSubtreesBranches:
    """The branches of select_subtrees() that real bead data cannot reach."""

    def test_scope_filter_on_intermediate_does_not_sever_deeper_descendants(self):
        """A hidden middle bead must not cut the chain to what's below it.

        This is why the walk runs over `topology` (the unfiltered
        `bd list --all` set) and only the final membership test is scoped.
        Walking the scoped set instead would lose `deep` entirely, because the
        only path to it runs through a bead that --open/--status filtered out.
        """
        topology = [
            issue("p-root"),
            issue("p-middle", parent="p-root"),
            issue("p-deep", parent="p-middle"),
        ]
        # `p-middle` is closed, so a scope filter such as --open dropped it.
        scoped = [issue("p-root"), issue("p-deep", parent="p-middle")]

        kept, members = bd_log.select_subtrees(scoped, topology, ["p-root"])

        assert [i["id"] for i in kept] == ["p-root", "p-deep"]
        assert members["p-root"] == {"p-root", "p-deep"}

    def test_chain_of_entirely_non_dotted_ids_resolves(self):
        """Parentage comes from the `parent` field, never from id text.

        Nothing in these ids hints at the hierarchy -- there is not a dot in
        sight -- so an implementation that inferred structure from the id
        string would return only the root.
        """
        topology = [
            issue("alpha"),
            issue("bravo", parent="alpha"),
            issue("charlie", parent="bravo"),
            issue("delta"),  # unrelated, must not be swept in
        ]

        kept, members = bd_log.select_subtrees(topology, topology, ["alpha"])

        assert {i["id"] for i in kept} == {"alpha", "bravo", "charlie"}
        assert members["alpha"] == {"alpha", "bravo", "charlie"}

    def test_reparented_bead_is_not_claimed_by_the_parent_its_id_names(self):
        """`bd update --parent` reparents without renumbering.

        So `proj-a1b.4` can end up as a child of `proj-zzz` while keeping an id
        that still spells out `proj-a1b`. The moved bead must follow its
        `parent` field, not its name -- it belongs to the new parent's subtree
        and must be absent from the old one's.
        """
        topology = [
            issue("proj-a1b"),
            issue("proj-a1b.1", parent="proj-a1b"),
            issue("proj-zzz"),
            issue("proj-a1b.4", parent="proj-zzz"),  # moved out of proj-a1b
        ]

        kept_old, members_old = bd_log.select_subtrees(topology, topology, ["proj-a1b"])
        assert {i["id"] for i in kept_old} == {"proj-a1b", "proj-a1b.1"}
        assert "proj-a1b.4" not in members_old["proj-a1b"]

        kept_new, members_new = bd_log.select_subtrees(topology, topology, ["proj-zzz"])
        assert {i["id"] for i in kept_new} == {"proj-zzz", "proj-a1b.4"}
        assert members_new["proj-zzz"] == {"proj-zzz", "proj-a1b.4"}

    def test_parent_cycle_terminates(self):
        """A cycle must exhaust the walk, not spin forever.

        bd should never emit one, but nothing in bd-log guarantees that, so
        the `seen` set bounds the traversal. Run on a worker thread with a
        deadline: a regression here would otherwise hang the whole suite
        rather than failing one test.
        """
        topology = [
            issue("c-a", parent="c-b"),
            issue("c-b", parent="c-a"),
            issue("c-c", parent="c-b"),
        ]
        result = {}

        def walk():
            result["value"] = bd_log.select_subtrees(topology, topology, ["c-a"])

        worker = threading.Thread(target=walk, daemon=True)
        worker.start()
        worker.join(timeout=10)

        assert not worker.is_alive(), "select_subtrees did not terminate on a parent cycle"
        kept, members = result["value"]
        assert {i["id"] for i in kept} == {"c-a", "c-b", "c-c"}
        assert members["c-a"] == {"c-a", "c-b", "c-c"}


class TestSelectSubtreesGeneral:
    """The ordinary paths, which live data does cover."""

    def test_root_absent_from_topology_yields_an_empty_claim(self):
        topology = [issue("p-1")]
        kept, members = bd_log.select_subtrees(topology, topology, ["p-nope"])
        assert kept == []
        assert members["p-nope"] == set()

    def test_root_outside_the_scope_still_claims_its_in_scope_descendants(self):
        topology = [issue("p-root"), issue("p-kid", parent="p-root")]
        scoped = [issue("p-kid", parent="p-root")]
        kept, members = bd_log.select_subtrees(scoped, topology, ["p-root"])
        assert [i["id"] for i in kept] == ["p-kid"]
        assert members["p-root"] == {"p-kid"}

    def test_multiple_roots_union_their_subtrees_and_report_separately(self):
        topology = [
            issue("r-1"), issue("r-1.1", parent="r-1"),
            issue("r-2"), issue("r-2.1", parent="r-2"),
            issue("r-3"),
        ]
        kept, members = bd_log.select_subtrees(topology, topology, ["r-1", "r-2"])
        assert {i["id"] for i in kept} == {"r-1", "r-1.1", "r-2", "r-2.1"}
        assert members["r-1"] == {"r-1", "r-1.1"}
        assert members["r-2"] == {"r-2", "r-2.1"}

    def test_overlapping_roots_do_not_duplicate_the_kept_rows(self):
        topology = [issue("o-1"), issue("o-1.1", parent="o-1")]
        kept, _ = bd_log.select_subtrees(topology, topology, ["o-1", "o-1.1"])
        assert [i["id"] for i in kept] == ["o-1", "o-1.1"]

    def test_kept_rows_preserve_the_input_order(self):
        topology = [issue("k-3", parent="k-1"), issue("k-1"), issue("k-2", parent="k-1")]
        kept, _ = bd_log.select_subtrees(topology, topology, ["k-1"])
        assert [i["id"] for i in kept] == ["k-3", "k-1", "k-2"]

    def test_rows_without_an_id_are_ignored_rather_than_matching_a_root(self):
        """issue_id() normalizes a missing id to '', which must not match."""
        topology = [issue("n-1"), {"parent": "n-1", "title": "id-less"}]
        kept, members = bd_log.select_subtrees(topology, topology, ["n-1"])
        assert [i["id"] for i in kept] == ["n-1"]
        assert members["n-1"] == {"n-1"}

    def test_an_empty_root_cannot_reach_select_subtrees(self):
        """issue_id() maps a missing id to '', which an empty root would match.

        That is only harmless because '' can never arrive: parse_ids() drops
        empty entries and errors when nothing is left, so `--id ,,` fails at
        the boundary instead of passing '' down. Pinned here -- along with what
        the walk would actually do -- so a future loosening of parse_ids does
        not quietly open the path.
        """
        with pytest.raises(SystemExit):
            bd_log.parse_ids(",,")

        topology = [issue("e-1"), {"title": "id-less"}]
        kept, members = bd_log.select_subtrees(topology, topology, [""])
        assert kept == [{"title": "id-less"}]  # documented, not endorsed
        assert members[""] == {""}


# --- issue_id / collapse --------------------------------------------------


@pytest.mark.parametrize(
    "row,expected",
    [
        ({"id": "x-1"}, "x-1"),
        ({}, ""),
        ({"id": None}, ""),
        ({"id": ""}, ""),
    ],
)
def test_issue_id_normalizes_missing_ids_to_empty_string(row, expected):
    assert bd_log.issue_id(row) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("plain", "plain"),
        ("two   spaces", "two spaces"),
        ("line\nbreak", "line break"),
        ("  padded  ", "padded"),
        ("", ""),
        ("tab\tsep", "tab sep"),
    ],
)
def test_collapse_folds_all_whitespace_runs_to_single_spaces(text, expected):
    assert bd_log.collapse(text) == expected


# --- scope_args -----------------------------------------------------------


@pytest.mark.parametrize(
    "status,open_only,expected",
    [
        (None, False, ["--all"]),          # default: everything, incl. closed
        (None, True, []),                  # --open: bd's own default is "not closed"
        ("in_progress", False, ["--status=in_progress"]),
        ("open,in_progress", False, ["--status=open,in_progress"]),
        # --status wins if both somehow arrive; argparse makes them exclusive.
        ("open", True, ["--status=open"]),
    ],
)
def test_scope_args_maps_each_scope_to_bd_list_flags(status, open_only, expected):
    assert bd_log.scope_args(status, open_only) == expected


# --- drop_deferred --------------------------------------------------------


def test_drop_deferred_removes_only_the_deferred_status():
    rows = [
        issue("p-open", status="open"),
        issue("p-parked", status="deferred"),
        issue("p-busy", status="in_progress"),
        issue("p-blocked", status="blocked"),
        issue("p-done", status="closed"),
    ]
    kept = bd_log.drop_deferred(rows)
    assert [i["id"] for i in kept] == ["p-open", "p-busy", "p-blocked", "p-done"]


def test_drop_deferred_keeps_a_row_with_no_status_field():
    """Only a *known* deferred status is dropped; an absent one is not a guess."""
    rows = [issue("p-1"), issue("p-2", status=None)]
    assert bd_log.drop_deferred(rows) == rows


def test_drop_deferred_leaves_a_custom_status_alone():
    """bd has custom statuses; the filter names exactly one and passes the rest."""
    rows = [issue("p-1", status="pinned"), issue("p-2", status="hooked")]
    assert bd_log.drop_deferred(rows) == rows


def test_drop_deferred_of_nothing_is_nothing():
    assert bd_log.drop_deferred([]) == []


# --- parse_only / parse_ids ----------------------------------------------


def test_parse_only_accepts_the_verbs_and_trims_whitespace():
    assert bd_log.parse_only("create, end") == {"create", "end"}
    assert bd_log.parse_only("change") == {"change"}
    assert bd_log.parse_only("create,change,end") == set(bd_log.VERBS)


def test_parse_only_still_accepts_the_pre_grid_kind_names():
    """`--only=start,close` predates the entity axis and must keep working.

    Those two spellings are in the epilog, in CLAUDE.md and in both completion
    files, so they are an interface, not an implementation detail.
    """
    assert bd_log.parse_only("start") == {"change"}
    assert bd_log.parse_only("close") == {"end"}
    assert bd_log.parse_only("create,start,close") == set(bd_log.VERBS)


def test_parse_only_rejects_an_unknown_verb_by_name():
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_only("create,finish")
    assert "finish" in str(excinfo.value.code)
    assert str(excinfo.value.code).startswith("error: ")


def test_parse_only_rejects_a_memory_kind_name():
    """The entity lives on --about; `--only=remember` would blur the axes."""
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_only("remember")
    assert "remember" in str(excinfo.value.code)


@pytest.mark.parametrize("value", ["", ",", "  ", ", ,"])
def test_parse_only_rejects_an_empty_list(value):
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_only(value)
    assert "at least one event verb" in str(excinfo.value.code)


# --- parse_about / select_kinds ------------------------------------------


def test_parse_about_accepts_both_entities_and_their_singulars():
    assert bd_log.parse_about("beads,memories") == {"beads", "memories"}
    assert bd_log.parse_about("memory") == {"memories"}
    assert bd_log.parse_about(" bead ") == {"beads"}


def test_parse_about_rejects_an_unknown_entity_by_name():
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_about("beads,widgets")
    assert "widgets" in str(excinfo.value.code)


@pytest.mark.parametrize("value", ["", ",", "  "])
def test_parse_about_rejects_an_empty_list(value):
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_about(value)
    assert "at least one entity" in str(excinfo.value.code)


def test_select_kinds_picks_the_named_cells_of_the_grid():
    assert bd_log.select_kinds({"beads"}, {"create"}) == {"create"}
    assert bd_log.select_kinds({"memories"}, {"create"}) == {"remember"}
    assert bd_log.select_kinds({"memories"}, {"change", "end"}) == {"revise", "forget"}
    assert bd_log.select_kinds(set(bd_log.ENTITIES), set(bd_log.VERBS)) == set(
        bd_log.EVENT_KINDS
    )


@pytest.mark.parametrize("value", ["", "   "])
def test_parse_status_rejects_an_empty_value(value):
    """`--status="$UNSET_VAR"` must fail by name, not widen the log.

    Read as absent it is doubly wrong: scope_args falls through to --all, and
    --status drops out of the filters implying --about=beads -- so a typo that
    looks like a narrowing returned every bead *plus* the whole memory log,
    silently. --id has always been guarded this way; --status was not.
    """
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_status(value)
    assert "--status must name at least one status" in str(excinfo.value.code)


def test_parse_status_passes_a_real_value_through_untouched():
    """bd owns the vocabulary -- this guard checks emptiness, nothing more."""
    assert bd_log.parse_status("open,in_progress") == "open,in_progress"
    assert bd_log.parse_status("whatever-bd-allows") == "whatever-bd-allows"


def test_parse_ids_dedupes_while_preserving_the_order_given():
    assert bd_log.parse_ids("b-2, b-1 ,b-2,b-3") == ["b-2", "b-1", "b-3"]


@pytest.mark.parametrize("value", ["", ",", "   ", ",,"])
def test_parse_ids_rejects_an_empty_list(value):
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_ids(value)
    assert "at least one bead id" in str(excinfo.value.code)


# --- synthesize_events ----------------------------------------------------


def test_synthesize_events_emits_one_event_per_non_empty_timestamp():
    issues = [
        issue("a-1", created_at="2026-01-01T00:00:00Z",
              started_at="2026-01-02T00:00:00Z", closed_at="2026-01-03T00:00:00Z"),
    ]
    events = bd_log.synthesize_events(issues, set(bd_log.EVENT_KINDS))
    assert {(kind, ts) for ts, kind, _ in events} == {
        ("create", "2026-01-01T00:00:00Z"),
        ("start", "2026-01-02T00:00:00Z"),
        ("close", "2026-01-03T00:00:00Z"),
    }


@pytest.mark.parametrize("missing", [None, ""])
def test_synthesize_events_skips_absent_and_blank_timestamps(missing):
    issues = [issue("a-1", created_at="2026-01-01T00:00:00Z",
                    started_at=missing, closed_at=missing)]
    events = bd_log.synthesize_events(issues, set(bd_log.EVENT_KINDS))
    assert [kind for _, kind, _ in events] == ["create"]


def test_synthesize_events_honors_the_requested_kinds():
    issues = [issue("a-1", created_at="2026-01-01T00:00:00Z",
                    started_at="2026-01-02T00:00:00Z",
                    closed_at="2026-01-03T00:00:00Z")]
    events = bd_log.synthesize_events(issues, {"close"})
    assert [kind for _, kind, _ in events] == ["close"]


def test_synthesize_events_carries_the_originating_issue_through():
    row = issue("a-1", created_at="2026-01-01T00:00:00Z", title="hello")
    (_, _, carried), = bd_log.synthesize_events([row], {"create"})
    assert carried is row


def test_synthesize_events_returns_nothing_for_no_issues():
    assert bd_log.synthesize_events([], set(bd_log.EVENT_KINDS)) == []


# --- event_actor ----------------------------------------------------------


@pytest.mark.parametrize(
    "kind,row,expected",
    [
        ("create", {"created_by": "ann", "owner": "bob"}, "ann"),
        ("create", {"owner": "bob"}, "bob"),
        ("create", {"created_by": "", "owner": "bob"}, "bob"),
        ("create", {}, ""),
        ("start", {"assignee": "cat", "owner": "bob"}, "cat"),
        ("start", {"owner": "bob"}, "bob"),
        ("close", {"assignee": "cat", "created_by": "ann"}, "cat"),
        ("close", {}, ""),
    ],
)
def test_event_actor_prefers_the_field_that_matches_the_event(kind, row, expected):
    assert bd_log.event_actor(kind, row) == expected


# --- render ---------------------------------------------------------------


def test_render_lays_out_the_header_then_the_title():
    row = issue("a-1", priority=1, issue_type="bug", assignee="ann", title="Fix   it")
    lines = bd_log.render("2026-04-01T13:05:00Z", "start", row)
    assert lines == ["▶ 2026-04-01 13:05  a-1  P1 bug  ann", "  Fix it"]


def test_render_omits_the_actor_segment_when_there_is_none():
    row = issue("a-1", priority=2, issue_type="task", title="Anon")
    head = bd_log.render("2026-04-01T13:05:00Z", "create", row)[0]
    assert head == "+ 2026-04-01 13:05  a-1  P2 task"


def test_render_falls_back_for_a_missing_id_priority_and_title():
    lines = bd_log.render("2026-04-01T13:05:00Z", "create", {})
    assert lines[0] == "+ 2026-04-01 13:05  ?  P?"
    assert lines[1] == "  (no title)"


def test_render_appends_a_close_reason_only_on_close_events():
    row = issue("a-1", title="Done", close_reason="superseded  by   b-2")
    assert bd_log.render("2026-04-01T13:05:00Z", "close", row)[2] == "  superseded by b-2"
    assert len(bd_log.render("2026-04-01T13:05:00Z", "create", row)) == 2


def test_render_omits_an_empty_close_reason():
    row = issue("a-1", title="Done", close_reason="")
    assert len(bd_log.render("2026-04-01T13:05:00Z", "close", row)) == 2


@pytest.mark.parametrize(
    "kind,code",
    [("create", "\033[34m"), ("start", "\033[32m"), ("close", "\033[31m")],
)
def test_render_tints_every_line_of_the_entry_by_event_kind(kind, code):
    """Traffic-light hues, and the *whole* entry is colored, not just the stamp.

    Both are deliberate: a ~18-character stamp is too little area to judge a
    hue against, and green/yellow are indistinguishable in Solarized Light.
    """
    row = issue("a-1", title="Colored", close_reason="because")
    lines = bd_log.render("2026-04-01T13:05:00Z", kind, row, color=True)
    for line in lines:
        assert line.startswith(code)
        assert line.endswith("\033[0m")


def test_render_emits_no_escapes_when_color_is_off():
    row = issue("a-1", title="Plain")
    for line in bd_log.render("2026-04-01T13:05:00Z", "close", row, color=False):
        assert "\033[" not in line


# --- render_oneline -------------------------------------------------------


def test_render_oneline_lays_out_glyph_stamp_id_meta_and_title():
    row = issue("a-1", priority=1, issue_type="bug", title="Fix   it")
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "start", row, 3, 6)
    assert line == "▶ 2026-04-01 13:05  a-1  P1 bug  Fix it"


def test_render_oneline_drops_the_actor_and_the_close_reason():
    """The whole point of the flag: one row, whatever the entry carries."""
    row = issue("a-1", priority=1, issue_type="bug", assignee="ann",
                title="Done", close_reason="a whole paragraph of context")
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "close", row, 3, 6)
    assert "\n" not in line
    assert "ann" not in line
    assert "paragraph" not in line


def test_render_oneline_pads_the_id_and_meta_columns_to_the_given_widths():
    row = issue("a-1", priority=2, issue_type="task", title="T")
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "create", row, 8, 10)
    assert line == "+ 2026-04-01 13:05  a-1       P2 task     T"


@pytest.mark.parametrize("row", [{}, {"id": ""}, {"id": None}])
def test_display_id_falls_back_for_every_falsy_id(row):
    """'' and None are the cases plain .get('id', '?') lets through.

    A '' id would size the column to 0 and leave a four-space hole where the
    id belongs; a None would raise TypeError out of the join. Both render as
    '?' instead. Distinct from issue_id(), which normalizes to '' precisely so
    a falsy id cannot match a requested --id root.
    """
    assert bd_log.display_id(row) == "?"
    assert bd_log.issue_id(row) == ""


def test_render_oneline_always_has_a_meta_cell_to_render():
    """There is no empty-meta case to special-case, and that's load-bearing.

    format_priority() falls back to 'P?' rather than '', so event_meta() is
    never empty and meta_w is only 0 for an empty event list -- which main()
    returns early on. render_oneline can therefore pad unconditionally.
    """
    assert bd_log.event_meta("create", {}) == "P?"
    assert bd_log.event_meta("remember", {}) == "memory"
    assert bd_log.oneline_widths([("t", "create", {})]) == (1, 2)


def test_render_oneline_falls_back_for_a_missing_id_and_title():
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "create", {}, 1, 2)
    assert line == "+ 2026-04-01 13:05  ?  P?  (no title)"


@pytest.mark.parametrize(
    "kind,code",
    [("create", "\033[34m"), ("start", "\033[32m"), ("close", "\033[31m")],
)
def test_render_oneline_tints_the_row_by_event_kind(kind, code):
    """Same traffic-light hues as the block form, over the whole row.

    A row is ~70 colored chars against a block entry's ~160-240 -- still well
    above the area where hues stopped separating in Solarized Light, but it is
    the dimension that regressed before, so the color must reach end of line.
    """
    row = issue("a-1", title="Colored")
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", kind, row, 3, 6,
                                 color=True)
    assert line.startswith(code)
    assert line.endswith("\033[0m")


def test_render_oneline_emits_no_escapes_when_color_is_off():
    row = issue("a-1", title="Plain")
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "close", row, 3, 6)
    assert "\033[" not in line


def test_oneline_widths_size_each_column_to_its_widest_value():
    events = [
        ("2026-04-01T00:00:00Z", "create", issue("a-1", priority=2,
                                                 issue_type="task")),
        ("2026-04-01T00:00:00Z", "create", issue("project-longer-id",
                                                 priority=1,
                                                 issue_type="feature")),
    ]
    assert bd_log.oneline_widths(events) == (len("project-longer-id"),
                                             len("P1 feature"))


def test_oneline_widths_of_nothing_are_zero():
    assert bd_log.oneline_widths([]) == (0, 0)


def test_event_kind_tables_stay_in_step_with_each_other():
    """Every kind needs a glyph, an order and a color.

    Not a timestamp field: beads carry their own, while memory events are
    reconstructed from Dolt commit dates, so EVENT_TS_FIELD covers the beads
    row of the grid alone.
    """
    for table in (bd_log.EVENT_GLYPH, bd_log.EVENT_ORDER, bd_log.EVENT_COLOR,
                  bd_log.KIND_LABEL):
        assert set(table) == set(bd_log.EVENT_KINDS)
    assert set(bd_log.EVENT_TS_FIELD) == set(bd_log.BEAD_KINDS)


def test_the_grid_covers_every_entity_and_verb_exactly_once():
    """Both axes must be total, and no cell may be shared by two of them."""
    assert set(bd_log.KIND_BY_ENTITY_VERB) == set(bd_log.ENTITIES)
    cells = []
    for entity in bd_log.ENTITIES:
        assert set(bd_log.KIND_BY_ENTITY_VERB[entity]) == set(bd_log.VERBS)
        cells += list(bd_log.KIND_BY_ENTITY_VERB[entity].values())
    assert sorted(cells) == sorted(bd_log.EVENT_KINDS)


def test_color_is_keyed_on_the_verb_not_the_entity():
    """The palette stays at three hues because both rows share them.

    That is the whole reason the grid earns its keep visually: a fourth hue for
    memories would have to come from the plain 30-37 range, where the remaining
    candidates (yellow, cyan) are the two that Solarized Light renders as olive
    and as a near-blue. Entity rides on the glyph instead.
    """
    for verb in bd_log.VERBS:
        hues = {
            bd_log.EVENT_COLOR[bd_log.KIND_BY_ENTITY_VERB[entity][verb]]
            for entity in bd_log.ENTITIES
        }
        assert len(hues) == 1, f"{verb} is not one hue across entities"
    assert len(set(bd_log.EVENT_COLOR.values())) == len(bd_log.VERBS)


@pytest.mark.parametrize(
    "mode,tty,expected",
    [
        ("always", False, True),   # forced on through a pipe
        ("always", True, True),
        ("never", True, False),    # forced off at a terminal
        ("never", False, False),
        ("auto", True, True),
        ("auto", False, False),    # the default in a pipeline
    ],
)
def test_want_legend_resolves_the_tri_state(mode, tty, expected, monkeypatch):
    """The auto branch is only falsifiable with isatty patched.

    Every end-to-end run pipes stdout, so 'auto' is already False there and an
    assertion over those runs would survive deleting the isatty check
    outright -- the same trap the color tests document.
    """
    monkeypatch.setattr(bd_log.sys.stdout, "isatty", lambda: tty, raising=False)
    assert bd_log.want_legend(mode) is expected


def test_want_legend_defaults_to_auto(monkeypatch):
    """main() passes args.legend, whose argparse default is 'auto' -- so the
    signature default only matters to a caller that omits it. Pinned so the
    two cannot drift apart."""
    monkeypatch.setattr(bd_log.sys.stdout, "isatty", lambda: True, raising=False)
    assert bd_log.want_legend() is True


def test_legend_lays_out_the_same_grid_the_flags_select():
    lines = bd_log.render_legend()
    assert lines[0].split() == ["key", *bd_log.VERBS]
    assert lines[1].split()[0] == "beads"
    assert lines[2].split()[0] == "memories"
    # Every glyph the log can print is explained, none is explained twice.
    glyphs = [tok for ln in lines[1:] for tok in ln.split()
              if tok in set(bd_log.EVENT_GLYPH.values())]
    assert sorted(glyphs) == sorted(bd_log.EVENT_GLYPH.values())


def test_legend_tints_each_cell_like_the_rows_it_explains():
    """It is a color key as well as a symbol key -- naming the hues in words
    would say what they are called, not what they look like in your theme."""
    lines = bd_log.render_legend(color=True)
    for entity, line in zip(bd_log.ENTITIES, lines[1:]):
        for verb in bd_log.VERBS:
            kind = bd_log.KIND_BY_ENTITY_VERB[entity][verb]
            # COLORS values are whole escape sequences, not bare SGR numbers.
            code = bdutils.COLORS[bd_log.EVENT_COLOR[kind]]
            assert f"{code}{bd_log.EVENT_GLYPH[kind]}" in line


def test_legend_emits_no_escapes_when_color_is_off():
    assert not any("\033[" in ln for ln in bd_log.render_legend(color=False))


def test_memory_glyphs_are_ascii():
    """beads-utils-fh0: '▶' is East-Asian-ambiguous and mis-columns already.

    The new kinds must not widen that bug, so their glyphs stay in ASCII.
    """
    for kind in bd_log.MEMORY_KINDS:
        assert bd_log.EVENT_GLYPH[kind].isascii()
    assert bd_log.ELLIPSIS.isascii()


# --- filter_since ---------------------------------------------------------
#
# These call bd-log's own filter_since()/sort_events(). An earlier draft
# reimplemented the one-line comparison inside the test, which passed happily
# while testing nothing -- the reason both are named functions in the script
# rather than inline expressions in main().


def event(ts, kind="create", iid="p-1"):
    return (ts, kind, {"id": iid})


def test_filter_since_keeps_events_on_or_after_a_bare_date():
    """A 'YYYY-MM-DD' bound is shorter than the values it is compared to.

    It works because the bound is a prefix of every timestamp on that date, so
    it sorts before all of them and the whole day survives -- worth pinning,
    since it is the form a user actually types.
    """
    events = [
        event("2026-03-31T23:59:59Z"),
        event("2026-04-01T00:00:00Z"),
        event("2026-04-02T10:00:00Z"),
    ]
    kept = bd_log.filter_since(events, "2026-04-01")
    assert [e[0] for e in kept] == ["2026-04-01T00:00:00Z", "2026-04-02T10:00:00Z"]


def test_filter_since_accepts_a_full_rfc3339_bound():
    events = [event("2026-04-01T09:00:00Z"), event("2026-04-01T11:00:00Z")]
    kept = bd_log.filter_since(events, "2026-04-01T10:00:00Z")
    assert [e[0] for e in kept] == ["2026-04-01T11:00:00Z"]


@pytest.mark.parametrize("kind", ["create", "start", "close"])
def test_filter_since_applies_to_every_event_kind(kind):
    """Not just closures -- --since predates the other two event kinds."""
    events = [event("2026-03-01T00:00:00Z", kind), event("2026-05-01T00:00:00Z", kind)]
    kept = bd_log.filter_since(events, "2026-04-01")
    assert [e[1] for e in kept] == [kind]


def test_filter_since_that_excludes_everything_leaves_nothing():
    assert bd_log.filter_since([event("2026-04-01T00:00:00Z")], "2027-01-01") == []


def test_filter_since_keeps_everything_for_an_earlier_bound():
    events = [event("2026-04-01T00:00:00Z"), event("2026-04-02T00:00:00Z")]
    assert bd_log.filter_since(events, "2020-01-01") == events


# --- sort_events ----------------------------------------------------------


def test_sort_events_puts_the_newest_first():
    events = [event("2026-04-01T00:00:00Z"), event("2026-04-03T00:00:00Z"),
              event("2026-04-02T00:00:00Z")]
    assert [e[0][:10] for e in bd_log.sort_events(events)] == [
        "2026-04-03", "2026-04-02", "2026-04-01",
    ]


def test_sort_events_keeps_one_timestamps_lifecycle_reading_top_down():
    """Within a single timestamp the story should still read forwards.

    Hence the negated kind rank: the outer sort is reversed, so negating puts
    create above start above close rather than the mirror image.
    """
    same = "2026-04-01T00:00:00Z"
    events = [event(same, k) for k in ("close", "create", "start")]
    assert [e[1] for e in bd_log.sort_events(events)] == ["create", "start", "close"]


def test_sort_events_breaks_remaining_ties_on_id():
    """Two beads stamped the same second must not swap places between runs."""
    same = "2026-04-01T00:00:00Z"
    events = [event(same, "create", "p-1"), event(same, "create", "p-2")]
    assert [e[2]["id"] for e in bd_log.sort_events(events)] == ["p-2", "p-1"]


def test_sort_events_tolerates_an_event_whose_issue_has_no_id():
    same = "2026-04-01T00:00:00Z"
    events = [(same, "create", {}), (same, "create", {"id": "p-1"})]
    assert len(bd_log.sort_events(events)) == 2


def test_sort_events_returns_a_new_list():
    events = [event("2026-04-01T00:00:00Z"), event("2026-04-03T00:00:00Z")]
    assert bd_log.sort_events(events) is not events


# --- memory events --------------------------------------------------------
#
# 'bd remember' records no timestamps of its own -- a memory is a key/value row
# in Dolt's `config` table, and bd's `events` audit table holds only issue
# lifecycle rows. So these events are reconstructed from `dolt_diff_config`,
# which is why every test here goes through a fake `dolt` rather than `bd`.


@pytest.fixture
def dolt_project(project):
    """`project`, plus the Dolt database directory locate_dolt_db() looks for.

    The plain `project` fixture deliberately lacks it: that is a repo with no
    Dolt database, where memory history is simply unavailable.
    """
    (project / ".beads" / "embeddeddolt" / "testdb" / ".dolt").mkdir(parents=True)
    return project


def diff_row(key, diff_type="added", commit="c1", date="2026-04-01 13:05:00.000000",
             to_value=None, from_value=None):
    """One `dolt_diff_config` row, in the shape dolt's JSON output really has.

    NULL columns are *omitted* rather than sent as null (see
    bdutils.dolt_sql_json), so this builder drops them too -- an added row has
    no from_key, and an uncommitted one has no to_commit_date at all.
    """
    row = {"diff_type": diff_type, "to_commit": commit}
    if date is not None:
        row["to_commit_date"] = date
    if diff_type == "removed":
        row["from_key"] = bd_log.MEMORY_PREFIX + key
    else:
        row["to_key"] = bd_log.MEMORY_PREFIX + key
    if to_value is not None:
        row["to_value"] = to_value
    if from_value is not None:
        row["from_value"] = from_value
    return row


def program_dolt(fake_dolt, *rows):
    fake_dolt.default(stdout=json.dumps({"rows": list(rows)}))
    return fake_dolt


ALL_MEMORY_KINDS = set(bd_log.MEMORY_KINDS)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-08-02 19:55:33.460000", "2026-08-02T19:55:33Z"),
        ("2026-08-02 19:55:33", "2026-08-02T19:55:33Z"),
        # A working-set row has no date at all; dolt's JSON omits the column.
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("2026-08-02", ""),  # too short to be a timestamp; treated as absent
    ],
)
def test_normalize_dolt_ts_matches_bds_own_spelling(raw, expected):
    """Dolt returns UTC space-separated, bd returns RFC3339 with a Z.

    They have to agree: the merged timeline sorts events as plain strings, and
    --since compares a bare 'YYYY-MM-DD' as a prefix of them.
    """
    assert bd_log.normalize_dolt_ts(raw) == expected


def test_memory_events_maps_each_diff_type_to_its_verb(fake_dolt, dolt_project):
    program_dolt(
        fake_dolt,
        diff_row("added-one", "added", commit="c1", to_value="new"),
        diff_row("changed-one", "modified", commit="c2", to_value="after",
                 from_value="before"),
        diff_row("gone-one", "removed", commit="c3", from_value="what it said"),
    )
    events = bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)
    assert {(kind, payload["key"]) for _, kind, payload in events} == {
        ("remember", "added-one"),
        ("revise", "changed-one"),
        ("forget", "gone-one"),
    }


def test_memory_events_strip_the_kv_memory_prefix_from_the_key(fake_dolt, dolt_project):
    program_dolt(fake_dolt, diff_row("plain-key", to_value="v"))
    (_, _, payload), = bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)
    assert payload["key"] == "plain-key"


def test_memory_events_read_a_removals_value_from_the_from_side(fake_dolt, dolt_project):
    """A deletion has no to_value -- the text that existed is on `from`."""
    program_dolt(fake_dolt, diff_row("gone", "removed", from_value="it said this"))
    (_, kind, payload), = bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)
    assert kind == "forget"
    assert payload["value"] == "it said this"


def test_memory_events_leave_an_uncommitted_row_undated(fake_dolt, dolt_project):
    """Working-set changes are real and common -- a repo with dolt auto-commit
    off accumulates them -- and they carry no date to report."""
    program_dolt(fake_dolt, diff_row("fresh", commit="WORKING", date=None,
                                     to_value="just written"))
    (ts, _, _), = bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)
    assert ts == ""


def test_memory_events_dedupe_identical_rows_at_one_commit(fake_dolt, dolt_project):
    """Two rows sharing a (key, commit) identity collapse to one event.

    Named for what it actually constructs. It does NOT cover a merge commit
    re-reporting a change under a *different* to_commit, which the dedupe key
    would treat as distinct -- no repo on hand has a merge commit to check
    Dolt's real behavior against, so beads-utils-bld carries that question.
    """
    program_dolt(
        fake_dolt,
        diff_row("dup", commit="c1", to_value="v"),
        diff_row("dup", commit="c1", to_value="v"),
    )
    assert len(bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)) == 1


def test_memory_events_keep_the_same_key_changed_in_two_commits(fake_dolt, dolt_project):
    """The dedup key is (key, commit) -- a memory's history is not one row."""
    program_dolt(
        fake_dolt,
        diff_row("k", commit="c1", to_value="first"),
        diff_row("k", "modified", commit="c2", to_value="second", from_value="first"),
    )
    assert len(bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)) == 2


def test_memory_events_honor_the_requested_kinds(fake_dolt, dolt_project):
    program_dolt(
        fake_dolt,
        diff_row("a", "added", commit="c1", to_value="v"),
        diff_row("b", "removed", commit="c2", from_value="v"),
    )
    events = bd_log.memory_events(dolt_project, {"forget"})
    assert [kind for _, kind, _ in events] == ["forget"]


def test_memory_events_ignore_a_diff_type_they_do_not_know(fake_dolt, dolt_project):
    program_dolt(fake_dolt, diff_row("weird", "renamed", to_value="v"))
    assert bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS) == []


def test_memory_events_read_nothing_but_memories(fake_dolt, dolt_project):
    """The `config` table also holds bd's own settings; the query filters."""
    program_dolt(fake_dolt)
    bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)
    argv, = fake_dolt.calls
    assert f"like '{bd_log.MEMORY_PREFIX}%'" in " ".join(argv)


def test_memory_events_do_not_push_since_into_the_query(fake_dolt, dolt_project):
    """A 'to_commit_date >= ...' clause would silently drop every working-set
    row, because a NULL date fails every comparison. --since is applied in
    Python instead, and filter_since keeps undated events unconditionally."""
    program_dolt(fake_dolt)
    bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS)
    argv, = fake_dolt.calls
    assert "to_commit_date >" not in " ".join(argv)


# The None-vs-[] distinction: only the caller knows whether the user named
# memories explicitly, and so whether an empty answer deserves a warning.


def test_memory_events_are_none_without_a_dolt_cli(project, monkeypatch):
    monkeypatch.setenv("PATH", str(project))  # no `dolt` anywhere on it
    assert bd_log.memory_events(project, ALL_MEMORY_KINDS) is None


def test_memory_events_are_none_without_a_dolt_database(fake_dolt, project):
    """A JSONL-only (`no-db`) repo has no history to read, and must not crash."""
    program_dolt(fake_dolt, diff_row("k", to_value="v"))
    assert bd_log.memory_events(project, ALL_MEMORY_KINDS) is None


def test_memory_events_are_none_without_metadata_json(fake_dolt, tmp_path):
    """bdutils.read_metadata() exits the process when metadata.json is absent.

    That is right for the dolt scripts and wrong here -- bd-log still has bead
    events to print -- so the file is checked before it is read.
    """
    bare = tmp_path / "bare"
    (bare / ".beads").mkdir(parents=True)
    assert bd_log.memory_events(bare, ALL_MEMORY_KINDS) is None


def test_memory_events_are_none_when_the_query_fails(fake_dolt, dolt_project):
    fake_dolt.default(stderr="boom", exit_code=1)
    assert bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS) is None


def test_memory_events_of_an_empty_history_are_an_empty_list(fake_dolt, dolt_project):
    program_dolt(fake_dolt)
    assert bd_log.memory_events(dolt_project, ALL_MEMORY_KINDS) == []


# --- rendering a memory event --------------------------------------------


def memory(key="a-key", value="some value"):
    return {"key": key, "value": value}


def test_render_shows_the_memory_key_and_its_value():
    lines = bd_log.render("2026-04-01T13:05:00Z", "remember", memory("my-key", "hello"))
    assert lines == ["* 2026-04-01 13:05  my-key  memory", "  hello"]


def test_render_marks_an_undated_memory_event_as_uncommitted():
    lines = bd_log.render("", "revise", memory("k", "v"))
    assert lines[0].startswith("~ (uncommitted)")


def test_event_stamp_pads_uncommitted_to_the_width_of_a_real_timestamp():
    """So the columns behind it line up in --oneline."""
    assert len(bd_log.event_stamp("")) == len(
        bd_log.event_stamp("2026-04-01T13:05:00Z")
    )


def test_a_memory_event_has_no_actor():
    """Dolt records the committer as 'root'; the real name lives only inside
    the commit message text, which is too fragile to parse."""
    assert bd_log.event_actor("remember", memory()) == ""
    assert bd_log.render("2026-04-01T13:05:00Z", "remember", memory())[0].count("  ") == 2


LONG_KEY = "checkpoint-commit-before-second-round-of-changes"


def test_a_long_memory_key_is_capped_in_the_columnar_form():
    """Keys run to ~50 characters against ~17 for a bead id, and in --oneline
    the widest cell pads every row -- beads-utils-u20's failure mode."""
    cell = bd_log.event_id("remember", memory(LONG_KEY), bd_log.MEMORY_KEY_MAX)
    assert len(cell) == bd_log.MEMORY_KEY_MAX
    assert cell.endswith(bd_log.ELLIPSIS)
    assert LONG_KEY.startswith(cell[:-len(bd_log.ELLIPSIS)])


def test_the_block_form_leaves_a_long_memory_key_whole():
    """It has no column to protect, so there is nothing to trade legibility for."""
    assert bd_log.event_id("remember", memory(LONG_KEY)) == LONG_KEY
    assert LONG_KEY in bd_log.render("2026-04-01T13:05:00Z", "remember",
                                     memory(LONG_KEY))[0]


def test_a_long_memory_key_does_not_widen_the_bead_id_column_without_limit():
    events = [
        ("2026-04-01T00:00:00Z", "create", issue("p-1")),
        ("2026-04-01T00:00:00Z", "remember", memory(LONG_KEY)),
    ]
    id_w, _ = bd_log.oneline_widths(events)
    assert id_w == bd_log.MEMORY_KEY_MAX
    assert id_w < len(LONG_KEY)


def test_a_long_memory_value_is_truncated_unlike_a_bead_title():
    """Titles are left whole on purpose (git doesn't truncate either), but a
    memory value is a multi-paragraph essay -- shedding it is the point."""
    body = bd_log.event_title("remember", memory(value="x" * 500))
    assert len(body) == bd_log.MEMORY_VALUE_MAX
    assert body.endswith(bd_log.ELLIPSIS)


def test_a_memory_value_is_collapsed_to_one_line():
    body = bd_log.event_title("remember", memory(value="first\n\nsecond   para"))
    assert body == "first second para"


def test_an_empty_memory_value_still_renders_a_body():
    assert bd_log.event_title("remember", memory(value="")) == "(empty)"


@pytest.mark.parametrize("title", ["", "   ", "\t\n", None])
def test_a_blank_bead_title_falls_back_rather_than_painting_whitespace(title):
    """The fallback has to apply *after* collapsing, not to the raw value.

    '   ' is truthy, so an `or "(no title)"` placed first lets it through and
    collapse() then reduces it to '' -- rendering a body line that is nothing
    but padding, with the blanks trapped inside the color span ahead of the
    reset. The memory branch beside it already got this right.
    """
    assert bd_log.event_title("create", {"title": title}) == "(no title)"
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "create",
                                 {"title": title}, 3, 6)
    assert not line.endswith(" ")


@pytest.mark.parametrize(
    "kind,code", [("remember", "\033[34m"), ("revise", "\033[32m"),
                  ("forget", "\033[31m")],
)
def test_memory_events_share_the_bead_hues_verb_for_verb(kind, code):
    """Blue create, green change, red end -- the same three, not a fourth."""
    for line in bd_log.render("2026-04-01T13:05:00Z", kind, memory(), color=True):
        assert line.startswith(code)
        assert line.endswith("\033[0m")


def test_render_oneline_lays_a_memory_event_out_like_a_bead():
    line = bd_log.render_oneline("2026-04-01T13:05:00Z", "forget",
                                 memory("gone", "was this"), 6, 6)
    assert line == "x 2026-04-01 13:05  gone    memory  was this"


def test_oneline_widths_size_the_id_column_across_both_entities():
    events = [
        ("2026-04-01T00:00:00Z", "create", issue("p-1", priority=2,
                                                 issue_type="task")),
        ("2026-04-01T00:00:00Z", "remember", memory("a-longer-memory-key")),
    ]
    id_w, meta_w = bd_log.oneline_widths(events)
    assert id_w == len("a-longer-memory-key")
    assert meta_w == len("P2 task")


# --- the two entity rows, merged -----------------------------------------


def test_sort_events_float_undated_memory_changes_to_the_top():
    """An uncommitted change postdates every commit in the database, so it is
    the newest thing there is. '' sorts *lowest*, which under a reversed sort
    would have sunk it to the bottom -- hence the sentinel in the sort key."""
    events = [
        ("2026-04-01T00:00:00Z", "create", issue("p-1")),
        ("", "remember", memory("fresh")),
        ("2026-05-01T00:00:00Z", "create", issue("p-2")),
    ]
    ordered = bd_log.sort_events(events)
    assert ordered[0][2].get("key") == "fresh"


def test_split_pending_separates_undated_events_keeping_order():
    events = [
        ("", "remember", memory("fresh-a")),
        ("2026-05-01T00:00:00Z", "create", issue("p-1")),
        ("", "revise", memory("fresh-b")),
        ("2026-04-01T00:00:00Z", "create", issue("p-2")),
    ]
    pending, dated = bd_log.split_pending(events)
    assert [e[2]["key"] for e in pending] == ["fresh-a", "fresh-b"]
    assert [e[2]["id"] for e in dated] == ["p-1", "p-2"]


def test_split_pending_of_an_all_dated_list_yields_no_pending():
    events = [("2026-05-01T00:00:00Z", "create", issue("p-1"))]
    assert bd_log.split_pending(events) == ([], events)


def test_filter_since_never_drops_an_undated_event():
    events = [("", "remember", memory("fresh")),
              ("2026-01-01T00:00:00Z", "create", issue("old"))]
    kept = bd_log.filter_since(events, "2027-01-01")
    assert [e[2].get("key") for e in kept] == ["fresh"]


def test_sort_events_break_ties_between_two_memories_on_their_key():
    same = "2026-04-01T00:00:00Z"
    events = [(same, "remember", memory("k-1")), (same, "remember", memory("k-2"))]
    assert [e[2]["key"] for e in bd_log.sort_events(events)] == ["k-2", "k-1"]


def test_synthesize_events_ignores_memory_kinds():
    """It receives the whole grid selection; the memory half is fetched
    elsewhere, and a KeyError here would be a crash rather than a no-op."""
    rows = [issue("a-1", created_at="2026-01-01T00:00:00Z")]
    events = bd_log.synthesize_events(rows, {"create", "remember", "forget"})
    assert [kind for _, kind, _ in events] == ["create"]


# --- run_bd_list ----------------------------------------------------------


def test_run_bd_list_passes_the_scope_flags_and_parses_the_json(fake_bd, project):
    fake_bd.issues([{"id": "x-1", "title": "one"}])
    rows = bd_log.run_bd_list(project, ["--all"], None)
    assert rows == [{"id": "x-1", "title": "one"}]
    argv, = fake_bd.calls
    assert argv[:2] == ["list", "--all"]
    assert "--json" in argv


def test_run_bd_list_appends_the_id_filter_as_a_single_comma_list(fake_bd, project):
    fake_bd.issues([])
    bd_log.run_bd_list(project, [], ["b-1", "b-2"])
    argv, = fake_bd.calls
    assert "--id=b-1,b-2" in argv


def test_run_bd_list_treats_empty_output_as_no_issues(fake_bd, project):
    fake_bd.default(stdout="   \n")
    assert bd_log.run_bd_list(project, ["--all"], None) == []


def test_run_bd_list_reports_a_bd_failure_without_a_traceback(fake_bd, project):
    fake_bd.default(stderr="boom\n", exit_code=3)
    with pytest.raises(SystemExit) as excinfo:
        bd_log.run_bd_list(project, ["--all"], None)
    assert "exit 3" in str(excinfo.value.code)


def test_run_bd_list_reports_unparseable_json(fake_bd, project):
    fake_bd.default(stdout="not json at all")
    with pytest.raises(SystemExit) as excinfo:
        bd_log.run_bd_list(project, ["--all"], None)
    assert "could not parse" in str(excinfo.value.code)


def test_run_bd_list_reports_a_missing_bd_binary(project, monkeypatch):
    monkeypatch.setenv("PATH", str(project))  # no `bd` anywhere on it
    with pytest.raises(SystemExit) as excinfo:
        bd_log.run_bd_list(project, ["--all"], None)
    assert "not found on PATH" in str(excinfo.value.code)
