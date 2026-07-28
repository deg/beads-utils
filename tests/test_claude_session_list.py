"""Tests for claude-session-list."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import claudeutils
from conftest import load_script

session_list = load_script("claude-session-list")

NOW = datetime(2026, 5, 27, 18, 0, 0, tzinfo=timezone.utc)


# Timestamps default to a real value: render_range() falls back to the file's
# mtime when a session has none, and these fake metas point at paths that do
# not exist. Tests that want the fallback pass first=None, last=None with a
# real jsonl.
DEFAULT_TS = "2026-05-27T14:32:00Z"


def meta(uuid="abcd1234-ef56", first=DEFAULT_TS, last=DEFAULT_TS, prompts=0,
         replies=0, custom=None, ai=None, cwd=None, jsonl=None
         ) -> claudeutils.SessionMeta:
    return claudeutils.SessionMeta(
        jsonl=jsonl or Path(f"/tmp/projects/proj/{uuid}.jsonl"),
        custom_title=custom, ai_title=ai, cwd=cwd,
        first_ts=first, last_ts=last,
        human_prompts=prompts, assistant_turns=replies,
    )


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- _parse_iso -----------------------------------------------------------


def test_parse_iso_reads_a_z_suffixed_timestamp():
    assert session_list._parse_iso("2026-05-27T09:11:00Z") == datetime(
        2026, 5, 27, 9, 11, tzinfo=timezone.utc
    )


def test_parse_iso_reads_an_explicit_offset():
    parsed = session_list._parse_iso("2026-05-27T11:11:00+02:00")
    assert parsed.utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize("value", [None, "", "not a date", "2026-13-99"])
def test_parse_iso_returns_none_for_anything_unusable(value):
    assert session_list._parse_iso(value) is None


# --- _humanize_delta ------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"), (59, "59s"),
        (60, "1m"), (3599, "59m"),
        (3600, "1h"), (86399, "23h"),
        (86400, "1d"), (6 * 86400, "6d"),
        (7 * 86400, "1w"), (29 * 86400, "4w"),
        (30 * 86400, "1mo"), (330 * 86400, "11mo"),
        # The month bucket is 30 days flat, so the last stretch of a
        # year reads as "12mo" rather than rolling over early.
        (364 * 86400, "12mo"),
        (365 * 86400, "1y"), (800 * 86400, "2y"),
    ],
)
def test_humanize_delta_picks_the_largest_fitting_unit(seconds, expected):
    assert session_list._humanize_delta(seconds) == expected


# --- _humanize_span -------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, ""), (59, ""),          # below a minute there is nothing worth saying
        (60, "1m"), (3599, "59m"),
        (3600, "1h"),               # exact hour drops the minutes
        (4320, "1h12m"),
        (86400, "1d"),              # exact day drops the hours
        (97200, "1d3h"),
    ],
)
def test_humanize_span_renders_an_active_duration(seconds, expected):
    assert session_list._humanize_span(seconds) == expected


# --- _duration_secs -------------------------------------------------------


def test_duration_secs_measures_first_to_last():
    m = meta(first="2026-05-27T09:00:00Z", last="2026-05-27T10:30:00Z")
    assert session_list._duration_secs(m) == 5400


@pytest.mark.parametrize(
    "first,last",
    [(None, "2026-05-27T10:00:00Z"), ("2026-05-27T09:00:00Z", None), (None, None)],
)
def test_duration_secs_is_zero_without_both_endpoints(first, last):
    assert session_list._duration_secs(meta(first=first, last=last)) == 0.0


# --- render_range ---------------------------------------------------------


def test_render_range_shows_a_same_day_span_with_a_bare_end_time():
    m = meta(first="2026-05-27T09:11:00Z", last="2026-05-27T14:32:00Z")
    assert session_list.render_range(m, NOW) == (
        "2026-05-27 09:11 → 14:32  (3h ago, 5h21m active)"
    )


def test_render_range_spells_out_the_date_when_the_session_crosses_midnight():
    m = meta(first="2026-05-26T23:00:00Z", last="2026-05-27T01:00:00Z")
    out = session_list.render_range(m, NOW)
    assert "2026-05-26 23:00 → 2026-05-27 01:00" in out


def test_render_range_omits_the_active_span_when_it_is_under_a_minute():
    m = meta(first="2026-05-27T14:32:00Z", last="2026-05-27T14:32:30Z")
    assert session_list.render_range(m, NOW).endswith("(3h ago)")


def test_render_range_collapses_a_single_instant_to_one_timestamp():
    m = meta(first="2026-05-27T14:32:00Z", last="2026-05-27T14:32:00Z")
    out = session_list.render_range(m, NOW)
    assert "→" not in out
    assert out.startswith("2026-05-27 14:32")


def test_render_range_falls_back_to_the_file_mtime(tmp_path):
    """A jsonl with no timestamped entries still has to render something."""
    jsonl = tmp_path / "u.jsonl"
    jsonl.write_text("{}\n")
    stamp = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(jsonl, (stamp, stamp))
    out = session_list.render_range(meta(jsonl=jsonl, first=None, last=None), NOW)
    assert "mtime" in out
    assert "2026-05-27 12:00" in out


def test_render_range_uses_whichever_endpoint_exists():
    only_last = meta(first=None, last="2026-05-27T14:32:00Z")
    assert session_list.render_range(only_last, NOW).startswith("2026-05-27 14:32")
    only_first = meta(first="2026-05-27T14:32:00Z", last=None)
    assert session_list.render_range(only_first, NOW).startswith("2026-05-27 14:32")


# --- render_block ---------------------------------------------------------


def test_render_block_lists_uuid_range_counts_and_title():
    m = meta(uuid="abcd1234-ef56", first="2026-05-27T09:11:00Z",
             last="2026-05-27T14:32:00Z", prompts=5, replies=9, custom="Test Suite")
    lines = session_list.render_block(m, NOW, show_project=False)
    assert lines[0] == "abcd1234-ef56"
    assert lines[2] == "  5 prompts / 9 replies"
    assert lines[3] == "  Test Suite"


def test_render_block_singularizes_a_count_of_one():
    m = meta(prompts=1, replies=1)
    assert "  1 prompt / 1 reply" in session_list.render_block(m, NOW, False)


def test_render_block_pluralizes_zero():
    m = meta(prompts=0, replies=0)
    assert "  0 prompts / 0 replies" in session_list.render_block(m, NOW, False)


def test_render_block_adds_a_project_line_when_asked():
    m = meta(cwd="/Users/deg/Documents/degel/beads-utils")
    lines = session_list.render_block(m, NOW, show_project=True)
    assert lines[1] == "  beads-utils"


def test_render_block_labels_an_untitled_session():
    assert session_list.render_block(meta(), NOW, False)[-1] == "  (untitled)"


# --- _oneline_row / header ------------------------------------------------


def test_oneline_row_starts_with_the_eight_character_uuid_prefix():
    m = meta(uuid="abcd1234-ef56-7890", first="2026-05-27T09:11:00Z",
             last="2026-05-27T14:32:00Z", prompts=5, replies=9, custom="T")
    row = session_list._oneline_row(m, NOW, show_project=False, counts_w=6, project_w=0)
    assert row.startswith("abcd1234")
    assert "2026-05-27 09:11" in row
    assert "3h ago" in row
    assert row.endswith("T")


def test_oneline_row_started_is_the_first_timestamp_not_the_last():
    """STARTED and AGE are independent dimensions -- start vs. freshness."""
    m = meta(first="2026-05-20T08:00:00Z", last="2026-05-27T17:00:00Z")
    row = session_list._oneline_row(m, NOW, False, 6, 0)
    assert "2026-05-20 08:00" in row
    assert "1h ago" in row


def test_oneline_row_renders_the_counts_compactly():
    m = meta(prompts=12, replies=30, first=iso(NOW), last=iso(NOW))
    assert "12p/30r" in session_list._oneline_row(m, NOW, False, 7, 0)


def test_oneline_row_includes_the_project_when_asked():
    m = meta(cwd="/a/beads-utils", first=iso(NOW), last=iso(NOW))
    row = session_list._oneline_row(m, NOW, show_project=True, counts_w=6, project_w=12)
    assert "beads-utils" in row


def test_oneline_header_matches_the_requested_widths():
    header = session_list._oneline_header(show_project=True, counts_w=8, project_w=12)
    assert header.startswith("ID      ")
    for column in ("STARTED", "AGE", "COUNTS", "PROJECT", "TITLE"):
        assert column in header


def test_oneline_header_omits_project_when_not_shown():
    assert "PROJECT" not in session_list._oneline_header(False, 6, 0)


def test_render_oneline_block_sizes_columns_to_the_data():
    """Auto-sizing is what stops the TITLE column jittering row to row."""
    sessions = [
        meta(uuid="aaaa1111", prompts=1, replies=2, first=iso(NOW), last=iso(NOW)),
        meta(uuid="bbbb2222", prompts=123, replies=456, first=iso(NOW), last=iso(NOW)),
    ]
    lines = session_list.render_oneline_block(sessions, NOW, show_project=False)
    title_columns = {line.index("(untitled)") for line in lines[1:]}
    assert len(title_columns) == 1


def test_render_oneline_block_never_shrinks_below_the_header_width():
    sessions = [meta(prompts=0, replies=0, first=iso(NOW), last=iso(NOW))]
    lines = session_list.render_oneline_block(sessions, NOW, show_project=False)
    assert "COUNTS" in lines[0]
    assert len(lines) == 2


def test_render_oneline_block_handles_an_empty_session_list():
    lines = session_list.render_oneline_block([], NOW, show_project=True)
    assert len(lines) == 1 and "TITLE" in lines[0]


# --- parse_sort / apply_sort ----------------------------------------------


def test_parse_sort_reads_keys_and_descending_prefixes():
    assert session_list.parse_sort("-started,title") == [("started", True), ("title", False)]


def test_parse_sort_accepts_an_explicit_plus_and_ignores_blanks():
    assert session_list.parse_sort(" +id , ,-last ") == [("id", False), ("last", True)]


def test_parse_sort_rejects_an_unknown_key_and_lists_the_valid_ones():
    with pytest.raises(SystemExit) as excinfo:
        session_list.parse_sort("bogus")
    message = str(excinfo.value.code)
    assert "'bogus'" in message and "duration" in message


def test_sort_keys_match_the_documented_set():
    assert set(session_list.SORT_KEYS) == {
        "started", "last", "duration", "prompts", "replies",
        "turns", "title", "project", "id",
    }


def test_apply_sort_orders_by_prompt_count():
    sessions = [meta(uuid="a", prompts=3), meta(uuid="b", prompts=1)]
    ordered = session_list.apply_sort(sessions, [("prompts", False)])
    assert [m.human_prompts for m in ordered] == [1, 3]


def test_apply_sort_orders_by_turns_which_sums_both_sides():
    sessions = [meta(uuid="a", prompts=1, replies=1), meta(uuid="b", prompts=0, replies=5)]
    ordered = session_list.apply_sort(sessions, [("turns", True)])
    assert ordered[0].assistant_turns == 5


def test_apply_sort_compares_titles_case_insensitively():
    sessions = [meta(uuid="a", custom="zebra"), meta(uuid="b", custom="Apple")]
    ordered = session_list.apply_sort(sessions, [("title", False)])
    assert ordered[0].title == "Apple"


def test_apply_sort_treats_the_first_key_as_primary():
    sessions = [
        meta(uuid="a", prompts=1, custom="B"),
        meta(uuid="b", prompts=1, custom="A"),
        meta(uuid="c", prompts=0, custom="C"),
    ]
    ordered = session_list.apply_sort(sessions, [("prompts", False), ("title", False)])
    assert [m.title for m in ordered] == ["C", "A", "B"]


def test_apply_sort_sorts_missing_timestamps_before_real_ones():
    sessions = [meta(uuid="a", first="2026-01-01T00:00:00Z"), meta(uuid="b", first=None)]
    ordered = session_list.apply_sort(sessions, [("started", False)])
    assert ordered[0].first_ts is None


def test_apply_sort_returns_a_new_list():
    sessions = [meta(uuid="a", prompts=2), meta(uuid="b", prompts=1)]
    ordered = session_list.apply_sort(sessions, [("prompts", False)])
    assert ordered is not sessions
    assert sessions[0].human_prompts == 2


def test_apply_sort_with_no_keys_preserves_order():
    sessions = [meta(uuid="a"), meta(uuid="b")]
    assert session_list.apply_sort(sessions, []) == sessions


# --- apply_match ----------------------------------------------------------


def test_apply_match_finds_a_title_substring_case_insensitively():
    sessions = [meta(uuid="a", custom="Test Suite"), meta(uuid="b", custom="Other")]
    assert [m.title for m in session_list.apply_match(sessions, "test")] == ["Test Suite"]


def test_apply_match_also_matches_the_uuid():
    sessions = [meta(uuid="abcd1234-ef56"), meta(uuid="9999zzzz-0000")]
    matched = session_list.apply_match(sessions, "ABCD")
    assert len(matched) == 1 and matched[0].jsonl.stem.startswith("abcd")


def test_apply_match_returns_nothing_when_no_session_matches():
    assert session_list.apply_match([meta(custom="A")], "zzz") == []


def test_apply_match_with_an_empty_pattern_keeps_everything():
    sessions = [meta(uuid="a"), meta(uuid="b")]
    assert session_list.apply_match(sessions, "") == sessions
