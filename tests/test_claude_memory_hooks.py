"""Tests for the two memory hooks: commit-memories.sh and check-memories-pushed.sh.

Each runs as Claude Code runs it, a bash subprocess with the hook JSON on
stdin, against a memories repo that claude-memory-setup built under tmp_path
and a bare local remote. The commit hook's guard is the part that matters:
it must refuse to commit the moment anything but a memory file is visible,
because the hook pushes, and a transcript pushed is a transcript published.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from conftest import ROOT

COMMIT = ROOT / "hooks" / "commit-memories.sh"
CHECK = ROOT / "hooks" / "check-memories-pushed.sh"
SETUP = ROOT / "claude-memory-setup"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="the hooks need jq")


class Store:
    """A memories repo with an upstream, plus the env the hooks run under."""

    def __init__(self, tmp_path):
        self.projects = tmp_path / "projects"
        self.git_dir = tmp_path / "mem.git"
        self.remote = tmp_path / "remote.git"
        self.env = dict(os.environ)
        self.env.update({
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            "HOME": str(tmp_path / "home"),
            "CLAUDE_MEMORIES_GIT": str(self.git_dir),
        })
        self.env.pop("PYTHONPATH", None)
        (tmp_path / "home").mkdir()
        subprocess.check_call(
            [sys.executable, str(SETUP), "--git-dir", str(self.git_dir), "--projects", str(self.projects)],
            env=self.env, stdout=subprocess.DEVNULL,
        )
        subprocess.check_call(["git", "init", "-q", "--bare", str(self.remote)], env=self.env)
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "-u", "origin", "main")

    def git(self, *args):
        return subprocess.check_output(
            ["git", f"--git-dir={self.git_dir}", *args],
            text=True, cwd=self.projects, env=self.env,
        ).strip()

    def memory(self, slug, name, body="x"):
        d = self.projects / slug / "memory"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(f"---\nname: {name}\n---\n{body}\n")

    def hook(self, script, *args, stdin: dict | None = None):
        return subprocess.run(
            ["bash", str(script), *args], input=json.dumps(stdin or {}),
            capture_output=True, text=True, env=self.env, cwd=self.projects,
        )

    def head(self):
        return self.git("rev-parse", "HEAD")

    def remote_head(self):
        return subprocess.check_output(
            ["git", f"--git-dir={self.remote}", "rev-parse", "main"], text=True, env=self.env,
        ).strip()

    def wait_for_push(self, timeout=10.0):
        """The hook pushes detached; poll the remote rather than guess a sleep."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.remote_head() == self.head():
                    return True
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.1)
        return False

    def refusal(self):
        p = self.git_dir / "last-refusal"
        return p.read_text() if p.exists() else None


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def silent_ok(done):
    assert done.returncode == 0 and done.stdout == "" and done.stderr == "", done


# --- commit-memories.sh ------------------------------------------------------


def test_a_new_memory_is_committed_with_the_session_in_the_message(store):
    before = store.head()
    store.memory("p1", "a")
    done = store.hook(COMMIT, stdin={"session_id": "0123456789abcdef", "cwd": store.env["HOME"] + "/Documents/x"})
    silent_ok(done)
    assert store.head() != before
    assert store.git("log", "-1", "--format=%s") == (
        "Snapshot Claude Code memories at session end (~/Documents/x, session 01234567)"
    )
    assert store.git("ls-files") == ".gitignore\np1/memory/a.md"


def test_a_message_argument_replaces_the_generic_one(store):
    """/close-shop passes what the audit did; that is the one commit that can say why."""
    store.memory("p1", "a")
    store.hook(COMMIT, "Audit: retired two stale memories")
    assert store.git("log", "-1", "--format=%s") == "Audit: retired two stale memories"


def test_a_name_with_spaces_and_non_ascii_is_committed(store):
    """Porcelain would quote such a name; -z keeps it raw so the guard still matches."""
    store.memory("my project", "déjà vu — notes")
    store.hook(COMMIT)
    assert store.refusal() is None
    # git quotes non-ASCII names in ls-files output unless told not to.
    assert "my project/memory/déjà vu — notes.md" in store.git("-c", "core.quotePath=false", "ls-files")


def test_nothing_to_do_makes_no_commit(store):
    before = store.head()
    silent_ok(store.hook(COMMIT))
    assert store.head() == before


def test_the_commit_is_pushed_to_the_upstream(store):
    store.memory("p1", "a")
    store.hook(COMMIT)
    assert store.wait_for_push(), (store.git_dir / "last-push.log").read_text()


def test_a_visible_non_memory_path_refuses_the_whole_commit(store):
    """The allowlist mangled so a transcript shows: nothing may be committed."""
    (store.projects / ".gitignore").write_text("!/*/memory/*.md\n")  # no leading `*`
    store.memory("p1", "a")
    (store.projects / "p1" / "t.jsonl").write_text("pasted secrets\n")
    before = store.head()
    silent_ok(store.hook(COMMIT))
    assert store.head() == before
    assert "a non-memory path is visible" in store.refusal()


