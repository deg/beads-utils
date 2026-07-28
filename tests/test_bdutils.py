"""Tests for bdutils.py, the shared helper module.

Every script in the collection imports from here, so a regression is a
regression everywhere at once. Note the two different assertion styles for
failure output: error() calls sys.exit(str), whose message is printed by the
interpreter's top-level handler -- which never runs under pytest.raises -- so
it is asserted via SystemExit.code, while warn() writes to sys.stderr directly
and shows up in capsys.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys

import pytest

import bdutils


# --- Version and error reporting -----------------------------------------


def test_add_version_arg_prints_prog_and_the_shared_version(capsys):
    parser = argparse.ArgumentParser(prog="bd-thing")
    bdutils.add_version_arg(parser)
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"bd-thing {bdutils.__version__}"


def test_version_is_a_plain_dotted_string():
    """The whole collection versions as one unit off this single string."""
    parts = bdutils.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_error_exits_non_zero_with_a_lowercase_error_prefix():
    with pytest.raises(SystemExit) as excinfo:
        bdutils.error("something broke")
    assert excinfo.value.code == "error: something broke"


def test_warn_writes_to_stderr_and_returns(capsys):
    bdutils.warn("heads up")
    captured = capsys.readouterr()
    assert captured.err == "warning: heads up\n"
    assert captured.out == ""


# --- format_ts ------------------------------------------------------------
#
# The session pins TZ=UTC (see conftest), so these literals are stable
# everywhere; without that pin they would differ between a developer's machine
# and CI.


@pytest.mark.parametrize(
    "iso,expected",
    [
        ("2026-04-01T13:05:00Z", "2026-04-01 13:05"),
        ("2026-04-01T13:05:00+00:00", "2026-04-01 13:05"),
        ("2026-04-01T13:05:00.123456Z", "2026-04-01 13:05"),
        # An offset is normalized to UTC, not printed as-is.
        ("2026-04-01T15:05:00+02:00", "2026-04-01 13:05"),
        ("2026-12-31T23:59:59Z", "2026-12-31 23:59"),
    ],
)
def test_format_ts_renders_utc_timestamps_to_minute_precision(iso, expected):
    assert bdutils.format_ts(iso) == expected


def test_format_ts_returns_empty_for_empty_input():
    assert bdutils.format_ts("") == ""


@pytest.mark.parametrize("junk", ["not a date", "2026-13-45", "yesterday"])
def test_format_ts_passes_unparseable_input_through_unchanged(junk):
    assert bdutils.format_ts(junk) == junk


def test_format_ts_handles_a_naive_timestamp_without_raising():
    """No zone suffix means the value is read as local time (UTC here)."""
    assert bdutils.format_ts("2026-04-01T13:05:00") == "2026-04-01 13:05"


# --- format_priority ------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "P0"), (1, "P1"), (2, "P2"), (3, "P3"), (4, "P4"),
        ("2", "P2"),          # bd sometimes hands back a string
        (2.0, "P2"),
        (None, "P?"),
        ("", "P?"),
    ],
)
def test_format_priority_renders_the_pn_form(value, expected):
    assert bdutils.format_priority(value) == expected


@pytest.mark.parametrize("value", ["high", "urgent", "P2"])
def test_format_priority_passes_through_a_non_numeric_label(value):
    """An unexpected vocabulary should surface, not be swallowed as P?."""
    assert bdutils.format_priority(value) == value


# --- resolve_project_path -------------------------------------------------


def test_resolve_project_path_accepts_a_directory_with_a_beads_dir(project):
    assert bdutils.resolve_project_path(str(project)) == project.resolve()


def test_resolve_project_path_rejects_a_directory_without_beads(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        bdutils.resolve_project_path(str(tmp_path))
    assert "no .beads/ directory" in str(excinfo.value.code)


def test_resolve_project_path_rejects_a_nonexistent_path(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        bdutils.resolve_project_path(str(tmp_path / "nope"))
    assert "no .beads/ directory" in str(excinfo.value.code)


def test_resolve_project_path_rejects_a_beads_file_masquerading_as_the_dir(tmp_path):
    (tmp_path / ".beads").write_text("not a directory")
    with pytest.raises(SystemExit):
        bdutils.resolve_project_path(str(tmp_path))


def test_resolve_project_path_expands_a_tilde(project, monkeypatch):
    monkeypatch.setenv("HOME", str(project.parent))
    assert bdutils.resolve_project_path(f"~/{project.name}") == project.resolve()


def test_resolve_project_path_returns_an_absolute_resolved_path(project, monkeypatch):
    monkeypatch.chdir(project.parent)
    resolved = bdutils.resolve_project_path(project.name)
    assert resolved.is_absolute()
    assert resolved == project.resolve()


# --- Color ----------------------------------------------------------------


def test_add_color_arg_defaults_to_auto_and_rejects_other_words():
    parser = argparse.ArgumentParser(prog="x")
    bdutils.add_color_arg(parser)
    assert parser.parse_args([]).color == "auto"
    assert parser.parse_args(["--color=always"]).color == "always"
    with pytest.raises(SystemExit):
        parser.parse_args(["--color=sometimes"])


def test_color_modes_and_the_flag_choices_agree():
    parser = argparse.ArgumentParser(prog="x")
    bdutils.add_color_arg(parser)
    for mode in bdutils.COLOR_MODES:
        assert parser.parse_args([f"--color={mode}"]).color == mode


@pytest.mark.parametrize("mode", ["always", "never"])
def test_want_color_obeys_an_explicit_mode_regardless_of_environment(mode, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    assert bdutils.want_color(mode) is (mode == "always")


def test_want_color_auto_follows_stdout_when_the_environment_is_neutral(monkeypatch):
    monkeypatch.setattr(bdutils.sys.stdout, "isatty", lambda: True, raising=False)
    assert bdutils.want_color("auto") is True
    monkeypatch.setattr(bdutils.sys.stdout, "isatty", lambda: False, raising=False)
    assert bdutils.want_color("auto") is False


@pytest.mark.parametrize("value", ["1", "yes", "anything"])
def test_want_color_auto_honors_any_non_empty_no_color(value, monkeypatch):
    """no-color.org: presence disables color; the value is not interpreted."""
    monkeypatch.setattr(bdutils.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setenv("NO_COLOR", value)
    assert bdutils.want_color("auto") is False


def test_want_color_auto_ignores_an_empty_no_color(monkeypatch):
    monkeypatch.setattr(bdutils.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setenv("NO_COLOR", "")
    assert bdutils.want_color("auto") is True


def test_want_color_auto_declines_on_a_dumb_terminal(monkeypatch):
    monkeypatch.setattr(bdutils.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert bdutils.want_color("auto") is False


def test_want_color_defaults_to_auto_when_called_with_no_argument(monkeypatch):
    monkeypatch.setattr(bdutils.sys.stdout, "isatty", lambda: False, raising=False)
    assert bdutils.want_color() is False


def test_paint_wraps_the_text_in_the_named_color():
    assert bdutils.paint("hi", "red", True) == "\033[31mhi\033[0m"


def test_paint_composes_space_separated_attributes():
    painted = bdutils.paint("hi", "bold blue", True)
    assert painted == "\033[1m\033[34mhi\033[0m"


def test_paint_returns_the_text_untouched_when_disabled():
    assert bdutils.paint("hi", "red", False) == "hi"


def test_paint_leaves_empty_text_alone():
    """No point emitting escapes around nothing."""
    assert bdutils.paint("", "red", True) == ""


def test_paint_skips_unknown_names_rather_than_raising():
    """A miscolored line must never take down an otherwise working command."""
    assert bdutils.paint("hi", "chartreuse", True) == "hi"
    assert bdutils.paint("hi", "chartreuse red", True) == "\033[31mhi\033[0m"


def test_paint_defaults_to_enabled():
    assert bdutils.paint("hi", "green") == "\033[32mhi\033[0m"


def test_palette_avoids_the_bright_slots():
    """90-97 are greys in Solarized; the collection sticks to plain 30-37."""
    for name, code in bdutils.COLORS.items():
        number = code.removeprefix("\033[").removesuffix("m")
        assert not number.startswith("9"), f"{name} uses a bright slot"


def test_strip_ansi_removes_sgr_escapes():
    assert bdutils.strip_ansi("\033[31mred\033[0m") == "red"
    assert bdutils.strip_ansi("\033[1;32mboth\033[0m") == "both"
    assert bdutils.strip_ansi("plain") == "plain"


def test_strip_ansi_round_trips_paint():
    assert bdutils.strip_ansi(bdutils.paint("hi", "bold blue", True)) == "hi"


# --- run ------------------------------------------------------------------


def test_run_captures_output_and_honors_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("x")
    result = bdutils.run([sys.executable, "-c", "import os; print(os.listdir('.'))"], tmp_path)
    assert "marker.txt" in result.stdout
    assert result.returncode == 0


def test_run_does_not_raise_on_failure_by_default(tmp_path):
    result = bdutils.run([sys.executable, "-c", "import sys; sys.exit(7)"], tmp_path)
    assert result.returncode == 7


def test_run_raises_when_check_is_requested(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        bdutils.run([sys.executable, "-c", "import sys; sys.exit(7)"], tmp_path, check=True)


# --- have_dolt ------------------------------------------------------------


def test_have_dolt_reports_true_when_the_cli_is_on_path(fake_dolt):
    assert bdutils.have_dolt() is True


def test_have_dolt_reports_false_when_the_cli_is_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert bdutils.have_dolt() is False


def test_have_dolt_is_cached_within_a_test(tmp_path, monkeypatch):
    """Cached on purpose -- which is why conftest clears it around every test."""
    monkeypatch.setenv("PATH", str(tmp_path))
    assert bdutils.have_dolt() is False
    (tmp_path / "dolt").write_text("#!/bin/sh\n")
    (tmp_path / "dolt").chmod(0o755)
    assert bdutils.have_dolt() is False  # stale by design
    bdutils.have_dolt.cache_clear()
    assert bdutils.have_dolt() is True


# --- .beads/metadata.json -------------------------------------------------


def test_read_metadata_returns_the_database_and_mode(project):
    assert bdutils.read_metadata(project / ".beads") == ("testdb", "embedded")


def test_read_metadata_falls_back_to_unknown_for_absent_keys(tmp_path):
    (tmp_path / "metadata.json").write_text("{}")
    assert bdutils.read_metadata(tmp_path) == ("unknown", "unknown")


def test_read_metadata_errors_when_the_file_is_missing(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        bdutils.read_metadata(tmp_path)
    assert "no metadata.json" in str(excinfo.value.code)


def test_read_metadata_errors_on_malformed_json(tmp_path):
    (tmp_path / "metadata.json").write_text("{not json")
    with pytest.raises(SystemExit) as excinfo:
        bdutils.read_metadata(tmp_path)
    assert "could not read" in str(excinfo.value.code)


# --- Dolt database location and repo_state.json ---------------------------


@pytest.mark.parametrize("layout", ["embeddeddolt", "dolt"])
def test_locate_dolt_db_finds_both_layouts(tmp_path, layout):
    db = tmp_path / layout / "mydb"
    (db / ".dolt").mkdir(parents=True)
    assert bdutils.locate_dolt_db(tmp_path, "mydb") == db


def test_locate_dolt_db_prefers_the_embedded_layout(tmp_path):
    for layout in ("embeddeddolt", "dolt"):
        (tmp_path / layout / "mydb" / ".dolt").mkdir(parents=True)
    assert bdutils.locate_dolt_db(tmp_path, "mydb") == tmp_path / "embeddeddolt" / "mydb"


def test_locate_dolt_db_returns_none_when_there_is_no_dolt_marker(tmp_path):
    (tmp_path / "embeddeddolt" / "mydb").mkdir(parents=True)
    assert bdutils.locate_dolt_db(tmp_path, "mydb") is None


def write_repo_state(db_dir, payload) -> None:
    (db_dir / ".dolt").mkdir(parents=True, exist_ok=True)
    (db_dir / ".dolt" / "repo_state.json").write_text(
        payload if isinstance(payload, str) else json.dumps(payload)
    )


def test_read_repo_state_parses_the_file(tmp_path):
    write_repo_state(tmp_path, {"head": "refs/heads/main"})
    assert bdutils.read_repo_state(tmp_path) == {"head": "refs/heads/main"}


def test_read_repo_state_returns_empty_when_the_file_is_missing(tmp_path):
    assert bdutils.read_repo_state(tmp_path) == {}


def test_read_repo_state_returns_empty_on_malformed_json(tmp_path):
    """Degrade to "not verifiable" rather than crashing the caller."""
    write_repo_state(tmp_path, "{broken")
    assert bdutils.read_repo_state(tmp_path) == {}


@pytest.mark.parametrize(
    "head,expected",
    [
        ("refs/heads/main", "main"),
        ("refs/heads/feature/x", "feature/x"),
        ("", "main"),
        ("main", "main"),  # unprefixed value is not trusted; default wins
    ],
)
def test_get_head_branch_strips_the_refs_heads_prefix(tmp_path, head, expected):
    write_repo_state(tmp_path, {"head": head})
    assert bdutils.get_head_branch(tmp_path) == expected


def test_get_head_branch_defaults_to_main_without_a_repo_state(tmp_path):
    assert bdutils.get_head_branch(tmp_path) == "main"


def test_read_dolt_remotes_maps_names_to_urls(tmp_path):
    write_repo_state(tmp_path, {"remotes": {"origin": {"url": "https://example/db"}}})
    assert bdutils.read_dolt_remotes(tmp_path) == {"origin": "https://example/db"}


def test_read_dolt_remotes_marks_a_remote_with_no_url(tmp_path):
    write_repo_state(tmp_path, {"remotes": {"origin": {}}})
    assert bdutils.read_dolt_remotes(tmp_path) == {"origin": "?"}


@pytest.mark.parametrize("remotes", [{}, None])
def test_read_dolt_remotes_returns_empty_when_there_are_none(tmp_path, remotes):
    write_repo_state(tmp_path, {"remotes": remotes})
    assert bdutils.read_dolt_remotes(tmp_path) == {}


# --- Dolt plumbing (against a fake `dolt`) --------------------------------


def test_dolt_rev_returns_the_leading_hash(fake_dolt, tmp_path):
    fake_dolt.default(stdout="abc123 some commit message\n")
    assert bdutils.dolt_rev(tmp_path, "main") == "abc123"


def test_dolt_rev_strips_the_color_dolt_emits_even_when_piped(fake_dolt, tmp_path):
    fake_dolt.default(stdout="\033[33mabc123\033[0m message\n")
    assert bdutils.dolt_rev(tmp_path, "main") == "abc123"


def test_dolt_rev_returns_none_when_the_ref_does_not_resolve(fake_dolt, tmp_path):
    fake_dolt.default(stderr="unknown ref\n", exit_code=1)
    assert bdutils.dolt_rev(tmp_path, "nope") is None


def test_dolt_rev_returns_none_on_empty_output(fake_dolt, tmp_path):
    fake_dolt.default(stdout="\n")
    assert bdutils.dolt_rev(tmp_path, "main") is None


def test_dolt_rev_returns_none_without_the_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert bdutils.dolt_rev(tmp_path, "main") is None


def test_dolt_count_range_counts_non_blank_lines(fake_dolt, tmp_path):
    fake_dolt.default(stdout="a one\nb two\n\nc three\n")
    assert bdutils.dolt_count_range(tmp_path, "a..b") == 3


def test_dolt_count_range_returns_zero_for_an_empty_range(fake_dolt, tmp_path):
    fake_dolt.default(stdout="")
    assert bdutils.dolt_count_range(tmp_path, "a..b") == 0


def test_dolt_count_range_distinguishes_failure_from_zero(fake_dolt, tmp_path):
    """None means "could not tell"; 0 means "told, and it's none"."""
    fake_dolt.default(exit_code=1)
    assert bdutils.dolt_count_range(tmp_path, "a..b") is None


def test_dolt_log_range_returns_stripped_summaries(fake_dolt, tmp_path):
    fake_dolt.default(stdout="\033[33mabc\033[0m first\n\ndef second\n")
    assert bdutils.dolt_log_range(tmp_path, "a..b") == ["abc first", "def second"]


def test_dolt_log_range_returns_empty_on_failure(fake_dolt, tmp_path):
    fake_dolt.default(exit_code=1)
    assert bdutils.dolt_log_range(tmp_path, "a..b") == []


def test_dolt_sql_json_unwraps_the_rows_key(fake_dolt, tmp_path):
    fake_dolt.default(stdout=json.dumps({"rows": [{"a": 1}, {"a": 2}]}))
    assert bdutils.dolt_sql_json(tmp_path, "select 1") == [{"a": 1}, {"a": 2}]


def test_dolt_sql_json_returns_none_on_a_query_error(fake_dolt, tmp_path):
    fake_dolt.default(stderr="syntax error\n", exit_code=1)
    assert bdutils.dolt_sql_json(tmp_path, "select nope") is None


@pytest.mark.parametrize("payload", ["not json", "[1, 2, 3]"])
def test_dolt_sql_json_returns_none_on_unexpected_output(fake_dolt, tmp_path, payload):
    fake_dolt.default(stdout=payload)
    assert bdutils.dolt_sql_json(tmp_path, "select 1") is None


def test_dolt_table_columns_lists_the_field_names(fake_dolt, tmp_path):
    fake_dolt.default(
        stdout=json.dumps({"rows": [{"Field": "id"}, {"Field": "title"}, {"Type": "x"}]})
    )
    assert bdutils.dolt_table_columns(tmp_path, "issues") == ["id", "title"]


def test_dolt_table_columns_describes_the_plain_table_without_a_rev(fake_dolt, tmp_path):
    fake_dolt.default(stdout=json.dumps({"rows": []}))
    bdutils.dolt_table_columns(tmp_path, "issues")
    (argv,) = fake_dolt.calls
    assert "describe issues;" in argv


def test_dolt_table_columns_pins_the_table_to_a_revision(fake_dolt, tmp_path):
    fake_dolt.default(stdout=json.dumps({"rows": []}))
    bdutils.dolt_table_columns(tmp_path, "issues", rev="main")
    (argv,) = fake_dolt.calls
    assert "describe issues as of 'main';" in argv


def test_dolt_table_columns_escapes_a_quote_in_the_revision(fake_dolt, tmp_path):
    """A ref name may contain `'`, and `dolt sql -q` runs `;`-separated
    statements -- so an unescaped rev could break out of the string literal."""
    fake_dolt.default(stdout=json.dumps({"rows": []}))
    bdutils.dolt_table_columns(tmp_path, "issues", rev="oops'; drop table issues; --")
    (argv,) = fake_dolt.calls
    query = next(a for a in argv if a.startswith("describe"))
    assert query == "describe issues as of 'oops''; drop table issues; --';"


def test_dolt_table_columns_returns_empty_when_describe_fails(fake_dolt, tmp_path):
    fake_dolt.default(exit_code=1)
    assert bdutils.dolt_table_columns(tmp_path, "issues") == []


def test_dolt_fetch_reports_success_and_failure(fake_dolt, tmp_path):
    fake_dolt.default(exit_code=0)
    assert bdutils.dolt_fetch(tmp_path, "origin") is True
    fake_dolt.default(exit_code=1)
    assert bdutils.dolt_fetch(tmp_path, "origin") is False


def test_dolt_fetch_reports_false_without_the_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert bdutils.dolt_fetch(tmp_path, "origin") is False


# --- git remote -----------------------------------------------------------


def test_get_git_remote_url_reads_origin(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/r.git"],
        cwd=tmp_path, check=True,
    )
    assert bdutils.get_git_remote_url(tmp_path) == "https://example.com/r.git"


def test_get_git_remote_url_reports_no_remote(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert bdutils.get_git_remote_url(tmp_path) == "(no remote)"


# --- paged_output ---------------------------------------------------------


class _FakeStdout:
    """Minimal stdout stand-in whose tty-ness is dictated by the test.

    fileno() raises io.UnsupportedOperation, matching what a non-file stream
    (StringIO, pytest's capture object) does -- paged_output's broken-pipe
    handler catches OSError, and that is an OSError subclass.
    """

    def __init__(self, tty: bool):
        self._tty = tty
        self.written: list[str] = []

    def isatty(self) -> bool:
        return self._tty

    def fileno(self) -> int:
        raise io.UnsupportedOperation("fileno")

    def write(self, text: str) -> int:
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        pass


def _pager_recording_to(tmp_path, sink, capture: str) -> str:
    """A $PAGER command that records `capture` ('stdin' or 'LESS') into `sink`.

    Written as a script file rather than `python -c '...'` because $PAGER goes
    through shlex.split(), and nesting quotes inside it is a good way to test
    the quoting rather than the pager.
    """
    body = {
        "stdin": "import sys; open(SINK, 'w').write(sys.stdin.read())",
        "LESS": "import os; open(SINK, 'w').write(os.environ.get('LESS', ''))",
    }[capture]
    script = tmp_path / f"pager_{capture}.py"
    script.write_text(f"SINK = {str(sink)!r}\n{body}\n")
    return f"{sys.executable} {script}"


def test_paged_output_yields_stdout_when_it_is_not_a_tty(monkeypatch):
    fake = _FakeStdout(tty=False)
    monkeypatch.setattr(bdutils.sys, "stdout", fake)
    with bdutils.paged_output() as out:
        assert out is fake


def test_paged_output_yields_stdout_when_paging_is_disabled(monkeypatch):
    fake = _FakeStdout(tty=True)
    monkeypatch.setattr(bdutils.sys, "stdout", fake)
    monkeypatch.setenv("PAGER", "cat")
    with bdutils.paged_output(no_pager=True) as out:
        assert out is fake


def test_paged_output_pipes_through_the_pager_when_stdout_is_a_tty(monkeypatch, tmp_path):
    sink = tmp_path / "paged.txt"
    monkeypatch.setattr(bdutils.sys, "stdout", _FakeStdout(tty=True))
    monkeypatch.setenv("PAGER", _pager_recording_to(tmp_path, sink, "stdin"))
    with bdutils.paged_output() as out:
        print("through the pager", file=out)
    assert sink.read_text() == "through the pager\n"


def test_paged_output_sets_less_defaults_for_the_child(monkeypatch, tmp_path):
    """-FRX is what makes short output look like direct-to-stdout."""
    sink = tmp_path / "env.txt"
    monkeypatch.delenv("LESS", raising=False)
    monkeypatch.setattr(bdutils.sys, "stdout", _FakeStdout(tty=True))
    monkeypatch.setenv("PAGER", _pager_recording_to(tmp_path, sink, "LESS"))
    with bdutils.paged_output():
        pass
    assert sink.read_text() == "FRX"


def test_paged_output_respects_an_existing_less_setting(monkeypatch, tmp_path):
    sink = tmp_path / "env.txt"
    monkeypatch.setenv("LESS", "custom")
    monkeypatch.setattr(bdutils.sys, "stdout", _FakeStdout(tty=True))
    monkeypatch.setenv("PAGER", _pager_recording_to(tmp_path, sink, "LESS"))
    with bdutils.paged_output():
        pass
    assert sink.read_text() == "custom"


def test_paged_output_falls_back_to_stdout_when_the_pager_cannot_start(monkeypatch):
    fake = _FakeStdout(tty=True)
    monkeypatch.setattr(bdutils.sys, "stdout", fake)
    monkeypatch.setenv("PAGER", "/nonexistent/pager/binary")
    with bdutils.paged_output() as out:
        assert out is fake


def test_paged_output_swallows_a_broken_pipe_from_the_consumer(monkeypatch):
    """`… | head -1` closes the pipe early; that must not surface as a crash."""
    fake = _FakeStdout(tty=False)
    monkeypatch.setattr(bdutils.sys, "stdout", fake)
    with bdutils.paged_output(no_pager=True):
        raise BrokenPipeError


def test_paged_output_does_not_swallow_other_exceptions(monkeypatch):
    monkeypatch.setattr(bdutils.sys, "stdout", _FakeStdout(tty=False))
    with pytest.raises(ValueError):
        with bdutils.paged_output(no_pager=True):
            raise ValueError("real bug")
