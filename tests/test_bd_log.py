"""Tests for bd-log.

The first class here is the reason the suite exists (bead beads-utils-86m):
four `select_subtrees` behaviors that this repo's own bead data cannot
exercise, because it has exactly one dotted hierarchy, no reparented beads and
no non-dotted children. Two of the four correspond to defects that were found
only by an ad-hoc check during beads-utils-52x, so the coverage is
load-bearing rather than decorative.
"""
from __future__ import annotations

import threading

import pytest

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


# --- parse_only / parse_ids ----------------------------------------------


def test_parse_only_accepts_known_kinds_and_trims_whitespace():
    assert bd_log.parse_only("create, close") == {"create", "close"}
    assert bd_log.parse_only("start") == {"start"}
    assert bd_log.parse_only("create,start,close") == set(bd_log.EVENT_KINDS)


def test_parse_only_rejects_an_unknown_kind_by_name():
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_only("create,finish")
    assert "finish" in str(excinfo.value.code)
    assert str(excinfo.value.code).startswith("error: ")


@pytest.mark.parametrize("value", ["", ",", "  ", ", ,"])
def test_parse_only_rejects_an_empty_list(value):
    with pytest.raises(SystemExit) as excinfo:
        bd_log.parse_only(value)
    assert "at least one event kind" in str(excinfo.value.code)


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


def test_render_oneline_always_has_a_meta_cell_to_render():
    """There is no empty-meta case to special-case, and that's load-bearing.

    format_priority() falls back to 'P?' rather than '', so event_meta() is
    never empty and meta_w is only 0 for an empty event list -- which main()
    returns early on. render_oneline can therefore pad unconditionally.
    """
    assert bd_log.event_meta({}) == "P?"
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
    """Every kind needs a timestamp field, a glyph, an order and a color."""
    for table in (bd_log.EVENT_TS_FIELD, bd_log.EVENT_GLYPH,
                  bd_log.EVENT_ORDER, bd_log.EVENT_COLOR):
        assert set(table) == set(bd_log.EVENT_KINDS)


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
