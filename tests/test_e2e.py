"""End-to-end runs: each script as a real subprocess.

These catch what in-process tests structurally cannot -- argparse wiring, the
sibling `from bdutils import ...` import resolving off sys.path[0], and the
exit code the shell actually sees. Output assertions are deliberately narrow
(one key line, not the whole render); the detailed behavior lives in the
per-script unit tests.

Note that piping stdout inverts two defaults: want_color('auto') is False and
_open_pager() returns None, so these runs are plain and unpaged unless a flag
says otherwise. That is the same thing that happens in a pipeline, which is
why it is the right default to assert against.
"""
from __future__ import annotations

import csv
import json

import pytest

import bdutils

from conftest import ROOT, write_session

pytestmark = pytest.mark.e2e

SCRIPTS = [
    "bd-complete", "bd-dolt-check", "bd-dolt-diff", "bd-export-csv",
    "bd-log", "bd-view", "claude-session-find", "claude-session-list",
    "claude-session-report",
]


def issue(iid, **fields):
    base = {
        "id": iid, "title": f"Title {iid}", "status": "open", "priority": 2,
        "issue_type": "task", "created_at": "2026-04-01T13:05:00Z",
    }
    base.update(fields)
    return base


# --- Every script, uniformly ---------------------------------------------


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_reports_the_shared_version(script, run_script):
    """The collection versions as one unit -- this is CI's smoke test too."""
    result = run_script(script, "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{script} {bdutils.__version__}"


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_has_working_help(script, run_script):
    result = run_script(script, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_the_script_list_matches_what_the_repo_ships():
    """A new script must be added here, the way CI discovers them by shebang."""
    shipped = {
        p.name for p in ROOT.iterdir()
        if p.is_file() and p.stat().st_mode & 0o111
        and p.read_bytes()[:2] == b"#!"
    }
    assert shipped == set(SCRIPTS)


# --- bd-log ---------------------------------------------------------------


def test_bd_log_renders_events_newest_first(run_script, fake_bd):
    fake_bd.issues([
        issue("p-1", created_at="2026-04-01T10:00:00Z"),
        issue("p-2", created_at="2026-04-02T10:00:00Z"),
    ])
    result = run_script("bd-log")
    assert result.returncode == 0, result.stderr
    lines = [ln for ln in result.stdout.splitlines() if ln.startswith("+")]
    assert lines[0].split()[3] == "p-2"
    assert lines[1].split()[3] == "p-1"


def test_bd_log_reports_when_nothing_matches(run_script, fake_bd):
    fake_bd.issues([])
    result = run_script("bd-log")
    assert result.returncode == 0
    assert result.stdout.strip() == "no matching events"


def test_bd_log_only_narrows_the_event_kinds(run_script, fake_bd):
    fake_bd.issues([issue("p-1", closed_at="2026-04-03T10:00:00Z")])
    result = run_script("bd-log", "--only=close")
    assert "✓" in result.stdout
    assert "+" not in result.stdout


def test_bd_log_limit_trims_the_list(run_script, fake_bd):
    fake_bd.issues([issue(f"p-{i}", created_at=f"2026-04-0{i}T10:00:00Z")
                    for i in range(1, 5)])
    result = run_script("bd-log", "-n", "2")
    assert len([ln for ln in result.stdout.splitlines() if ln.startswith("+")]) == 2


def test_bd_log_rejects_a_negative_limit(run_script, fake_bd):
    result = run_script("bd-log", "-n", "-1")
    assert result.returncode != 0
    assert "error: --limit must be >= 0" in result.stderr


def test_bd_log_requires_id_alongside_children(run_script, fake_bd):
    result = run_script("bd-log", "--children")
    assert result.returncode != 0
    assert "--children needs --id" in result.stderr


def test_bd_log_warns_about_an_id_with_no_events(run_script, fake_bd):
    fake_bd.issues([])
    result = run_script("bd-log", "--id", "p-nope")
    assert result.returncode == 0
    assert "warning: no events for: p-nope (not found)" in result.stderr


def test_bd_log_names_only_the_filters_actually_passed(run_script, fake_bd):
    """Listing every filter that *could* explain the absence misleads."""
    fake_bd.issues([])
    result = run_script("bd-log", "--id", "p-nope", "--open")
    assert "excluded by --open" in result.stderr
    assert "--since" not in result.stderr


def test_bd_log_id_warning_fires_before_the_limit_trims(run_script, fake_bd):
    """Deliberate: -n cutting a bead's events off must not read as "missing".

    p-1 and p-2 both have events, but `-n 1` shows only one of them. Neither id
    may be warned about -- the check runs against the full event list.
    """
    fake_bd.issues([
        issue("p-1", created_at="2026-04-01T10:00:00Z"),
        issue("p-2", created_at="2026-04-02T10:00:00Z"),
    ])
    result = run_script("bd-log", "--id", "p-1,p-2", "-n", "1")
    assert result.returncode == 0, result.stderr
    assert "warning:" not in result.stderr
    assert len([ln for ln in result.stdout.splitlines() if ln.startswith("+")]) == 1


def test_bd_log_since_filters_by_date(run_script, fake_bd):
    fake_bd.issues([
        issue("p-old", created_at="2026-03-01T10:00:00Z"),
        issue("p-new", created_at="2026-04-02T10:00:00Z"),
    ])
    result = run_script("bd-log", "--since", "2026-04-01")
    assert result.returncode == 0, result.stderr
    assert "p-new" in result.stdout
    assert "p-old" not in result.stdout


def test_bd_log_since_is_named_in_the_id_warning_when_it_is_the_cause(
        run_script, fake_bd):
    fake_bd.issues([issue("p-1", created_at="2026-03-01T10:00:00Z")])
    result = run_script("bd-log", "--id", "p-1", "--since", "2026-04-01")
    assert "excluded by --since" in result.stderr


def test_bd_log_children_walks_the_whole_subtree(run_script, fake_bd):
    fake_bd.issues([
        issue("p-root"),
        issue("p-mid", parent="p-root"),
        issue("p-leaf", parent="p-mid"),
        issue("p-other"),
    ])
    result = run_script("bd-log", "--id", "p-root", "--children")
    assert result.returncode == 0, result.stderr
    assert "p-leaf" in result.stdout
    assert "p-other" not in result.stdout


def test_bd_log_oneline_emits_exactly_one_row_per_event(run_script, fake_bd):
    """Two events, two lines -- no title line, and no blank separator either."""
    fake_bd.issues([
        issue("p-1", title="First", created_at="2026-04-01T10:00:00Z",
              closed_at="2026-04-02T10:00:00Z", close_reason="a whole "
              "paragraph that the block form would put on its own line"),
    ])
    result = run_script("bd-log", "--oneline")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert all(ln.strip() for ln in lines)
    assert all("First" in ln for ln in lines)
    assert "paragraph" not in result.stdout


def test_bd_log_oneline_aligns_the_id_column_across_rows(run_script, fake_bd):
    fake_bd.issues([
        issue("p-1", title="Short id", created_at="2026-04-01T10:00:00Z"),
        issue("p-considerably-longer", title="Long id",
              created_at="2026-04-02T10:00:00Z"),
    ])
    result = run_script("bd-log", "--oneline")
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert [ln.index("Short id") for ln in lines if "Short id" in ln] == \
           [ln.index("Long id") for ln in lines if "Long id" in ln]


def test_bd_log_oneline_sizes_columns_after_the_limit_trims(run_script, fake_bd):
    """A long id that -n cut off must not pad the rows that survived."""
    fake_bd.issues([
        issue("p-1", title="Kept", created_at="2026-04-02T10:00:00Z"),
        issue("p-considerably-longer", title="Trimmed",
              created_at="2026-04-01T10:00:00Z"),
    ])
    result = run_script("bd-log", "--oneline", "-n", "1")
    assert result.stdout.splitlines() == [
        "+ 2026-04-02 10:00  p-1  P2 task  Kept",
    ]


def test_bd_log_oneline_keeps_the_per_kind_color(run_script, fake_bd):
    fake_bd.issues([issue("p-1")])
    result = run_script("bd-log", "--oneline", "--color=always")
    assert "\033[34m" in result.stdout


def test_bd_log_color_always_survives_a_pipe(run_script, fake_bd):
    fake_bd.issues([issue("p-1")])
    result = run_script("bd-log", "--color=always")
    assert "\033[34m" in result.stdout


def test_bd_log_color_never_suppresses_the_escapes(run_script, fake_bd):
    """--color=never, not the bare default.

    Asserting that a *piped* default run is plain proves nothing: the pipe
    already makes want_color("auto") false, so the assertion survives deleting
    the isatty check entirely. The auto branch is covered by the unit test that
    patches isatty; here only an explicit mode is falsifiable.
    """
    fake_bd.issues([issue("p-1")])
    assert "\033[" not in run_script("bd-log", "--color=never").stdout


def test_bd_log_color_always_overrides_no_color(run_script, fake_bd):
    """An explicit --color beats the environment; NO_COLOR only governs 'auto'.

    Asserting NO_COLOR with *no* --color flag would prove nothing here: piped
    stdout already makes 'auto' resolve to False, so the assertion would hold
    with the NO_COLOR check deleted. The unit test that patches isatty is the
    one covering that branch.
    """
    fake_bd.issues([issue("p-1")])
    result = run_script("bd-log", "--color=always", env={"NO_COLOR": "1"})
    assert "\033[34m" in result.stdout


def test_bd_log_rejects_a_directory_that_is_not_a_beads_project(run_script, tmp_path):
    result = run_script("bd-log", str(tmp_path))
    assert result.returncode != 0
    assert "no .beads/ directory" in result.stderr


def test_bd_log_rejects_an_unknown_event_kind(run_script, fake_bd):
    result = run_script("bd-log", "--only=finish")
    assert result.returncode != 0
    assert "unknown event kind(s): finish" in result.stderr


def test_bd_log_refuses_status_together_with_open(run_script, fake_bd):
    result = run_script("bd-log", "--status=open", "--open")
    assert result.returncode == 2
    assert "not allowed with" in result.stderr


# --- bd-export-csv --------------------------------------------------------


def test_bd_export_csv_writes_a_csv_and_prints_its_path(run_script, fake_bd, tmp_path):
    fake_bd.default(stdout="\n".join(
        json.dumps(issue(i)) for i in ("beads-1", "beads-2")
    ))
    out_path = tmp_path / "out.csv"
    result = run_script("bd-export-csv", ".", "-o", str(out_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(out_path.resolve())

    with out_path.open() as f:
        rows = list(csv.DictReader(f))
    assert [r["id"] for r in rows] == ["beads-1", "beads-2"]
    assert rows[0]["type"] == "task"


def test_bd_export_csv_sorts_by_the_requested_keys(run_script, fake_bd, tmp_path):
    fake_bd.default(stdout="\n".join(
        json.dumps(issue(i, priority=p)) for i, p in (("b-1", 3), ("b-2", 1))
    ))
    out_path = tmp_path / "out.csv"
    run_script("bd-export-csv", ".", "-o", str(out_path), "--sort=priority")
    with out_path.open() as f:
        assert [r["id"] for r in csv.DictReader(f)] == ["b-2", "b-1"]


def test_bd_export_csv_writes_a_header_only_file_for_an_empty_project(
        run_script, fake_bd, tmp_path):
    fake_bd.default(stdout="")
    out_path = tmp_path / "out.csv"
    result = run_script("bd-export-csv", ".", "-o", str(out_path))
    assert result.returncode == 0
    assert "warning: no issues in project" in result.stderr
    assert out_path.read_text().startswith("id,title,type")


def test_bd_export_csv_rejects_an_unknown_sort_key(run_script, fake_bd, tmp_path):
    result = run_script("bd-export-csv", ".", "--sort=nonsense")
    assert result.returncode != 0
    assert "unknown key 'nonsense'" in result.stderr


# --- bd-complete ----------------------------------------------------------


def test_bd_complete_ids_emits_tab_separated_candidates(run_script, fake_bd):
    fake_bd.issues([issue("beads-utils-v9o", title="A title")])
    result = run_script("bd-complete", "ids")
    assert result.returncode == 0
    assert result.stdout == "beads-utils-v9o\tA title\n"


def test_bd_complete_stays_silent_and_succeeds_when_bd_fails(run_script, fake_bd):
    """A completion helper must never garble the prompt."""
    fake_bd.default(stderr="boom\n", exit_code=1)
    result = run_script("bd-complete", "ids")
    assert result.returncode == 0
    assert result.stdout == ""


# --- bd-view --------------------------------------------------------------


def test_bd_view_renders_a_bead(run_script, fake_bd):
    fake_bd.json_rule("show", payload=[issue("b-1", description="The **body**.")])
    fake_bd.json_rule("dep", payload=[])
    fake_bd.json_rule("comments", payload=[])
    result = run_script("bd-view", "b-1")
    assert result.returncode == 0, result.stderr
    assert "b-1" in result.stdout
    assert "Title b-1" in result.stdout


def test_bd_view_reports_an_unknown_bead_without_a_traceback(run_script, fake_bd):
    fake_bd.default(stdout=json.dumps({"error": "issue not found: b-9"}), exit_code=1)
    result = run_script("bd-view", "b-9")
    assert result.returncode != 0
    assert result.stderr.startswith("error: ")
    assert "Traceback" not in result.stderr


# --- bd-dolt-check / bd-dolt-diff ----------------------------------------


def test_bd_dolt_check_rejects_a_non_beads_directory(run_script, tmp_path):
    result = run_script("bd-dolt-check", str(tmp_path))
    assert result.returncode != 0
    assert "no .beads/ directory" in result.stderr


def test_bd_dolt_diff_rejects_a_non_beads_directory(run_script, tmp_path):
    result = run_script("bd-dolt-diff", str(tmp_path))
    assert result.returncode != 0
    assert "no .beads/ directory" in result.stderr


# --- Claude session scripts ----------------------------------------------


@pytest.fixture
def fake_home(tmp_path, project):
    """A HOME whose ~/.claude/projects holds sessions for `project`.

    Two sessions, deliberately: one real conversation carrying every content
    channel the report script can toggle (prose, a slash command with its skill
    body, a tool call and its result), and one `/clear` ghost whose only entry
    is wrapper plumbing -- which is what the empty-session filter exists for.
    """
    home = tmp_path / "home"
    projects = home / ".claude" / "projects"
    mangled = str(project).replace("/", "-").replace(".", "-")
    pdir = projects / mangled

    write_session(pdir, "abcd1234-ef56-7890", [
        {"type": "custom-title", "customTitle": "A recorded session"},
        {"type": "user", "uuid": "u1", "cwd": str(project),
         "timestamp": "2026-05-27T09:11:00Z",
         "message": {"role": "user", "content": "please fix the pager"}},
        # A slash command, plus the skill body Claude Code injects as its child.
        {"type": "user", "uuid": "u2", "timestamp": "2026-05-27T09:12:00Z",
         "message": {"role": "user", "content":
                     "<command-message>finalize</command-message>"
                     "<command-name>/finalize</command-name>"
                     "<command-args>beads-utils-86m</command-args>"}},
        {"type": "user", "uuid": "u3", "parentUuid": "u2",
         "timestamp": "2026-05-27T09:12:01Z",
         "message": {"role": "user", "content": "BOILERPLATE_SKILL_BODY step one"}},
        {"type": "assistant", "timestamp": "2026-05-27T09:13:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "on it"},
             {"type": "tool_use", "id": "t1", "name": "Bash",
              "input": {"command": "TOOL_INPUT_MARKER"}},
         ]}},
        {"type": "user", "uuid": "u4", "timestamp": "2026-05-27T09:13:05Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t1",
              "content": "TOOL_RESULT_MARKER"},
         ]}},
    ])

    # A `/clear` ghost: a user entry made entirely of wrapper tags, so
    # has_human_prose() finds nothing and the session counts as 0p/0r.
    write_session(pdir, "ffff0000-0000-0000", [
        {"type": "user", "cwd": str(project), "timestamp": "2026-05-27T08:00:00Z",
         "message": {"role": "user", "content":
                     "<command-name>/clear</command-name>"
                     "<local-command-stdout></local-command-stdout>"}},
    ])
    return home


