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


def run_main(monkeypatch, path, argv_extra=()):
    monkeypatch.setattr(bd_dolt_check.sys, "argv",
                        ["bd-dolt-check", str(path), *argv_extra])
    return bd_dolt_check.main()


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
    assert "not verifiable" in capsys.readouterr().out


def test_main_reports_in_sync_when_the_heads_match(dolt_project, monkeypatch,
                                                   tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    fake_dolt.default(stdout="samehash a commit\n")
    assert run_main(monkeypatch, dolt_project) == 0
    assert "IN SYNC" in capsys.readouterr().out


def test_main_exits_one_with_unpushed_commits(dolt_project, monkeypatch,
                                              tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
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
    fake_dolt.rule("remotes/origin/main..main", stdout="")
    fake_dolt.rule("main..remotes/origin/main", stdout="c1 one\n")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    assert "BEHIND" in capsys.readouterr().out


def test_main_reports_divergence(dolt_project, monkeypatch, tmp_path, fake_dolt, capsys):
    install_fake_git(tmp_path, monkeypatch, "abc123\trefs/dolt/data\n")
    fake_dolt.rule("remotes/origin/main..main", stdout="c1 one\n")
    fake_dolt.rule("main..remotes/origin/main", stdout="c2 two\n")
    fake_dolt.rule("remotes/origin/main", stdout="remotehash old\n")
    fake_dolt.rule("main", stdout="localhash new\n")
    assert run_main(monkeypatch, dolt_project) == 1
    assert "DIVERGED" in capsys.readouterr().out


def test_main_rejects_a_directory_that_is_not_a_beads_project(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as excinfo:
        run_main(monkeypatch, tmp_path)
    assert "no .beads/ directory" in str(excinfo.value.code)
