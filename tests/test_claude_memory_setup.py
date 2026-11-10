"""Tests for claude-memory-setup, which gives Claude Code memories a git repo.

Real git, always under tmp_path and with the global config masked, as the
bd-verify-backup tests do. The properties that matter: the work tree is the
projects directory and gains nothing but one .gitignore; that file is an
allowlist that hides transcripts; a clone writes out only files that are
missing, and does so even when an earlier run died after the clone; an empty
remote ends up holding the first commit; and every run after the first is a
no-op repair.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from conftest import BIN

SETUP = BIN / "claude-memory-setup"


@pytest.fixture
def env(tmp_path):
    e = dict(os.environ)
    e.update({
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "HOME": str(tmp_path / "home"),
    })
    e.pop("CLAUDE_MEMORIES_GIT", None)
    e.pop("PYTHONPATH", None)
    return e


def setup(env, *args, expect_ok=True):
    # sys.executable rather than the shebang, as conftest's run_script does,
    # so the interpreter under test is the suite's own.
    done = subprocess.run(
        [sys.executable, str(SETUP), *args], capture_output=True, text=True, env=env,
    )
    if expect_ok:
        assert done.returncode == 0, done.stdout + done.stderr
    return done


def git(git_dir, *args, cwd=None, env=None):
    return subprocess.check_output(
        ["git", f"--git-dir={git_dir}", *args], text=True, cwd=cwd, env=env,
    ).strip()


def memory(projects, slug, name, body="x"):
    d = projects / slug / "memory"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(f"---\nname: {name}\n---\n{body}\n")


# --- a fresh repo ----------------------------------------------------------


def test_fresh_setup_commits_the_allowlist_and_existing_memories(tmp_path, env):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    memory(projects, "p1", "a")
    (projects / "p1" / "s.jsonl").write_text("secret transcript\n")

    setup(env, "--git-dir", str(git_dir), "--projects", str(projects))

    tracked = git(git_dir, "ls-files", cwd=projects, env=env).splitlines()
    assert tracked == [".gitignore", "p1/memory/a.md"]
    assert git(git_dir, "config", "core.worktree", cwd=projects, env=env) == str(projects.resolve())
    assert git(git_dir, "config", "core.bare", cwd=projects, env=env) == "false"


def test_the_allowlist_hides_everything_but_memory_markdown(tmp_path, env):
    """The one property the whole design rests on."""
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    memory(projects, "p1", "a")
    (projects / "p1" / "memory" / "MEMORY.md~").write_text("backup\n")
    (projects / "p1" / "memory" / ".DS_Store").write_bytes(b"\0")
    (projects / "p1" / "memory" / "a.md").write_text("changed\n")
    (projects / "p1" / "t.jsonl").write_text("transcript\n")
    (projects / "tool-results").mkdir()
    (projects / "tool-results" / "out.txt").write_text("pasted\n")

    status = git(git_dir, "status", "--porcelain", "-uall", cwd=projects, env=env)
    assert status.splitlines() == ["?? p1/memory/a.md"]


def test_a_fresh_setup_without_memories_still_makes_a_commit(tmp_path, env):
    """The allowlist alone is worth committing: HEAD must exist for the hooks."""
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    assert git(git_dir, "ls-files", cwd=projects, env=env) == ".gitignore"
    assert git(git_dir, "rev-parse", "--abbrev-ref", "HEAD", cwd=projects, env=env) == "main"


def test_rerun_is_a_repair_not_a_second_commit(tmp_path, env):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    git(git_dir, "config", "--unset", "core.worktree", cwd=projects, env=env)

    setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    assert git(git_dir, "config", "core.worktree", cwd=projects, env=env) == str(projects.resolve())
    assert git(git_dir, "rev-list", "--count", "HEAD", cwd=projects, env=env) == "1"


def test_an_existing_gitignore_is_not_overwritten(tmp_path, env):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    projects.mkdir()
    (projects / ".gitignore").write_text("*\n!*/\n!/*/memory/*.md\n!/.gitignore\n!/notes.md\n")
    done = setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    assert (projects / ".gitignore").read_text().endswith("!/notes.md\n")
    assert "differs from the allowlist" in done.stderr


def test_a_gitignore_differing_only_in_comments_is_not_reported(tmp_path, env):
    """A clone of an older allowlist has other comments; warning every run is noise."""
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    projects.mkdir()
    (projects / ".gitignore").write_text("# older wording\n*\n!*/\n\n!/*/memory/*.md\n!/.gitignore\n")
    done = setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    assert done.stderr == ""
    assert (projects / ".gitignore").read_text().startswith("# older wording")


def test_without_an_upstream_the_summary_says_nothing_will_push(tmp_path, env):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    done = setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    assert "No upstream" in done.stdout


def test_defaults_come_from_home(tmp_path, env):
    """No flags: ~/claude-memories.git over ~/.claude/projects, both under HOME."""
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    setup(env)
    assert (home / "claude-memories.git" / "HEAD").exists()
    assert (home / ".claude" / "projects" / ".gitignore").exists()


def test_the_env_var_moves_the_git_dir(tmp_path, env):
    env["CLAUDE_MEMORIES_GIT"] = str(tmp_path / "elsewhere.git")
    setup(env, "--projects", str(tmp_path / "projects"))
    assert (tmp_path / "elsewhere.git" / "HEAD").exists()


def test_without_jq_it_refuses_to_set_anything_up(tmp_path, env):
    """The hooks need jq; a repo they cannot serve is worse than no repo."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(subprocess.check_output(["which", "git"], text=True).strip())
    env["PATH"] = str(bin_dir)
    done = setup(env, "--git-dir", str(tmp_path / "mem.git"), "--projects", str(tmp_path / "projects"),
                 expect_ok=False)
    assert done.returncode != 0
    assert "jq is required" in done.stderr
    assert not (tmp_path / "mem.git").exists()