def test_a_nested_path_under_a_memory_dir_is_not_a_memory(store):
    """`*` in a case pattern matches `/`; the guard must not accept a/b/memory/c.md."""
    (store.projects / ".gitignore").write_text("!/*/memory/*.md\n")
    nested = store.projects / "a" / "b" / "memory"
    nested.mkdir(parents=True)
    (nested / "c.md").write_text("x\n")
    before = store.head()
    store.hook(COMMIT)
    assert store.head() == before
    assert "a non-memory path is visible: a/b/memory/c.md" in store.refusal()


def test_a_deleted_allowlist_refuses_even_with_nothing_else_visible(store):
    (store.projects / ".gitignore").unlink()
    before = store.head()
    store.hook(COMMIT)
    assert store.head() == before
    assert "the allowlist .gitignore is deleted" in store.refusal()


def test_an_edit_to_the_allowlist_itself_may_be_committed(store):
    (store.projects / ".gitignore").write_text(
        (store.projects / ".gitignore").read_text() + "# a note\n"
    )
    before = store.head()
    store.hook(COMMIT)
    assert store.head() != before
    assert store.refusal() is None


def test_a_refusal_still_pushes_what_is_already_committed(store):
    """The guard protects the commit, not the push: committed work still goes out."""
    store.memory("p1", "a")
    store.git("add", "-A")
    store.git("commit", "-q", "-m", "by hand")
    (store.projects / ".gitignore").unlink()
    store.hook(COMMIT)
    assert store.refusal() is not None
    assert store.wait_for_push()


def test_twenty_deletions_are_committed_and_twenty_one_refused(store):
    """The limit is a boundary, not a vague ceiling: 20 passes, 21 does not."""
    for i in range(21):
        store.memory("p1", f"m{i:02d}")
    store.hook(COMMIT)
    assert store.refusal() is None
    for i in range(20):
        (store.projects / "p1" / "memory" / f"m{i:02d}.md").unlink()
    before = store.head()
    store.hook(COMMIT)
    assert store.head() != before and store.refusal() is None
    store.memory("p1", "m99")
    for i in range(20):
        store.memory("p1", f"n{i:02d}")
    store.hook(COMMIT)
    for i in range(20):
        (store.projects / "p1" / "memory" / f"n{i:02d}.md").unlink()
    (store.projects / "p1" / "memory" / "m99.md").unlink()
    before = store.head()
    store.hook(COMMIT)
    assert store.head() == before
    assert "21 memory files deleted at once (limit 20)" in store.refusal()


def test_a_refusal_is_cleared_by_the_next_clean_run(store):
    (store.projects / ".gitignore").unlink()
    store.hook(COMMIT)
    assert store.refusal() is not None
    store.git("checkout", "--", ".gitignore")
    store.hook(COMMIT)
    assert store.refusal() is None


def test_no_repo_is_silent(store):
    store.env["CLAUDE_MEMORIES_GIT"] = str(store.projects / "nowhere.git")
    silent_ok(store.hook(COMMIT))


def test_a_half_finished_merge_is_left_alone(store):
    (store.git_dir / "MERGE_HEAD").write_text(store.head() + "\n")
    store.memory("p1", "a")
    before = store.head()
    silent_ok(store.hook(COMMIT))
    assert store.head() == before


# --- check-memories-pushed.sh ------------------------------------------------


def message(done):
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)["systemMessage"] if done.stdout.strip() else None


def test_all_pushed_says_nothing(store):
    silent_ok(store.hook(CHECK))


def test_a_missing_repo_is_reported_with_the_fix(store):
    store.env["CLAUDE_MEMORIES_GIT"] = str(store.projects / "nowhere.git")
    assert "Run claude-memory-setup" in message(store.hook(CHECK))


def test_a_recorded_refusal_is_shown_first(store):
    (store.git_dir / "last-refusal").write_text("2026-11-09 10:00 a non-memory path is visible: x\n")
    m = message(store.hook(CHECK))
    assert "refused to commit: 2026-11-09 10:00 a non-memory path is visible: x" in m
    assert f"git -C {store.projects} --git-dir={store.git_dir} status -uall" in m


def test_a_rejected_push_is_reported_at_once(store):
    """Two machines diverged: waiting a day to say 'not pushed' hides the cause."""
    (store.git_dir / "last-push.log").write_text(
        "To remote.git\n ! [rejected]        HEAD -> main (fetch first)\n"
    )
    m = message(store.hook(CHECK))
    assert "the last push was rejected" in m and "pull --rebase" in m


def test_a_clean_push_log_is_not_a_rejection(store):
    (store.git_dir / "last-push.log").write_text("")
    silent_ok(store.hook(CHECK))


def test_no_upstream_is_reported(store):
    store.git("branch", "--unset-upstream", "main")
    assert "no upstream" in message(store.hook(CHECK))


def test_a_young_unpushed_commit_is_not_worth_a_warning(store):
    store.memory("p1", "a")
    store.git("add", "-A")
    store.git("commit", "-q", "-m", "fresh")
    silent_ok(store.hook(CHECK))


def test_a_day_old_unpushed_commit_is_reported(store):
    store.memory("p1", "a")
    store.git("add", "-A")
    store.env["GIT_COMMITTER_DATE"] = f"@{int(time.time()) - 2 * 86400} +0000"
    store.git("commit", "-q", "-m", "old")
    del store.env["GIT_COMMITTER_DATE"]
    m = message(store.hook(CHECK))
    assert m.startswith("claude-memories: 1 commit(s) not pushed, oldest 4") and "h old" in m
