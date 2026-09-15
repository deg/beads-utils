"""Tests for bd-dolt-check.

The exit code is the contract here: 0 means "in sync, or not verifiable", 1
means "there is unpushed data". CI gates on it, so the status/exit-code pairs
below are the load-bearing assertions.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from conftest import load_script

bd_dolt_check = load_script("bd-dolt-check")


# --- derive_dolt_remote_url -----------------------------------------------


@pytest.mark.parametrize(
    "git_url,expected",
    [
        ("git@github.com:owner/repo.git", "git+ssh://git@github.com/owner/repo.git"),
        ("git@gitlab.com:group/sub/repo", "git+ssh://git@gitlab.com/group/sub/repo"),
        ("https://github.com/owner/repo.git", "git+https://github.com/owner/repo.git"),
        ("http://example.com/r", "git+http://example.com/r"),
        # Already Dolt-flavored: pass through untouched.
        ("git+ssh://git@github.com/o/r", "git+ssh://git@github.com/o/r"),
        ("git+https://github.com/o/r", "git+https://github.com/o/r"),
        ("az://container/db", "az://container/db"),
    ],
)
def test_derive_dolt_remote_url_translates_known_forms(git_url, expected):
    assert bd_dolt_check.derive_dolt_remote_url(git_url) == expected


@pytest.mark.parametrize(
    "git_url",
    ["", "(no remote)", "ssh://git@github.com/o/r", "/local/path", "file:///tmp/r"],
)
def test_derive_dolt_remote_url_declines_to_guess(git_url):
    """No suggestion is better than a wrong one the user would paste."""
    assert bd_dolt_check.derive_dolt_remote_url(git_url) is None


# --- get_remote_dolt_ref --------------------------------------------------


def make_git_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


def test_get_remote_dolt_ref_returns_the_hash_from_ls_remote(project, monkeypatch, tmp_path):
    fake = tmp_path / "gitbin"
    fake.mkdir()
    script = fake / "git"
    script.write_text(
        "#!/bin/sh\n"
        "echo 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\trefs/dolt/data'\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{__import__('os').environ['PATH']}")
    assert bd_dolt_check.get_remote_dolt_ref(project) == "deadbeef" * 5


def test_get_remote_dolt_ref_returns_none_when_the_ref_is_absent(project, tmp_path):
    make_git_repo(project)
    assert bd_dolt_check.get_remote_dolt_ref(project) is None


# --- get_recent_dolt_log --------------------------------------------------


def test_get_recent_dolt_log_returns_stripped_lines(fake_dolt, tmp_path):
    fake_dolt.default(stdout="\033[33mabc\033[0m first\n\ndef second\n")
    assert bd_dolt_check.get_recent_dolt_log(tmp_path) == ["abc first", "def second"]


def test_get_recent_dolt_log_passes_the_requested_count(fake_dolt, tmp_path):
    fake_dolt.default(stdout="")
    bd_dolt_check.get_recent_dolt_log(tmp_path, n=3)
    (argv,) = fake_dolt.calls
    assert argv == ["log", "--oneline", "-n", "3"]


def test_get_recent_dolt_log_returns_empty_when_dolt_errors(fake_dolt, tmp_path):
    fake_dolt.default(exit_code=1)
    assert bd_dolt_check.get_recent_dolt_log(tmp_path) == []


def test_get_recent_dolt_log_returns_empty_without_the_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert bd_dolt_check.get_recent_dolt_log(tmp_path) == []


# --- main(): exit codes ---------------------------------------------------


@pytest.fixture
def dolt_project(project):
    """A beads project whose embedded Dolt database dir exists."""
    db = project / ".beads" / "embeddeddolt" / "testdb"
    (db / ".dolt").mkdir(parents=True)
    (db / ".dolt" / "repo_state.json").write_text(json.dumps({
        "head": "refs/heads/main",
        "remotes": {"origin": {"url": "git+ssh://git@github.com/o/r"}},
    }))
    return project


@pytest.fixture
def server_dolt_project(dolt_project):
    """dolt_project, but in server mode.

    conftest's `project` fixture hardcodes dolt_mode=embedded, so every main()
    test ran in the mode where `bd dolt commit` happens to work. That blind
    spot let the BEHIND action line tell a server-mode user to run a command
    the working-set section above had just declared a no-op.
    """
    meta = dolt_project / ".beads" / "metadata.json"
    data = json.loads(meta.read_text())
    data["dolt_mode"] = "server"
    meta.write_text(json.dumps(data))
    return dolt_project


def run_main(monkeypatch, path, argv_extra=()):
    monkeypatch.setattr(bd_dolt_check.sys, "argv",
                        ["bd-dolt-check", str(path), *argv_extra])
    return bd_dolt_check.main()


def working_set(fake_dolt, *rows):
    """Program the `dolt_status` query, ahead of any other rule.

    Rules match on substring and first-match-wins, so this has to be
    registered before the `dolt log` ones. Without it a test's broad
    .default() answers the status query with non-JSON, which reads as "could
    not look" rather than "clean" -- the two states this check distinguishes.
    """
    payload = {"rows": list(rows)} if rows else {}
    return fake_dolt.rule("dolt_status", stdout=json.dumps(payload))


def modified(table):
    return {"table_name": table, "staged": "0", "status": "modified"}


def install_fake_git(tmp_path, monkeypatch, ls_remote_output):
    bindir = tmp_path / "gitbin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "git"
    script.write_text(f"#!/bin/sh\nprintf '%s' {ls_remote_output!r}\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return bindir


def test_main_exits_one_when_the_remote_has_no_dolt_data(dolt_project, monkeypatch,
                                                         tmp_path, capsys):
    install_fake_git(tmp_path, monkeypatch, "")
    assert run_main(monkeypatch, dolt_project) == 1
    assert "NOT FOUND" in capsys.readouterr().out


def test_main_suggests_a_remote_url_when_none_is_configured(project, monkeypatch,
                                                            tmp_path, capsys):
    """No .dolt dir at all -> no configured remotes -> show how to add one."""
    install_fake_git(tmp_path, monkeypatch, "")
    monkeypatch.setattr(bd_dolt_check, "get_git_remote_url",
                        lambda p: "git@github.com:owner/repo.git")
    assert run_main(monkeypatch, project) == 1
    out = capsys.readouterr().out
    assert "bd dolt remote add origin git+ssh://git@github.com/owner/repo.git" in out


def test_main_reports_unverifiable_without_the_dolt_cli(dolt_project, monkeypatch,
                                                        tmp_path, capsys):
    """Degrade to "not verifiable" and exit 0 -- never fail CI for a missing tool."""
    bindir = install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    monkeypatch.setenv("PATH", str(bindir))  # git only; no dolt
    assert run_main(monkeypatch, dolt_project) == 0
    out = capsys.readouterr().out
    assert "Status:  remote has Dolt data — sync delta not verifiable" in out
    assert "Working set:  not verifiable" in out


def test_main_reports_in_sync_when_the_heads_match(dolt_project, monkeypatch,
                                                   tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt)
    fake_dolt.default(stdout="samehash a commit\n")
    assert run_main(monkeypatch, dolt_project) == 0
    out = capsys.readouterr().out
    assert "IN SYNC" in out
    assert "Working set:  clean" in out
    # Pipeline order: working set -> local commits -> remote.
    assert out.index("Working set:") < out.index("Remote:  refs/dolt/data =")


def test_main_exits_one_with_unpushed_commits(dolt_project, monkeypatch,
                                              tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt)
    # Range rules first: rules match on substring, so a bare "remotes/origin/main"
    # rule would otherwise also swallow the "remotes/origin/main..main" query.
    fake_dolt.rule("remotes/origin/main..main", stdout="c1 one\nc2 two\n")
    fake_dolt.rule("main..remotes/origin/main", stdout="")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    out = capsys.readouterr().out
    assert "OUT OF SYNC" in out
    assert "2 local commit(s) not pushed" in out


def test_main_reports_behind_without_failing(dolt_project, monkeypatch,
                                             tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt)
    fake_dolt.rule("remotes/origin/main..main", stdout="")
    fake_dolt.rule("main..remotes/origin/main", stdout="c1 one\n")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    assert "BEHIND" in capsys.readouterr().out


def test_main_reports_divergence(dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt)
    fake_dolt.rule("remotes/origin/main..main", stdout="c1 one\n")
    fake_dolt.rule("main..remotes/origin/main", stdout="c2 two\n")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    assert "DIVERGED" in capsys.readouterr().out


# --- main(): the Dolt working set -----------------------------------------
#
# "Pushed" is not the same as "committed and pushed". A table sitting in the
# working set is in no commit, so no push can carry it -- and the commit
# comparison above is blind to it. These are the states that distinguishes.


def test_main_exits_one_when_a_table_is_uncommitted_but_commits_are_in_sync(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """The bead's case: IN SYNC by the old check, yet data lives only here."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt, modified("config"))
    fake_dolt.default(stdout="samehash a commit\n")
    assert run_main(monkeypatch, dolt_project) == 1
    out = capsys.readouterr().out
    assert "Status:  UNCOMMITTED — commits in sync, 1 table not committed" in out
    assert "modified  config" in out
    assert "IN SYNC" not in out


