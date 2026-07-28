"""Tests for claude-session-report."""
from __future__ import annotations

import io

import pytest

from conftest import load_script

report = load_script("claude-session-report")


# --- parse_user_text ------------------------------------------------------


def test_parse_user_text_returns_plain_prose_untouched():
    parsed = report.parse_user_text("Please fix the pager.")
    assert parsed["human_text"] == "Please fix the pager."
    assert parsed["slash_command"] is None
    assert parsed["bash"] is None
    assert parsed["system_reminders"] == []


def test_parse_user_text_extracts_a_slash_command_with_args():
    text = (
        "<command-message>start-task</command-message>"
        "<command-name>/start-task</command-name>"
        "<command-args>beads-utils-86m</command-args>"
    )
    parsed = report.parse_user_text(text)
    assert parsed["slash_command"] == {
        "message": "start-task", "name": "/start-task", "args": "beads-utils-86m",
    }
    assert parsed["human_text"] == ""


def test_parse_user_text_handles_a_slash_command_without_args():
    text = (
        "<command-message>clear</command-message><command-name>/clear</command-name>"
    )
    parsed = report.parse_user_text(text)
    assert parsed["slash_command"]["name"] == "/clear"
    assert parsed["slash_command"]["args"] == ""


def test_parse_user_text_keeps_prose_alongside_a_slash_command():
    text = (
        "before "
        "<command-message>m</command-message><command-name>/x</command-name>"
        " after"
    )
    parsed = report.parse_user_text(text)
    assert parsed["slash_command"]["name"] == "/x"
    assert parsed["human_text"] == "before  after"


def test_parse_user_text_extracts_a_bash_shortcut():
    text = (
        "<bash-input>ls -l</bash-input>"
        "<bash-stdout>total 0</bash-stdout>"
        "<bash-stderr>oops</bash-stderr>"
    )
    parsed = report.parse_user_text(text)
    assert parsed["bash"] == {"input": "ls -l", "stdout": "total 0", "stderr": "oops"}
    assert parsed["human_text"] == ""


def test_parse_user_text_handles_bash_channels_arriving_separately():
    """Input lands in one entry and the output in the next."""
    first = report.parse_user_text("<bash-input>ls</bash-input>")
    assert first["bash"] == {"input": "ls", "stdout": "", "stderr": ""}
    second = report.parse_user_text("<bash-stdout>a\nb</bash-stdout>")
    assert second["bash"] == {"input": "", "stdout": "a\nb", "stderr": ""}


def test_parse_user_text_strips_bash_tags_even_though_the_channel_is_off_by_default():
    """Raw XML must never leak into the prose render."""
    parsed = report.parse_user_text("real question <bash-input>ls</bash-input>")
    assert "<bash-input>" not in parsed["human_text"]
    assert parsed["human_text"] == "real question"


def test_parse_user_text_extracts_local_command_stdout():
    parsed = report.parse_user_text(
        "<local-command-stdout>Session renamed</local-command-stdout>"
    )
    assert parsed["local_stdout"] == "Session renamed"


def test_parse_user_text_extracts_a_task_notification():
    parsed = report.parse_user_text("<task-notification>agent done</task-notification>")
    assert parsed["task_notification"] == "agent done"


def test_parse_user_text_collects_every_system_reminder():
    text = (
        "<system-reminder>one</system-reminder>"
        "keep me"
        "<system-reminder>two</system-reminder>"
    )
    parsed = report.parse_user_text(text)
    assert parsed["system_reminders"] == ["one", "two"]
    assert parsed["human_text"] == "keep me"


def test_parse_user_text_drops_the_local_command_caveat_entirely():
    """The caveat is boilerplate: not a channel, just noise to remove."""
    text = "<local-command-caveat>Caveat: ...</local-command-caveat>real"
    parsed = report.parse_user_text(text)
    assert parsed["human_text"] == "real"


def test_parse_user_text_handles_multiline_wrapper_bodies():
    parsed = report.parse_user_text("<system-reminder>a\nb\nc</system-reminder>x")
    assert parsed["system_reminders"] == ["a\nb\nc"]
    assert parsed["human_text"] == "x"


def test_parse_user_text_handles_an_empty_string():
    parsed = report.parse_user_text("")
    assert parsed["human_text"] == ""
    assert parsed["system_reminders"] == []


# --- gather_user_content --------------------------------------------------


def test_gather_user_content_accepts_a_bare_string():
    assert report.gather_user_content("hello") == ("hello", [])


def test_gather_user_content_joins_text_blocks_with_newlines():
    content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert report.gather_user_content(content) == ("a\nb", [])


def test_gather_user_content_separates_tool_results():
    content = [
        {"type": "text", "text": "prose"},
        {"type": "tool_result", "tool_use_id": "t1", "content": "output"},
    ]
    text, results = report.gather_user_content(content)
    assert text == "prose"
    assert results == [{"tool_use_id": "t1", "is_error": False, "content": "output"}]


def test_gather_user_content_marks_an_error_result():
    content = [{"type": "tool_result", "tool_use_id": "t1",
                "content": "boom", "is_error": True}]
    _, (result,) = report.gather_user_content(content)
    assert result["is_error"] is True


def test_gather_user_content_flattens_a_block_list_tool_result():
    content = [{"type": "tool_result", "content": [
        {"type": "text", "text": "one"}, {"type": "image"}, {"type": "text", "text": "two"},
    ]}]
    _, (result,) = report.gather_user_content(content)
    assert result["content"] == "one\ntwo"