def test_claude_session_list_shows_the_current_projects_session(run_script, fake_home):
    result = run_script("claude-session-list", env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "abcd1234-ef56-7890" in result.stdout
    # 2, not 4, from the four user entries: the /finalize turn is pure wrapper
    # tags and the tool-result turn carries no prose, so has_human_prose()
    # excludes both. Only the typed prompt and the skill body count.
    assert "2 prompts / 1 reply" in result.stdout
    assert "A recorded session" in result.stdout


def test_claude_session_list_hides_a_clear_ghost_and_says_so(run_script, fake_home):
    """A wrapper-only session registers 0p/0r; that's what the filter is for."""
    result = run_script("claude-session-list", env={"HOME": str(fake_home)})
    assert "ffff0000-0000-0000" not in result.stdout
    assert "(1 empty session hidden; use --all to show)" in result.stderr


def test_claude_session_list_all_brings_the_empty_session_back(run_script, fake_home):
    result = run_script("claude-session-list", "-a", env={"HOME": str(fake_home)})
    assert "ffff0000-0000-0000" in result.stdout
    assert "0 prompts / 0 replies" in result.stdout
    assert "hidden" not in result.stderr


def test_claude_session_list_min_prompts_is_stricter_than_the_default(
        run_script, fake_home):
    result = run_script("claude-session-list", "--min-prompts", "4",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0
    assert "abcd1234" not in result.stdout
    assert "no sessions to show" in result.stdout


def test_claude_session_list_refuses_all_together_with_min_prompts(
        run_script, fake_home):
    result = run_script("claude-session-list", "-a", "--min-prompts", "1",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 2
    assert "not allowed with" in result.stderr


def test_claude_session_list_quiet_suppresses_the_hidden_count_footer(
        run_script, fake_home):
    """-q output feeds a pipe; a footer would be noise even on stderr."""
    result = run_script("claude-session-list", "-q", env={"HOME": str(fake_home)})
    assert result.stderr == ""


def test_claude_session_list_errors_for_a_project_with_no_sessions(
        run_script, fake_home, tmp_path):
    elsewhere = tmp_path / "unrecorded"
    (elsewhere / ".beads").mkdir(parents=True)
    result = run_script("claude-session-list", cwd=elsewhere,
                        env={"HOME": str(fake_home)})
    assert result.returncode != 0
    assert "no Claude sessions recorded" in result.stderr
    assert "Traceback" not in result.stderr


def test_claude_session_list_oneline_prints_a_header(run_script, fake_home):
    result = run_script("claude-session-list", "--oneline", env={"HOME": str(fake_home)})
    assert result.stdout.splitlines()[0].startswith("ID")
    assert "COUNTS" in result.stdout.splitlines()[0]


def test_claude_session_list_quiet_prints_only_uuids(run_script, fake_home):
    """Pipe-friendly: the output feeds `claude --resume`."""
    result = run_script("claude-session-list", "-q", env={"HOME": str(fake_home)})
    assert result.stdout.strip() == "abcd1234-ef56-7890"


def test_claude_session_list_global_spans_every_project(run_script, fake_home,
                                                        tmp_path):
    other = fake_home / ".claude" / "projects" / "-some-other-project"
    write_session(other, "9999aaaa-bbbb-cccc", [
        {"type": "custom-title", "customTitle": "Elsewhere"},
        {"type": "user", "cwd": "/some/other/project",
         "timestamp": "2026-05-27T07:00:00Z",
         "message": {"role": "user", "content": "a prompt"}},
    ])
    result = run_script("claude-session-list", "-g", env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "9999aaaa-bbbb-cccc" in result.stdout
    assert "abcd1234-ef56-7890" in result.stdout
    assert "project" in result.stdout  # the project label line -g adds


def test_claude_session_find_locates_a_matching_session(run_script, fake_home):
    result = run_script("claude-session-find", "pager", env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "abcd1234-ef56-7890" in result.stdout


def test_claude_session_find_quiet_prints_only_uuids(run_script, fake_home):
    result = run_script("claude-session-find", "-q", "pager", env={"HOME": str(fake_home)})
    assert result.stdout.strip() == "abcd1234-ef56-7890"


def test_claude_session_find_oneline_drops_the_snippet_lines(run_script,
                                                             fake_home):
    """One line per hit, carrying the same fields, with the snippets gone.

    Not "identical to the block form's first line": --oneline pads the project
    label to align the columns, so the two forms diverge the moment two hits
    have labels of different widths. That padding is covered separately, by
    the --global test below -- it cannot be reached here, where every hit
    comes from one project dir and therefore shares one label.
    """
    block = run_script("claude-session-find", "pager",
                       env={"HOME": str(fake_home)})
    assert any(ln.startswith('  "') for ln in block.stdout.splitlines())

    result = run_script("claude-session-find", "--oneline", "pager",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    assert "abcd1234-ef56-7890" in lines[0]
    assert "(1 hit)" in lines[0]


def test_claude_session_find_oneline_aligns_across_project_labels(run_script,
                                                                  fake_home):
    """The label padding, which is the whole point of the --oneline layout.

    It can only ever do anything under --global: within one project dir every
    hit shares a label, so max() equals every element and the padding is a
    no-op. The default-scope test above therefore passes without touching this
    code at all -- a second project with a deliberately longer name is the
    only way to reach it.
    """
    other = fake_home / ".claude" / "projects" / "-a-much-longer-project-name"
    write_session(other, "9999aaaa-bbbb-cccc", [
        # Label is the cwd's basename, so this one is 26 chars against the
        # `project` fixture's 7 -- the width gap the padding has to close.
        {"type": "user", "cwd": "/somewhere/a-much-longer-project-name",
         "timestamp": "2026-05-27T07:00:00Z",
         "message": {"role": "user", "content": "please fix the pager here too"}},
    ])
    result = run_script("claude-session-find", "-g", "--oneline", "pager",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    # Both uuids start at the same column despite labels of different lengths.
    columns = {ln.index(ln.split()[3]) for ln in lines}
    assert len(columns) == 1, lines


def test_claude_session_find_rejects_oneline_with_quiet(run_script, fake_home):
    result = run_script("claude-session-find", "--oneline", "-q", "pager",
                        env={"HOME": str(fake_home)})
    assert result.returncode != 0
    assert "not allowed with" in result.stderr


def test_claude_session_find_global_spans_every_project(run_script, fake_home):
    """Covers main()'s --global branch, which walks CLAUDE_PROJECTS directly.

    Added because folding the duplicated helpers into claudeutils
    (beads-utils-8ju) touched exactly this list comprehension, and nothing
    else in the suite reaches it: the default branch goes through
    find_project_dir instead, and a missing projects directory exits at the
    guard several lines earlier.
    """
    other = fake_home / ".claude" / "projects" / "-some-other-project"
    write_session(other, "9999aaaa-bbbb-cccc", [
        {"type": "user", "cwd": "/some/other/project",
         "timestamp": "2026-05-27T07:00:00Z",
         "message": {"role": "user", "content": "please fix the pager elsewhere"}},
    ])
    scoped = run_script("claude-session-find", "pager", env={"HOME": str(fake_home)})
    assert "9999aaaa-bbbb-cccc" not in scoped.stdout  # cwd's project only

    result = run_script("claude-session-find", "-g", "pager",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "9999aaaa-bbbb-cccc" in result.stdout
    assert "abcd1234-ef56-7890" in result.stdout


def test_claude_session_find_all_searches_tool_content(run_script, fake_home):
    """-a widens the search domain past human-typed prose."""
    default = run_script("claude-session-find", "TOOL_INPUT_MARKER",
                         env={"HOME": str(fake_home)})
    assert "abcd1234" not in default.stdout
    widened = run_script("claude-session-find", "-a", "TOOL_INPUT_MARKER",
                         env={"HOME": str(fake_home)})
    assert widened.returncode == 0, widened.stderr
    assert "abcd1234-ef56-7890" in widened.stdout


def test_claude_session_find_reports_no_match(run_script, fake_home):
    """Exit 1 and a stderr line -- an empty stdout alone would also be true of
    a crash, or of any of the script's six early error() exits."""
    result = run_script("claude-session-find", "zzz-absent",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 1
    assert "no matching sessions" in result.stderr
    assert "abcd1234" not in result.stdout


def test_claude_session_report_renders_the_discussion(run_script, fake_home):
    result = run_script("claude-session-report", "abcd1234-ef56-7890",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "# Session: A recorded session" in result.stdout
    assert "## User" in result.stdout
    assert "please fix the pager" in result.stdout
    assert "## Claude" in result.stdout
    assert "on it" in result.stdout


def test_claude_session_report_resolves_a_title_substring(run_script, fake_home):
    result = run_script("claude-session-report", "recorded",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "please fix the pager" in result.stdout


def test_claude_session_report_reports_an_unknown_session(run_script, fake_home):
    result = run_script("claude-session-report", "no-such-session",
                        env={"HOME": str(fake_home)})
    assert result.returncode != 0
    assert "no session found" in result.stderr
    assert "Traceback" not in result.stderr


def test_claude_session_report_hides_the_opt_in_channels_by_default(
        run_script, fake_home):
    """The default render is the *discussion*: prose, replies, slash commands.

    The absence assertions are the point. Tool I/O and the repeated-verbatim
    skill body are the bulk of a raw transcript, and leaving them out is what
    makes the default readable.
    """
    result = run_script("claude-session-report", "abcd1234-ef56-7890",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    assert "please fix the pager" in result.stdout      # prompts: on
    assert "/finalize" in result.stdout                 # slash commands: on
    assert "TOOL_INPUT_MARKER" not in result.stdout     # tools: off
    assert "TOOL_RESULT_MARKER" not in result.stdout
    assert "BOILERPLATE_SKILL_BODY" not in result.stdout  # slash bodies: off


def test_claude_session_report_tools_flag_adds_tool_io(run_script, fake_home):
    result = run_script("claude-session-report", "abcd1234-ef56-7890", "--tools",
                        env={"HOME": str(fake_home)})
    assert "TOOL_INPUT_MARKER" in result.stdout
    assert "TOOL_RESULT_MARKER" in result.stdout
    assert "BOILERPLATE_SKILL_BODY" not in result.stdout  # still off


def test_claude_session_report_slash_bodies_flag_adds_the_skill_body(
        run_script, fake_home):
    result = run_script("claude-session-report", "abcd1234-ef56-7890",
                        "--slash-bodies", env={"HOME": str(fake_home)})
    assert "BOILERPLATE_SKILL_BODY" in result.stdout
    assert "<details>" in result.stdout                   # collapsed on GitHub
    assert "TOOL_INPUT_MARKER" not in result.stdout       # still off


def test_claude_session_report_all_turns_on_every_channel(run_script, fake_home):
    result = run_script("claude-session-report", "abcd1234-ef56-7890", "--all",
                        env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stderr
    for marker in ("please fix the pager", "/finalize",
                   "TOOL_INPUT_MARKER", "TOOL_RESULT_MARKER",
                   "BOILERPLATE_SKILL_BODY"):
        assert marker in result.stdout, marker


def test_claude_session_report_no_prompts_drops_the_human_turns(run_script, fake_home):
    result = run_script("claude-session-report", "abcd1234-ef56-7890",
                        "--no-prompts", env={"HOME": str(fake_home)})
    assert "please fix the pager" not in result.stdout
    assert "on it" in result.stdout    # replies stay on


# --- Cross-cutting --------------------------------------------------------


@pytest.mark.parametrize("script", ["bd-log", "bd-dolt-diff"])
def test_paging_scripts_accept_no_pager(script, run_script, fake_bd):
    fake_bd.issues([])
    result = run_script(script, "--no-pager")
    assert "unrecognized arguments" not in result.stderr


def test_bd_view_accepts_no_pager(run_script, fake_bd):
    """Run bd-view for real rather than pairing --no-pager with --help.

    argparse exits during parsing for --help, and for a missing required
    positional, in both cases *before* the unknown-argument check runs -- so
    either shortcut would pass with --no-pager deleted from the parser.
    """
    fake_bd.json_rule("show", payload=[issue("b-1")])
    fake_bd.json_rule("dep", payload=[])
    fake_bd.json_rule("comments", payload=[])
    result = run_script("bd-view", "b-1", "--no-pager")
    assert result.returncode == 0, result.stderr
    assert "unrecognized arguments" not in result.stderr


@pytest.mark.parametrize(
    "mode,colored", [("always", True), ("never", False), ("auto", False)],
)
def test_bd_log_accepts_every_color_mode(mode, colored, run_script, fake_bd):
    """Each mode must reach want_color and produce the matching output.

    The issue list must be non-empty: bd-log prints "no matching events" and
    returns *before* want_color() is called, so an empty fixture would make
    all three modes produce byte-identical output and assert nothing. ("auto"
    is False here only because stdout is piped -- see the --color=never test.)
    """
    fake_bd.issues([issue("p-1")])
    result = run_script("bd-log", f"--color={mode}")
    assert result.returncode == 0, result.stderr
    assert ("\033[" in result.stdout) is colored


def test_no_script_prints_a_traceback_for_a_bad_project_path(run_script, tmp_path):
    """The convention: errors are one lowercase line, never a traceback."""
    for script in ("bd-log", "bd-export-csv", "bd-dolt-check", "bd-dolt-diff"):
        result = run_script(script, str(tmp_path))
        assert "Traceback" not in result.stderr, script
        assert result.stderr.startswith("error: "), script