# --- cloning onto a new machine --------------------------------------------


@pytest.fixture
def remote(tmp_path, env):
    """A bare remote holding three memories, as the old machine would have pushed.

    Made with plain `git init --bare`, whose HEAD names master while the
    memories are on main: the shape that once left a clone's HEAD unborn.
    """
    old_projects, old_git = tmp_path / "old-projects", tmp_path / "old.git"
    memory(old_projects, "p1", "a", "from the old machine")
    memory(old_projects, "p2", "b")
    memory(old_projects, "p2", "[ab]", "a name that is also a glob matching a.md and b.md")
    setup(env, "--git-dir", str(old_git), "--projects", str(old_projects))
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "-q", "--bare", str(bare)], env=env)
    git(old_git, "push", "-q", str(bare), "main", cwd=old_projects, env=env)
    return bare


def test_clone_checks_out_the_memories_and_tracks_origin(tmp_path, env, remote):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    done = setup(env, "--remote", str(remote), "--git-dir", str(git_dir), "--projects", str(projects))
    assert (projects / "p1" / "memory" / "a.md").read_text().endswith("from the old machine\n")
    assert (projects / "p2" / "memory" / "[ab].md").exists()
    assert (projects / ".gitignore").exists()
    assert git(git_dir, "rev-parse", "--abbrev-ref", "@{upstream}", cwd=projects, env=env) == "origin/main"
    assert git(git_dir, "config", "remote.origin.fetch", cwd=projects, env=env) == "+refs/heads/*:refs/remotes/origin/*"
    assert "Checked out 4 file(s)" in done.stdout  # three memories and the allowlist
    assert git(git_dir, "status", "--porcelain", cwd=projects, env=env) == ""


def test_clone_leaves_a_memory_already_written_here_alone(tmp_path, env, remote):
    """Claude Code may have run before the clone; its newer file must win.

    p2/b.md is the sharper half: the missing `[ab].md` is checked out by
    name, and as a glob that name also matches b.md. Without literal
    pathspecs the checkout would overwrite the local b.md with the remote's.
    """
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    memory(projects, "p1", "a", "written on the new machine first")
    memory(projects, "p2", "b", "also written here first")
    done = setup(env, "--remote", str(remote), "--git-dir", str(git_dir), "--projects", str(projects))
    assert (projects / "p1" / "memory" / "a.md").read_text().endswith("new machine first\n")
    assert (projects / "p2" / "memory" / "b.md").read_text().endswith("also written here first\n")
    assert (projects / "p2" / "memory" / "[ab].md").exists()
    assert "differs from the repo" in done.stderr


def test_clone_rerun_does_not_resurrect_a_deleted_memory(tmp_path, env, remote):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    setup(env, "--remote", str(remote), "--git-dir", str(git_dir), "--projects", str(projects))
    (projects / "p2" / "memory" / "b.md").unlink()
    setup(env, "--remote", str(remote), "--git-dir", str(git_dir), "--projects", str(projects))
    assert not (projects / "p2" / "memory" / "b.md").exists()