@pytest.mark.parametrize("content", [None, 42, [], [{"not": "a block"}], ["raw"]])
def test_gather_user_content_tolerates_unexpected_shapes(content):
    text, results = report.gather_user_content(content)
    assert text == "" and results == []


# --- gather_assistant_blocks ----------------------------------------------


def test_gather_assistant_blocks_keeps_order_across_types():
    content = [
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": "answer"},
        {"type": "tool_use", "name": "Bash", "id": "t1", "input": {"command": "ls"}},
    ]
    blocks = report.gather_assistant_blocks(content)
    assert [b["type"] for b in blocks] == ["thinking", "text", "tool_use"]
    assert blocks[2]["name"] == "Bash"
    assert blocks[2]["input"] == {"command": "ls"}


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_gather_assistant_blocks_drops_whitespace_only_text(text):
    assert report.gather_assistant_blocks([{"type": "text", "text": text}]) == []


def test_gather_assistant_blocks_keeps_a_tool_use_with_no_input():
    blocks = report.gather_assistant_blocks([{"type": "tool_use", "name": "X"}])
    assert blocks == [{"type": "tool_use", "name": "X", "id": "", "input": None}]


@pytest.mark.parametrize("content", [None, "string", 42, {}])
def test_gather_assistant_blocks_returns_empty_for_non_lists(content):
    assert report.gather_assistant_blocks(content) == []


def test_gather_assistant_blocks_skips_unknown_block_types():
    assert report.gather_assistant_blocks([{"type": "mystery"}]) == []


# --- demote_headings ------------------------------------------------------


def test_demote_headings_pushes_content_headings_below_the_turn_header():
    """Our own section headers are H2, so content H1 must not compete."""
    assert report.demote_headings("# Title") == "### Title"
    assert report.demote_headings("## Sub") == "#### Sub"


def test_demote_headings_caps_at_h6():
    assert report.demote_headings("##### Deep") == "###### Deep"
    assert report.demote_headings("###### Deepest") == "###### Deepest"


def test_demote_headings_leaves_prose_and_hashtags_alone():
    assert report.demote_headings("no heading here") == "no heading here"
    assert report.demote_headings("#nospace") == "#nospace"


def test_demote_headings_preserves_leading_indentation():
    assert report.demote_headings("   # Indented") == "   ### Indented"


def test_demote_headings_ignores_a_four_space_indent():
    """Four spaces is an indented code block, not a heading."""
    assert report.demote_headings("    # Code") == "    # Code"


def test_demote_headings_skips_backtick_fenced_code():
    text = "# Real\n```\n# not a heading\n```\n# Also real"
    assert report.demote_headings(text) == (
        "### Real\n```\n# not a heading\n```\n### Also real"
    )


def test_demote_headings_skips_tilde_fenced_code():
    text = "~~~\n# comment\n~~~"
    assert report.demote_headings(text) == text


def test_demote_headings_handles_a_longer_fence_bar():
    text = "````\n# inside\n````\n# outside"
    out = report.demote_headings(text)
    assert "# inside" in out and "### outside" in out


def test_demote_headings_handles_a_bare_hash_line():
    assert report.demote_headings("#") == "###"


@pytest.mark.parametrize("by", [0, -1])
def test_demote_headings_is_a_no_op_for_a_non_positive_amount(by):
    assert report.demote_headings("# Title", by=by) == "# Title"


def test_demote_headings_returns_empty_input_unchanged():
    assert report.demote_headings("") == ""


def test_demote_headings_leaves_setext_underlines_alone():
    """Documented limitation -- rare in chat prose, needs lookahead to detect."""
    text = "Title\n====="
    assert report.demote_headings(text) == text


# --- fence ----------------------------------------------------------------


def test_fence_uses_three_backticks_for_ordinary_content():
    assert report.fence("plain") == "```\nplain\n```"


def test_fence_carries_a_language_tag():
    assert report.fence("ls", "bash").startswith("```bash\n")


def test_fence_grows_past_the_longest_backtick_run_inside():
    out = report.fence("a ``` b")
    assert out.startswith("````\n") and out.endswith("\n````")


def test_fence_grows_past_a_very_long_run():
    out = report.fence("`````")
    assert out.startswith("``````\n")


def test_fence_ignores_short_inline_code_runs():
    assert report.fence("use `x` here").startswith("```\n")


def test_fence_handles_empty_content():
    assert report.fence("") == "```\n\n```"


# --- Output helpers -------------------------------------------------------


def test_section_makes_every_emitted_item_its_own_h2():
    """Turn headers are H2; content headings get demoted to sit under them."""
    out = io.StringIO()
    report.section(out, "User — ts")
    assert out.getvalue() == "## User — ts\n\n"


def test_write_details_wraps_the_body_in_a_collapsible_block():
    out = io.StringIO()
    report.write_details(out, "Thinking", "the body")
    text = out.getvalue()
    assert "<details><summary>Thinking</summary>" in text
    assert "</details>" in text
    assert "the body" in text


def test_write_details_demotes_headings_inside_the_body():
    out = io.StringIO()
    report.write_details(out, "Skill body", "# Load Context")
    assert "### Load Context" in out.getvalue()


def test_channel_flags_cover_every_documented_toggle():
    assert set(report.CHANNEL_FLAGS) == {
        "prompts", "replies", "slash_commands",
        "thinking", "tools", "slash_bodies",
        "bash_shortcuts", "system_reminders", "task_notifications",
        "sidechains",
    }
