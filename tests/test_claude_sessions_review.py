"""Tests for claude-sessions-review."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import pytest

from conftest import load_script, write_session

review = load_script("claude-sessions-review")

NOW = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)


# --- classify: which extractor wins, and what it keeps ---------------------


def test_classify_finds_a_zsh_error_in_the_middle_of_the_output():
    """The case that makes scanning the whole text necessary: a compound
    command prints normally, then zsh fails on a later glob."""
    text = ("Exit code 1\nfile1.py\nfile2.py\n----\n"
            "(eval):1: no matches found: --include=*.py\nmore output")
    sig = review.classify(text)
    assert (sig.kind, sig.message, sig.variant) == (
        "failure", "zsh: no matches found", "--include=*.py")
    assert sig.detail == "(eval):1: no matches found: --include=*.py"


def test_classify_names_the_builtin_zsh_blames_and_keeps_the_argument():
    """The `cd ... backend` habit is only actionable with `backend` kept as a variant."""
    sig = review.classify("Exit code 1\n(eval):cd:7: no such file or directory: backend")
    assert sig.message == "zsh: cd: no such file or directory"
    assert sig.variant == "backend"


@pytest.mark.parametrize("word", ["==", "====", "===MODELS"])
def test_classify_folds_every_equals_word_into_one_pattern(word):
    """zsh puts the word itself in the message (`===== not found`), so
    without folding, each separator length is its own pattern."""
    sig = review.classify(f"Exit code 1\n(eval):1: {word} not found")
    assert sig.message == "zsh: =word not found"
    assert sig.variant == word


def test_classify_reads_the_last_line_of_a_traceback():
    """The exception is the LAST line; the frames above it differ every time."""
    text = ("Exit code 1\nTraceback (most recent call last):\n"
            '  File "<stdin>", line 3, in <module>\n'
            "ModuleNotFoundError: No module named 'openpyxl'")
    sig = review.classify(text)
    assert sig.message == "python: ModuleNotFoundError: No module named '…'"
    assert sig.variant == "openpyxl"


def test_classify_shortens_a_dotted_exception_name():
    """`json.decoder.JSONDecodeError` and `JSONDecodeError` are one pattern."""
    text = ("Traceback (most recent call last):\n  x\n"
            "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)")
    assert review.classify(text).message == (
        "python: JSONDecodeError: Expecting value: line <n> column <n> (char <n>)")


def test_classify_keeps_a_bare_exception_name():
    """A bare `AssertionError` has no message; it must not render as `AssertionError: `."""
    text = "Traceback (most recent call last):\n  assert x\nAssertionError"
    assert review.classify(text).message == "python: AssertionError"


def test_classify_reads_a_harness_tool_use_error():
    """Harness guards (Edit before Read) are failures a rule can fix, not noise."""
    text = ("<tool_use_error>File has not been read yet. Read it first before "
            "writing to it.</tool_use_error>")
    sig = review.classify(text)
    assert sig.message == "File has not been read yet."
    assert sig.kind == "failure"


def test_classify_puts_a_timeout_duration_in_the_variant():
    """2m and 1m30s timeouts are one pattern; the duration is what varies."""
    sig = review.classify("Exit code 143\nCommand timed out after 2m 0s")
    assert (sig.message, sig.variant) == ("command timed out", "2m 0s")


def test_classify_drops_the_mcp_wrapper():
    """Every MCP call wraps its error in `Error running <tool>:`; the tool is already counted."""
    sig = review.classify("Error running delete-many: MCP error -32001: Request timed out")
    assert sig.message == "MCP error -<n>: Request timed out"


def test_classify_prefers_an_error_looking_line_over_the_first_line():
    """git prints status before `fatal:`; grouping on the status line would hide the error."""
    text = "Exit code 128\nOn branch main\nfatal: not a git repository"
    assert review.classify(text).message == "fatal: not a git repository"


def test_classify_labels_an_exit_with_no_error_line():
    """Output that never says 'error' is stray stdout, not the failure."""
    sig = review.classify("Exit code 1\n  42 total")
    assert sig.message == "exit 1, first line: <n> total"


def test_classify_labels_an_exit_with_no_output():
    """A bare non-zero exit (grep finding nothing) is its own group, not an empty message."""
    assert review.classify("Exit code 1").message == "exit 1, no output"
    assert review.classify("").message == "error with no text"


@pytest.mark.parametrize("text, message", [
    ("The user doesn't want to proceed with this tool use. The tool use was "
     "rejected. To tell you how to proceed, the user said:\nuse rg instead",
     "rejected by the user"),
    ("Permission for this action was denied by the Claude Code auto mode "
     "classifier. Reason: deletes data.. If you have other tasks",
     "denied by the auto-mode classifier"),
    ("Permission for this action has been denied.", "denied by a permission rule"),
    ("[Request interrupted by user for tool use]", "interrupted by the user"),
])
def test_classify_recognizes_denials_whatever_the_tool(text, message):
    """Denials are decisions, not failures; misfiling them would bury real failures."""
    sig = review.classify(text)
    assert (sig.kind, sig.message) == ("denied", message)


def test_classify_keeps_what_the_user_said_and_the_classifiers_reason():
    """The why behind a denial is the preference signal /dream wants."""
    said = review.classify("The user doesn't want to proceed with this tool use. "
                           "the user said:\nuse rg instead")
    assert said.detail == "use rg instead"
    reason = review.classify("Permission for this action was denied by the Claude Code "
                             "auto mode classifier. Reason: deletes data.. If you")
    assert reason.detail == "deletes data"


@pytest.mark.parametrize("text, message", [
    ("claude-opus-4-7[1m] is temporarily unavailable, so auto mode cannot "
     "determine the safety of Bash right now.", "auto-mode classifier model unavailable"),
    ("The server-side auto mode classifier gave no verdict (error), so auto mode "
     "cannot determine the safety of Bash.", "auto-mode classifier gave no verdict"),
])
def test_classify_recognizes_classifier_outages(text, message):
    """Outages are neither a mistake nor a decision; they get their own kind."""
    sig = review.classify(text)
    assert (sig.kind, sig.message) == ("unavailable", message)


# --- normalize ---------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("ls: /Users/x/a.py: No such file", "ls: <path>: No such file"),
    ("sed: backend/app/x.py: No such file", "sed: <path>: No such file"),
    ("No module named 'yaml'", "No module named '…'"),
    ("commit 4b102dd not found", "commit <id> not found"),
    ("session 83bf7cb8-6ad8-42b2-b68b-560202d1413a gone", "session <id> gone"),
    ("Found 2 matches", "Found <n> matches"),
    ("a   b\n c", "a b c"),
])
def test_normalize_abstracts_what_varies_between_occurrences(raw, expected):
    """Without abstraction every occurrence is its own group and nothing recurs."""
    assert review.normalize(raw) == expected


def test_normalize_leaves_an_all_letter_hex_word_alone():
    """Only hex runs with a digit are ids; 'defaced' is a word."""
    assert review.normalize("defaced output") == "defaced output"


def test_clip_shows_the_home_directory_as_tilde(monkeypatch):
    """Variants and examples are read by a person; the home prefix is noise."""
    monkeypatch.setattr(review, "HOME", "/Users/someone")
    assert review.clip("/Users/someone/x", 40) == "~/x"
    assert review.clip("abcdef", 4) == "abc…"


# --- parse_since ---------------------------------------------------------------


@pytest.mark.parametrize("spec, hours", [("12h", 12), ("3d", 72), ("2w", 336)])
def test_parse_since_counts_back_from_now(spec, hours):
    """`--since 2w` is the everyday spelling; each unit must mean what it says."""
    assert (NOW - review.parse_since(spec, NOW)).total_seconds() == hours * 3600


def test_parse_since_reads_a_date_as_local_midnight():
    """A date means the whole day where David is, not from UTC midnight.

    conftest pins TZ=UTC for the suite, where the two are the same instant, so
    this test switches to New York (EDT on 2026-10-29, UTC-4). It restores UTC
    by hand: monkeypatch.setenv would put TZ back but not re-run tzset(), and
    the zone would leak into every later test.
    """
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        assert review.parse_since("2026-10-29", NOW) == datetime(
            2026, 10, 29, 4, 0, tzinfo=timezone.utc)
    finally:
        os.environ["TZ"] = "UTC"
        time.tzset()


@pytest.mark.parametrize("spec", ["yesterday", "3m", "2026-13-01", ""])
def test_parse_since_rejects_anything_else(spec):
    """A typo must be an error, not silently the whole history."""
    with pytest.raises(SystemExit) as excinfo:
        review.parse_since(spec, NOW)
    assert "--since" in str(excinfo.value.code)


# --- Transcript fixtures -------------------------------------------------------


def call(tool_id, name, tool_input, ts):
    return {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}}


def failed(tool_id, text, ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": text}]}}


def ok(tool_id, text, ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}


GLOB = "Exit code 1\n(eval):1: no matches found: *.py"
TIMEOUT = "Exit code 143\nCommand timed out after 2m 0s"


def glob_failure(n, ts="2026-10-01T10:00:00Z"):
    """A tool call plus its failed result, ids distinct per n."""
    return [call(f"t{n}", "Bash", {"command": f"grep -r x --include=*.py # {n}"}, ts),
            failed(f"t{n}", GLOB, ts)]


def wanted(groups, kind):
    """The groups of one kind, as main() hands them to select()."""
    return [g for g in groups.values() if g.kind == kind]


@pytest.fixture
def pdir(claude_home):
    return claude_home / "-proj"


# --- scan -------------------------------------------------------------------------


def test_scan_groups_failures_and_ignores_successes(pdir):
    """Only `is_error` results count: a successful result can contain error text."""
    write_session(pdir, "s1", [
        {"type": "custom-title", "customTitle": "first"},
        *glob_failure(1),
        call("t9", "Bash", {"command": "ls"}, "2026-10-01T10:01:00Z"),
        ok("t9", "Exit code 1\n(eval):1: no matches found: *.py", "2026-10-01T10:01:01Z"),
    ])
    groups = review.scan([pdir], None)
    assert list(groups) == [("failure", "zsh: no matches found")]
    g = groups[("failure", "zsh: no matches found")]
    assert len(g.occurrences) == 1  # the is_error-less result is not a failure
    assert g.tools == {"Bash": 1}
    assert g.variants == {"*.py": 1}
    occ = g.occurrences[0]
    assert (occ.session, occ.tool) == ("s1", "Bash")
    assert occ.input == "grep -r x --include=*.py # 1"


def test_scan_counts_a_subagent_failure_under_its_parent_session(pdir):
    """Counting subagents as sessions would inflate the spread that ranking uses."""
    write_session(pdir, "parent", [{"type": "custom-title", "customTitle": "p"}])
    write_session(pdir / "parent" / "subagents", "agent-abc", glob_failure(1))
    g = review.scan([pdir], None)[("failure", "zsh: no matches found")]
    assert g.sessions == {"parent"}
    assert g.occurrences[0].project_dir == pdir


def test_scan_drops_failures_before_the_cutoff(pdir):
    """A transcript spans days; --since must cut inside a file, not only by file."""
    write_session(pdir, "s1", [*glob_failure(1, "2026-09-01T00:00:00Z"),
                               *glob_failure(2, "2026-10-15T00:00:00Z")])
    cutoff = datetime(2026, 10, 1, tzinfo=timezone.utc)
    g = review.scan([pdir], cutoff)[("failure", "zsh: no matches found")]
    assert [o.ts for o in g.occurrences] == ["2026-10-15T00:00:00Z"]


def test_scan_skips_a_file_last_written_before_the_cutoff_unread(pdir):
    """The entry inside is dated 2030, so only the mtime check can drop it."""
    path = write_session(pdir, "old", glob_failure(1, "2030-01-01T00:00:00Z"))
    os.utime(path, (0, 0))  # mtime 1970: cannot hold anything after the cutoff
    cutoff = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert review.scan([pdir], cutoff) == {}


def test_scan_survives_junk_lines_and_an_unknown_tool_id(pdir):
    """One truncated transcript must not abort a run over hundreds."""
    path = write_session(pdir, "s1", [failed("never-called", TIMEOUT, "2026-10-01T00:00:00Z")])
    with path.open("a") as f:
        f.write('{"tool_use": not json\n')
    g = review.scan([pdir], None)[("failure", "command timed out")]
    assert g.occurrences[0].tool == "?"


# --- select: ranking and the min-sessions bar ---------------------------------------


def test_select_ranks_by_sessions_not_by_hits(pdir):
    """One session looping on a failure must not outrank a habit."""
    loop = []
    for n in range(10):
        loop += [call(f"x{n}", "Bash", {"command": "sleep"}, "2026-10-01T00:00:00Z"),
                 failed(f"x{n}", TIMEOUT, "2026-10-01T00:00:00Z")]
    write_session(pdir, "looper", loop)
    for s in ("a", "b", "c"):
        write_session(pdir, s, glob_failure(1))
    groups = review.scan([pdir], None)
    kept, hidden = review.select(wanted(groups, "failure"), min_sessions=1)
    assert [g.message for g in kept] == ["zsh: no matches found", "command timed out"]
    assert len(kept[1].occurrences) == 10


def test_select_hides_patterns_below_the_bar_and_counts_them(pdir):
    """Hidden one-offs are counted so the stderr footer can say they exist."""
    write_session(pdir, "a", [*glob_failure(1), call("t", "Bash", {}, "2026-10-01T00:00:00Z"),
                              failed("t", TIMEOUT, "2026-10-01T00:00:00Z")])
    write_session(pdir, "b", glob_failure(1))
    kept, hidden = review.select(wanted(review.scan([pdir], None), "failure"), min_sessions=2)
    assert [g.message for g in kept] == ["zsh: no matches found"]
    assert hidden == 1


# --- Group.examples and rendering ----------------------------------------------------


def test_examples_take_the_newest_hit_from_each_of_the_newest_sessions(pdir):
    """Three examples from one looping session would show one case three times."""
    write_session(pdir, "old", glob_failure(1, "2026-09-01T00:00:00Z"))
    write_session(pdir, "new", [*glob_failure(1, "2026-10-01T00:00:00Z"),
                                *glob_failure(2, "2026-10-02T00:00:00Z")])
    g = review.scan([pdir], None)[("failure", "zsh: no matches found")]
    ex = g.examples(5)
    assert [(o.session, o.ts) for o in ex] == [
        ("new", "2026-10-02T00:00:00Z"), ("old", "2026-09-01T00:00:00Z")]
    assert len(g.examples(1)) == 1


def test_render_group_shows_counts_span_variants_and_examples(pdir):
    """Pins the block layout the README and rule file describe."""
    write_session(pdir, "aaaaaaaa-1", [{"type": "custom-title", "customTitle": "Title A"},
                                       *glob_failure(1, "2026-09-01T00:00:00Z")])
    write_session(pdir, "bbbbbbbb-2", glob_failure(1, "2026-10-02T00:00:00Z"))
    g = review.scan([pdir], None)[("failure", "zsh: no matches found")]
    lines = review.render_group(g, review.Titles(), show_project=False, show_kind=False)
    assert lines[0] == "zsh: no matches found"
    assert lines[1] == "  2 times in 2 sessions · 2026-09-01 → 2026-10-02 · Bash"
    assert lines[2] == "  variants: *.py (2)"
    assert lines[3] == "  2026-10-02  bbbbbbbb  (untitled)"
    assert lines[4] == "      Bash: grep -r x --include=*.py # 1"
    assert lines[5] == "      -> (eval):1: no matches found: *.py"
    assert lines[6] == "  2026-09-01  aaaaaaaa  Title A"


def test_render_group_tags_the_kind_when_showing_every_kind(pdir):
    """With --kind all, a denial must not read as a failure."""
    write_session(pdir, "a", glob_failure(1))
    g = review.scan([pdir], None)[("failure", "zsh: no matches found")]
    assert review.render_group(g, review.Titles(), False, True)[0] == (
        "[failure] zsh: no matches found")


def test_to_json_carries_counts_dates_and_examples(pdir):
    """The JSON is /dream's interface; its fields must not drift silently."""
    write_session(pdir, "a", [{"type": "custom-title", "customTitle": "A"},
                              *glob_failure(1, "2026-10-01T00:00:00Z")])
    write_session(pdir, "b", glob_failure(1, "2026-10-05T00:00:00Z"))
    kept, _ = review.select(list(review.scan([pdir], None).values()), 2)
    doc = review.to_json(kept, review.Titles(), scope="global", since=None,
                         kinds=review.KINDS, min_sessions=2, totals={"patterns": 1})
    json.dumps(doc)  # serializable
    (p,) = doc["patterns"]
    assert (p["occurrences"], p["sessions"]) == (2, 2)
    assert (p["first_seen"], p["last_seen"]) == ("2026-10-01T00:00:00Z", "2026-10-05T00:00:00Z")
    assert [e["session"] for e in p["examples"]] == ["b", "a"]
    assert p["examples"][1]["title"] == "A"
    assert doc["kinds"] == ["failure", "denied", "unavailable"]
    assert doc["totals"] == {"patterns": 1}