def test_a_run_that_died_after_the_clone_is_finished_by_the_rerun(tmp_path, env, remote):
    """The git dir exists but nothing was ever checked out.

    Keyed on the git dir's existence, the rerun would skip the checkout and
    leave a repo that tracks every memory while the work tree holds none: to
    the SessionEnd hook, every memory deleted. The index is the right signal.
    """
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    subprocess.check_call(["git", "clone", "-q", "--bare", str(remote), str(git_dir)], env=env)
    assert not (git_dir / "index").exists()
    setup(env, "--remote", str(remote), "--git-dir", str(git_dir), "--projects", str(projects))
    assert (projects / "p1" / "memory" / "a.md").exists()
    assert git(git_dir, "status", "--porcelain", cwd=projects, env=env) == ""


def test_an_empty_remote_receives_the_first_commit(tmp_path, env):
    """A repo just created to hold the memories: it must end up live, not waiting."""
    projects, git_dir, bare = tmp_path / "projects", tmp_path / "mem.git", tmp_path / "empty.git"
    subprocess.check_call(["git", "init", "-q", "--bare", str(bare)], env=env)
    memory(projects, "p1", "a")
    done = setup(env, "--remote", str(bare), "--git-dir", str(git_dir), "--projects", str(projects))
    assert "is empty; making the first commit and pushing it" in done.stdout
    assert git(git_dir, "rev-parse", "--abbrev-ref", "@{upstream}", cwd=projects, env=env) == "origin/main"
    remote_main = subprocess.check_output(["git", f"--git-dir={bare}", "rev-parse", "main"], text=True, env=env).strip()
    assert remote_main == git(git_dir, "rev-parse", "HEAD", cwd=projects, env=env)
    assert git(git_dir, "ls-files", cwd=projects, env=env).splitlines() == [".gitignore", "p1/memory/a.md"]


def test_the_first_commit_refuses_when_the_allowlist_exposes_a_transcript(tmp_path, env):
    """A permissive .gitignore already in place must not put transcripts in the first commit.

    The hook guards every later commit; this is the one commit it never sees,
    and on the empty-remote path it would be pushed at once.
    """
    projects, git_dir, bare = tmp_path / "projects", tmp_path / "mem.git", tmp_path / "empty.git"
    subprocess.check_call(["git", "init", "-q", "--bare", str(bare)], env=env)
    projects.mkdir()
    (projects / ".gitignore").write_text("")  # hides nothing
    memory(projects, "p1", "a")
    # Under a memory directory on purpose: a loose "contains /memory/" rule would pass it.
    (projects / "p1" / "memory" / "sub").mkdir()
    (projects / "p1" / "memory" / "sub" / "t.jsonl").write_text("everything ever pasted\n")
    done = setup(env, "--remote", str(bare), "--git-dir", str(git_dir), "--projects", str(projects),
                 expect_ok=False)
    assert done.returncode != 0
    assert "refusing the first commit" in done.stderr and "p1/memory/sub/t.jsonl" in done.stderr
    assert subprocess.run(["git", f"--git-dir={git_dir}", "rev-parse", "-q", "--verify", "HEAD"],
                          capture_output=True, env=env).returncode != 0  # no commit
    assert subprocess.run(["git", f"--git-dir={bare}", "rev-parse", "-q", "--verify", "main"],
                          capture_output=True, env=env).returncode != 0  # nothing pushed


def test_the_first_commit_accepts_an_allowlist_edit_and_memories_only(tmp_path, env):
    projects, git_dir = tmp_path / "projects", tmp_path / "mem.git"
    projects.mkdir()
    (projects / ".gitignore").write_text("# mine\n*\n!*/\n!/*/memory/*.md\n!/.gitignore\n")
    memory(projects, "p1", "a")
    (projects / "p1" / "t.jsonl").write_text("hidden by the allowlist\n")
    setup(env, "--git-dir", str(git_dir), "--projects", str(projects))
    assert git(git_dir, "ls-files", cwd=projects, env=env).splitlines() == [".gitignore", "p1/memory/a.md"]


def test_an_unreachable_remote_is_an_error_not_a_traceback(tmp_path, env):
    done = setup(
        env, "--remote", str(tmp_path / "nowhere.git"),
        "--git-dir", str(tmp_path / "mem.git"), "--projects", str(tmp_path / "projects"),
        expect_ok=False,
    )
    assert done.returncode != 0
    assert "error: could not clone" in done.stderr
    assert "Traceback" not in done.stderr