def test_main_names_uncommitted_tables_alongside_unpushed_commits(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """Two independent failures: the commit verdict keeps its own wording."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt, modified("config"), modified("issues"))
    fake_dolt.rule("remotes/origin/main..main", stdout="c1 one\n")
    fake_dolt.rule("main..remotes/origin/main", stdout="")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    out = capsys.readouterr().out
    assert ("Status:  OUT OF SYNC — 1 local commit(s) not pushed; "
            "2 tables uncommitted") in out
    # The action line has to be reachable too: a push alone cannot sync while
    # tables sit in no commit, so promising it would send the reader in a loop.
    assert "Commit the working set first (above), then run 'bd dolt push'" in out


def test_main_reports_the_working_set_without_a_dolt_remote(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """The working set is local truth, so it is reported before the remote is
    consulted -- a repo that has never pushed still needs to hear it."""
    install_fake_git(tmp_path, monkeypatch, "")
    working_set(fake_dolt, modified("config"))
    assert run_main(monkeypatch, dolt_project) == 1
    assert "1 table with uncommitted changes" in capsys.readouterr().out


def test_main_exits_one_when_the_delta_is_unverifiable_and_the_working_set_is_dirty(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """Not knowing the commit delta says nothing about data in no commit."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt, modified("config"))
    fake_dolt.rule("main", exit_code=1)  # local HEAD unreadable
    assert run_main(monkeypatch, dolt_project) == 1
    out = capsys.readouterr().out
    assert "Status:  UNCOMMITTED — 1 table uncommitted; sync delta not verifiable" in out


def test_main_stays_at_zero_when_the_delta_is_unverifiable_and_nothing_is_dirty(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt)
    fake_dolt.rule("main", exit_code=1)
    assert run_main(monkeypatch, dolt_project) == 0
    assert "remote has Dolt data — sync delta not verifiable" in capsys.readouterr().out


def test_main_says_so_when_the_working_set_cannot_be_read(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """"Could not look" is stated, not skipped -- silence reading as clean is
    the failure this check exists to end."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    fake_dolt.rule("dolt_status", exit_code=1)
    fake_dolt.default(stdout="samehash a commit\n")
    assert run_main(monkeypatch, dolt_project) == 0
    assert "Working set:  not verifiable" in capsys.readouterr().out


def behind_and_dirty(fake_dolt, tmp_path, monkeypatch):
    """Rules for "one unpulled commit, and the working set is dirty"."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt, modified("config"))
    fake_dolt.rule("remotes/origin/main..main", stdout="")
    fake_dolt.rule("main..remotes/origin/main", stdout="c1 one\n")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")


def test_main_says_to_commit_before_pulling_onto_a_dirty_working_set(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """The one remedy pairing that can conflict rather than merely be
    incomplete -- and the action line is the last thing on screen."""
    behind_and_dirty(fake_dolt, tmp_path, monkeypatch)
    assert run_main(monkeypatch, dolt_project) == 1
    out = capsys.readouterr().out
    assert "BEHIND — 1 remote commit(s) not pulled; 1 table uncommitted" in out
    assert "Commit the working set first (above), then run 'bd dolt pull'" in out


def test_main_does_not_name_bd_dolt_commit_in_server_mode(
        server_dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """The closing action line must not contradict the remedy above it.

    In server mode the working-set section says `bd dolt commit` reports
    success and commits nothing -- so the last line on screen naming that same
    command would send the user round the loop this whole check exists to
    break. It did, until the action line stopped naming a command at all.
    """
    behind_and_dirty(fake_dolt, tmp_path, monkeypatch)
    assert run_main(monkeypatch, server_dolt_project) == 1
    out = capsys.readouterr().out
    assert "Run 'bd dolt stop'" in out            # the remedy that works there
    action = out.rsplit("\n\n", 1)[-1]
    assert "bd dolt commit" not in action
    assert "Commit the working set first (above), then run 'bd dolt pull'" in action


def test_main_carries_the_clause_when_the_delta_is_not_countable(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """Heads differ but neither range counts -- the fallback status line, which
    is the one branch a dirty working set could have slipped past untested."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt, modified("config"))
    fake_dolt.rule("remotes/origin/main..main", stdout="")
    fake_dolt.rule("main..remotes/origin/main", stdout="")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    assert "delta not countable); 1 table uncommitted" in capsys.readouterr().out


# --- print_working_set ----------------------------------------------------


def test_print_working_set_reports_dolt_status_words_verbatim(capsys):
    """Dolt owns this vocabulary; nothing is matched against a list that rots."""
    bd_dolt_check.print_working_set([
        {"table_name": "wisps", "staged": 1, "status": "new table"},
        {"table_name": "issues", "staged": "0", "status": "conflict"},
    ], None, "", "embedded")
    out = capsys.readouterr().out
    assert "new table  wisps" in out
    assert "conflict   issues" in out


def test_print_working_set_pluralizes(capsys):
    bd_dolt_check.print_working_set([modified("a")], None, "", "embedded")
    assert "1 table with uncommitted changes" in capsys.readouterr().out
    bd_dolt_check.print_working_set([modified("a"), modified("b")], None, "", "embedded")
    assert "2 tables with uncommitted changes" in capsys.readouterr().out


def test_main_reports_divergence_with_a_dirty_working_set(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """The third commit_first() call site; the other two are covered above."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    working_set(fake_dolt, modified("config"))
    fake_dolt.rule("remotes/origin/main..main", stdout="c1 one\n")
    fake_dolt.rule("main..remotes/origin/main", stdout="c2 two\n")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    out = capsys.readouterr().out
    assert "DIVERGED — 1 local commit(s) unpushed, 1 remote commit(s) unpulled; 1 table uncommitted" in out
    assert "Commit the working set first (above), then run 'bd dolt pull'" in out


def never_pushed(fake_dolt, tmp_path, monkeypatch):
    """Rules for "the remote has data but we have no tracking ref for it".

    Registration order matters: 'remotes/origin/main' has to shadow the bare
    'main' rule, which would otherwise match it as a substring.
    """
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    fake_dolt.rule("remotes/origin/main", exit_code=1)   # no tracking ref
    fake_dolt.rule("main", stdout="localhash new\n")


def test_main_stays_at_zero_without_a_tracking_ref_when_clean(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """The "never pushed once" case the CHANGELOG advertises, and the branch
    the other unverifiable tests miss -- their rule fails the *local* HEAD
    query first, so they return one branch earlier."""
    working_set(fake_dolt)
    never_pushed(fake_dolt, tmp_path, monkeypatch)
    assert run_main(monkeypatch, dolt_project) == 0
    assert "no local remote-tracking ref 'remotes/origin/main'" in capsys.readouterr().out


def test_main_exits_one_without_a_tracking_ref_when_dirty(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """Same branch, the exit state that matters: never having pushed says
    nothing about data that is in no commit to begin with."""
    working_set(fake_dolt, modified("config"))
    never_pushed(fake_dolt, tmp_path, monkeypatch)
    assert run_main(monkeypatch, dolt_project) == 1
    assert "UNCOMMITTED — 1 table uncommitted; sync delta not verifiable" in capsys.readouterr().out


def test_main_qualifies_in_sync_when_the_working_set_was_not_read(
        dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    """Commits check out, the working set could not be read -- so the verdict
    must not read as a flat all-clear. Exit 0 is still right (nothing is known
    to be wrong), but claiming IN SYNC on an unchecked axis is the same
    silence-reads-as-fine failure this check exists to end."""
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    fake_dolt.rule("dolt_status", exit_code=1)
    fake_dolt.default(stdout="samehash a commit\n")
    assert run_main(monkeypatch, dolt_project) == 0
    out = capsys.readouterr().out
    assert "Status:  IN SYNC (commits) — working set not verifiable" in out


# --- the dolt fallback ----------------------------------------------------
#
# `bd dolt commit` can report success having committed nothing (watched on bd
# 1.1.0 in server mode: "Committed." with no new commit, and `bd vc commit`
# answering with the existing HEAD's hash). Without a way out, the check would
# name a remedy that leaves its own warning standing.


def test_dolt_commit_command_names_every_dirty_table(tmp_path):
    cmd = bd_dolt_check.dolt_commit_command(
        tmp_path / "dolt" / "mydb", "mydb", [modified("config"), modified("issues")])
    assert "call dolt_add('config', 'issues')" in cmd
    assert "use `mydb`;" in cmd   # backticked: the name comes from metadata.json


def test_dolt_commit_command_runs_from_the_database_dir_parent(tmp_path):
    """In server mode that is the data dir holding .dolt/sql-server.info, where
    the CLI proxies to the running server instead of writing under it."""
    cmd = bd_dolt_check.dolt_commit_command(
        tmp_path / "dolt" / "mydb", "mydb", [modified("config")])
    assert cmd.startswith(f"cd {tmp_path / 'dolt'} && dolt sql")


def test_dolt_commit_command_quotes_a_path_with_spaces(tmp_path):
    """The line is printed to be pasted verbatim, so an unquoted directory
    with a space in it would cd somewhere else and silently do nothing."""
    spaced = tmp_path / "My Project" / "dolt" / "mydb"
    cmd = bd_dolt_check.dolt_commit_command(spaced, "mydb", [modified("config")])
    assert f"cd '{tmp_path}/My Project/dolt'" in cmd


def test_print_working_set_offers_the_fallback_in_server_mode(tmp_path, capsys):
    bd_dolt_check.print_working_set(
        [modified("config")], tmp_path / "dolt" / "mydb", "mydb", "server")
    out = capsys.readouterr().out
    assert "Run 'bd dolt stop'" in out
    assert "does NOT clear this in server mode" in out
    assert "call dolt_add('config')" in out


def test_print_working_set_names_bd_dolt_commit_in_embedded_mode(tmp_path, capsys):
    """It works there, verified at bd 1.1.0 with auto-commit off -- so the
    server-mode caveat would only be noise."""
    bd_dolt_check.print_working_set(
        [modified("config")], tmp_path / "embeddeddolt" / "mydb", "mydb", "embedded")
    out = capsys.readouterr().out
    assert "Run 'bd dolt commit', then 'bd dolt push'." in out
    assert "bd dolt stop" not in out
    assert "dolt_add" not in out


def test_main_rejects_a_directory_that_is_not_a_beads_project(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as excinfo:
        run_main(monkeypatch, tmp_path)
    assert "no .beads/ directory" in str(excinfo.value.code)
