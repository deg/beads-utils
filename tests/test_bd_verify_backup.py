"""Tests for bd-verify-backup.

The git legs run against real throwaway repositories with a local bare
"remote", so the porcelain and for-each-ref parsing is checked against what
git actually prints. The beads leg is bd-dolt-check's dolt_sync_state(),
covered in its own tests; here it is replaced by a stub DoltSyncState.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import bdutils
from conftest import load_script

bvb = load_script("bd-verify-backup")


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    """Commit as a fixed identity, and read none of the user's git config: a
    global commit.gpgsign or hook would otherwise decide whether tests pass."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "Test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "test@example.com")


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A beads project whose one branch, main, is pushed to a bare remote."""
    remote = tmp_path / "remote.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work"
    (work / ".beads").mkdir(parents=True)
    (work / ".beads" / "metadata.json").write_text(json.dumps({"dolt_database": "db"}))
    sh(work, "init", "-q", "-b", "main")
    sh(work, "add", ".")
    sh(work, "commit", "-q", "-m", "init")
    sh(work, "remote", "add", "origin", str(remote))
    sh(work, "push", "-q", "-u", "origin", "main")
    return work


@pytest.fixture
def beads_ok(monkeypatch):
    """The beads leg answers IN SYNC, so a test sees only the git legs."""
    monkeypatch.setattr(bvb, "beads_verdict", lambda path, fetch: ("IN SYNC", True, []))


def state(status="IN SYNC", dirty=(), db=Path("/db"), **kw):
    return bdutils.DoltSyncState(
        db_name="db", dolt_mode="embedded", dolt_db_dir=db, dolt_remotes={},
        beads_remote=None, dirty=None if dirty is None else list(dirty),
        status=status, **kw)


# --- check_repo: the git legs ----------------------------------------------


def test_a_clean_pushed_repo_is_backed_up(repo, beads_ok):
    rep = bvb.check_repo(repo, fetch=True)
    assert rep.ok
    assert (rep.dirty, rep.branches, rep.stashes, rep.n_branches) == ([], [], 0, 1)


def test_an_untracked_file_counts_as_uncommitted(repo, beads_ok):
    (repo / "new.txt").write_text("x")
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.dirty == ["?? new.txt"]
    assert not rep.ok


def test_a_stash_is_not_backed_up(repo, beads_ok):
    (repo / ".beads" / "metadata.json").write_text("{}")
    sh(repo, "stash", "-q")
    rep = bvb.check_repo(repo, fetch=False)
    assert (rep.dirty, rep.stashes) == ([], 1)
    assert not rep.ok


def test_every_local_branch_is_checked_not_only_the_current_one(repo, beads_ok):
    sh(repo, "branch", "never-pushed")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "one")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "two")
    sh(repo, "checkout", "-q", "never-pushed")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "only here")
    rep = bvb.check_repo(repo, fetch=False)
    assert sorted(rep.branches) == [("main", "2 commits not pushed"),
                                    ("never-pushed", "no upstream")]
    assert rep.n_branches == 2


def test_a_pushed_branch_with_no_upstream_still_fails_but_says_so(repo, beads_ok):
    """`git push origin gh-pages` with no -u: every commit is on origin, only
    the tracking config is missing. Still a failure, but the reader is told
    which case this is and given the fix."""
    sh(repo, "checkout", "-q", "-b", "gh-pages")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "deploy")
    sh(repo, "push", "-q", "origin", "gh-pages")
    # A remote branch merely ending in the name is not offered as upstream.
    sh(repo, "push", "-q", "origin", "gh-pages:site/gh-pages")
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.branches == [("gh-pages", "no upstream (every commit is on a remote; "
                                         "fix: git branch -u origin/gh-pages gh-pages)")]
    assert bvb.branches_cell(rep) == "1 no upstream"
    assert not rep.ok


def test_a_branch_with_no_upstream_or_namesake_whose_commits_are_on_a_remote(repo, beads_ok):
    sh(repo, "branch", "copy-of-main")
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.branches == [("copy-of-main", "no upstream (every commit is on a remote)")]
    assert not rep.ok


def test_a_branch_tracking_a_local_branch_has_no_upstream(repo, beads_ok):
    """`git branch -u main feature` gives feature an upstream, so it read as
    pushed -- yet its commits are on no remote, even with main pushed."""
    sh(repo, "branch", "feature")
    sh(repo, "branch", "-q", "-u", "main", "feature")
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.branches == [("feature", "no upstream (tracks local main)")]
    assert bvb.branches_cell(rep) == "1 no upstream"


def test_a_branch_whose_upstream_was_deleted_is_gone(repo, beads_ok):
    sh(repo, "checkout", "-q", "-b", "topic")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "only on topic")
    sh(repo, "push", "-q", "-u", "origin", "topic")
    # Deleted on the remote directly, as a merged PR's branch is; a local
    # `push --delete` would drop the remote-tracking ref itself.
    sh(repo.parent / "remote.git", "branch", "-q", "-D", "topic")
    # The fetch is what notices: --prune drops the stale remote-tracking ref.
    assert bvb.check_repo(repo, fetch=False).branches == []
    assert bvb.check_repo(repo, fetch=True).branches == [
        ("topic", "upstream origin/topic is gone, 1 commit on no remote")]


def test_a_gone_branch_whose_commits_are_all_on_a_remote_is_only_cleanup(
        repo, beads_ok, monkeypatch, capsys):
    """A merged PR's leftover: its upstream was deleted, but every commit is
    on origin/main, so nothing would be lost. It must not fail the repo --
    temperature-bot had 12 of these -- yet the detailed view still lists it,
    so the clutter is not forgotten."""
    sh(repo, "checkout", "-q", "-b", "topic")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "merged work")
    sh(repo, "push", "-q", "-u", "origin", "topic")
    sh(repo, "push", "-q", "origin", "topic:main")      # the merge
    sh(repo.parent / "remote.git", "branch", "-q", "-D", "topic")
    rep = bvb.check_repo(repo, fetch=True)
    assert rep.branches == []
    assert rep.cleanup == [("topic", "upstream origin/topic is gone, every commit is on a remote")]
    assert rep.ok
    bvb.print_detail(rep, color=False)
    out = capsys.readouterr().out
    assert "Cleanup:     1 merged branch to delete" in out
    assert "Status:      BACKED UP" in out


def test_a_branch_behind_its_upstream_is_backed_up(repo, beads_ok, tmp_path):
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    sh(other, "commit", "-q", "--allow-empty", "-m", "from elsewhere")
    sh(other, "push", "-q")
    rep = bvb.check_repo(repo, fetch=True)
    assert rep.branches == []
    assert rep.ok


def test_a_failed_fetch_is_a_note_not_a_failure(repo, beads_ok):
    sh(repo, "remote", "set-url", "origin", str(repo.parent / "missing.git"))
    rep = bvb.check_repo(repo, fetch=True)
    assert rep.ok
    assert len(rep.notes) == 1 and rep.notes[0].startswith("git fetch failed")


def test_a_directory_that_is_not_a_git_repo_is_not_backed_up(tmp_path, beads_ok):
    (tmp_path / ".beads").mkdir()
    rep = bvb.check_repo(tmp_path, fetch=False)
    assert rep.fatal == "not a git repository: nothing here is backed up"
    assert not rep.ok


def test_a_repo_with_no_remote_is_not_backed_up(repo, beads_ok):
    sh(repo, "remote", "remove", "origin")
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.fatal == "no git remote: nothing here is backed up"


def test_an_error_inside_one_repo_is_reported_not_raised(repo, monkeypatch):
    """bdutils.error() exits; under --global that would end the whole run."""
    def boom(path, fetch):
        bdutils.error("could not read metadata.json")
    monkeypatch.setattr(bvb, "beads_verdict", boom)
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.fatal == "error: could not read metadata.json"


def test_any_exception_inside_one_repo_is_its_failure_line(repo, monkeypatch):
    """A non-UTF-8 config.yaml raises UnicodeDecodeError, which no helper
    catches; under --global it would surface from pool.map as a traceback and
    no table would print."""
    def boom(path, fetch):
        b"\xff".decode()
    monkeypatch.setattr(bvb, "beads_verdict", boom)
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.fatal.startswith("error: UnicodeDecodeError: ")
    assert not rep.ok


def test_commits_on_a_detached_head_are_not_backed_up(repo, beads_ok):
    """No branch holds them, so the per-branch check alone would pass."""
    sh(repo, "checkout", "-q", "--detach")
    assert bvb.check_repo(repo, fetch=False).branches == []
    sh(repo, "commit", "-q", "--allow-empty", "-m", "orphaned")
    rep = bvb.check_repo(repo, fetch=False)
    assert rep.branches == [("detached HEAD", "1 commit not pushed")]
    assert not rep.ok


# --- beads_verdict ----------------------------------------------------------


@pytest.mark.parametrize("st,cell,ok", [
    (state(), "IN SYNC", True),
    # The remote has more than we do; nothing local is unpushed.
    (state("BEHIND"), "BEHIND", True),
    (state(dirty=[{"table_name": "config"}]), "IN SYNC, 1 table uncommitted", False),
    # Could not look is not clean: a backup check cannot pass on it.
    (state(dirty=None), "IN SYNC, working set not verifiable", False),
    (state("OUT OF SYNC", ahead=15), "OUT OF SYNC +15", False),
    (state("DIVERGED", ahead=2, behind=3), "DIVERGED +2/-3", False),
    (state("UNREACHABLE", ls_error="timed out"), "UNREACHABLE (timed out)", False),
    (state("NOT FOUND"), "NOT FOUND", False),
    (state("UNVERIFIABLE"), "UNVERIFIABLE", False),
    (state(db=None, dirty=None), "no Dolt database", False),
])
def test_beads_verdict(monkeypatch, st, cell, ok):
    monkeypatch.setattr(bvb, "dolt_sync_state", lambda path, fetch: st)
    assert bvb.beads_verdict(Path("/x"), fetch=False) == (cell, ok, [])


def test_a_failed_dolt_fetch_is_a_note_not_a_failure(monkeypatch):
    """IN SYNC against a stale tracking ref is still green, but the reader
    has to know the comparison is dated -- bd-dolt-check says so too."""
    monkeypatch.setattr(bvb, "dolt_sync_state",
                        lambda path, fetch: state(fetch_failed=True, remote_name="origin"))
    cell, ok, notes = bvb.beads_verdict(Path("/x"), fetch=True)
    assert (cell, ok) == ("IN SYNC", True)
    assert notes == ["dolt fetch origin failed; compared against the last-fetched Dolt refs"]


def test_check_repo_carries_the_beads_notes(repo, monkeypatch):
    monkeypatch.setattr(bvb, "beads_verdict", lambda path, fetch: ("IN SYNC", True, ["n"]))
    assert bvb.check_repo(repo, fetch=False).notes == ["n"]


# --- find_beads_repos -------------------------------------------------------


def make_beads(path: Path) -> Path:
    (path / ".beads").mkdir(parents=True)
    (path / ".beads" / "metadata.json").write_text("{}")
    return path


def test_find_beads_repos_unions_and_dedupes_the_three_sources(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    in_claude = make_beads(docs / "a" / "known")
    scanned_only = make_beads(docs / "b" / "unrecorded")
    extra = make_beads(tmp_path / "bin")
    (docs / "c" / "no-beads").mkdir(parents=True)
    # A .beads without metadata.json is not a beads repo (mirror/beads).
    (docs / "c" / "mirror" / ".beads").mkdir(parents=True)
    monkeypatch.setattr(bvb, "claude_project_paths",
                        lambda: [in_claude, tmp_path / "gone", tmp_path])
    monkeypatch.setattr(bvb, "SCAN_GLOBS", ((str(docs), "*/*"),))
    # The same repo spelled another way (as ~/.claude.json and a glob can).
    monkeypatch.setattr(bvb, "EXTRA_REPOS", (str(extra), f"{docs}/a/../a/known"))
    assert bvb.find_beads_repos() == sorted(
        p.resolve() for p in (in_claude, scanned_only, extra))


# --- main --------------------------------------------------------------------


def run_main(monkeypatch, *argv):
    monkeypatch.setattr(bvb.sys, "argv", ["bd-verify-backup", *argv])
    return bvb.main()


def test_main_exits_zero_only_when_the_repo_is_backed_up(repo, beads_ok, monkeypatch, capsys):
    assert run_main(monkeypatch, str(repo), "--no-fetch") == 0
    assert "Status:      BACKED UP" in capsys.readouterr().out
    (repo / "new.txt").write_text("x")
    assert run_main(monkeypatch, str(repo), "--no-fetch") == 1
    out = capsys.readouterr().out
    assert "?? new.txt" in out
    assert "Status:      NOT BACKED UP" in out


def test_global_lists_failures_first_and_counts(monkeypatch, capsys, tmp_path):
    good, bad, worse = (tmp_path / n for n in ("a-good", "b-bad", "c-worse"))
    reports = {
        good: bvb.Report(good, beads="IN SYNC", beads_ok=True, n_branches=1),
        bad: bvb.Report(bad, dirty=["?? x"], branches=[("main", "3 commits not pushed")],
                        beads="OUT OF SYNC +4"),
        worse: bvb.Report(worse, fatal="no git remote: nothing here is backed up"),
    }
    monkeypatch.setattr(bvb, "find_beads_repos", lambda: sorted(reports))
    monkeypatch.setattr(bvb, "check_repo", lambda p, fetch: reports[p])
    assert run_main(monkeypatch, "-g") == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["REPO", "TREE", "BRANCHES", "BEADS"]
    assert [ln.split()[0] for ln in lines[1:4]] == [str(bad), str(worse), str(good)]
    assert lines[1].split()[1:] == ["1", "uncommitted", "main", "+3", "OUT", "OF", "SYNC", "+4"]
    assert "no git remote" in lines[2]
    assert lines[-1] == "1 of 3 repos fully backed up"


def test_global_exits_zero_when_everything_is_backed_up(monkeypatch, capsys, tmp_path):
    rep = bvb.Report(tmp_path, beads="IN SYNC", beads_ok=True)
    monkeypatch.setattr(bvb, "find_beads_repos", lambda: [tmp_path])
    monkeypatch.setattr(bvb, "check_repo", lambda p, fetch: rep)
    assert run_main(monkeypatch, "--global") == 0
    assert capsys.readouterr().out.splitlines()[-1] == "1 of 1 repos fully backed up"


def test_global_refuses_a_project_path(monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, "-g", str(tmp_path))
    assert exc.value.code == 2


def test_branches_cell_summarizes_long_lists():
    rep = bvb.Report(Path("/x"), branches=[
        ("a", "1 commit not pushed"), ("b", "2 commits not pushed"),
        ("c", "5 commits not pushed"), ("d", "no upstream"), ("e", "no upstream"),
        ("f", "upstream origin/f is gone, 2 commits on no remote")])
    assert bvb.branches_cell(rep) == "a +1, b +2, 1 more ahead, 2 no upstream, 1 gone"