def test_classify_files_quoted_classifier_text_in_output_as_a_failure():
    """A grep over transcripts can print outage wording; that is not an outage."""
    text = ("Exit code 1\nlog.jsonl: The server-side auto mode classifier gave no verdict\n"
            "grep: other.jsonl: No such file or directory")
    assert review.classify(text).kind == "failure"


def test_classify_reads_an_overloaded_classifier_as_an_outage():
    """The overloaded wording inserts `(overloaded)`; the anchored pattern must allow it."""
    text = ("claude-sonnet-5[1m] is temporarily unavailable (overloaded), so auto mode "
            "cannot determine the safety of Bash right now.")
    assert review.classify(text).kind == "unavailable"


def test_classify_files_a_harness_error_printed_by_grep_as_the_grep_failure():
    """A grep over transcripts can print a <tool_use_error> it found. The
    failure is the grep's; only a result that STARTS with the tag is the
    harness's."""
    text = ('Exit code 2\nlog.jsonl: "<tool_use_error>File has not been read yet.'
            '</tool_use_error>"\ngrep: other.jsonl: No such file or directory')
    assert review.classify(text).message == "grep: other.jsonl: No such file or directory"


def test_classify_still_reads_a_harness_error_after_an_exit_line():
    """Anchoring must still allow the `Exit code N` line that precedes it."""
    text = "Exit code 1\n<tool_use_error>Blocked: sleep 45 followed by: ls</tool_use_error>"
    assert review.classify(text).message.startswith("Blocked: sleep <n>")


def test_normalize_does_not_take_an_apostrophe_for_a_quote():
    """`can't` paired with the next quote would swallow the text between, and
    with two contractions a real argument leaked into the grouping key, so
    every different value became its own pattern."""
    assert review.normalize("can't open file 'x.py': no") == "can't open file '…': no"
    assert review.normalize("couldn't find 'foo' and can't find 'bar'") == (
        "couldn't find '…' and can't find '…'")
    assert review.first_variant("can't open file '/x.py': no") == "/x.py"


def test_scan_counts_a_result_once_when_its_session_sits_under_two_project_dirs(claude_home):
    """A renamed project leaves the same session file under both its old and
    new project dir. Session counts are sets and survived that, but hits,
    tools and variants counted twice: 112 phantom hits in the real data."""
    old, new = claude_home / "-old-name", claude_home / "-new-name"
    for pdir in (old, new):
        write_session(pdir, "same-uuid", glob_failure(1))
    g = review.scan([old, new], None)[("failure", "zsh: no matches found")]
    assert len(g.occurrences) == 1
    assert g.tools == {"Bash": 1} and g.variants == {"*.py": 1}

