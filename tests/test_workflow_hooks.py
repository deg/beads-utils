"""Tests for the two beads-workflow hooks: claim-guard.sh and defer-hint.sh.

Both run as Claude Code runs them, a bash subprocess with the hook JSON on
stdin. Both are built to be silent almost always, so the tests of silence
matter as much as the tests of output: a hook that fires on ordinary
commands or ordinary English costs context in every session.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

GUARD = ROOT / "hooks" / "claim-guard.sh"
HINT = ROOT / "hooks" / "defer-hint.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="the hooks need jq")

needs_timeout = pytest.mark.skipif(
    not (shutil.which("timeout") or shutil.which("gtimeout")),
    reason="the in-progress clause needs GNU timeout",
)


# --- claim-guard.sh ----------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    """A git repo with one commit, and the env the guard runs under.

    Listed after fake_bd in a test's parameters, so the environment snapshot
    taken here carries the fake's PATH entry and data variables.
    """
    root = tmp_path / "repo"
    root.mkdir()
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "CLAUDE_PROJECT_DIR": str(root),
    })
    subprocess.check_call(["git", "init", "-q", str(root)], env=env)
    (root / "README").write_text("hi\n")
    subprocess.check_call(["git", "-C", str(root), "add", "-A"], env=env)
    subprocess.check_call(["git", "-C", str(root), "commit", "-q", "-m", "init"], env=env)
    return root, env


def guard(env, command, cwd=None, **extra):
    payload = {"tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    payload.update(extra)
    return subprocess.run(
        ["bash", str(GUARD)], input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )


def decision(done):
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    specific = out["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "ask"
    # The reason reaches the user, additionalContext the agent: same text, both.
    assert out["systemMessage"] == specific["permissionDecisionReason"] == specific["additionalContext"]
    return out["systemMessage"]


def silent(done):
    assert done.returncode == 0 and done.stdout == "" and done.stderr == "", done


def test_a_claim_on_a_clean_tree_passes_silently(repo):
    root, env = repo
    silent(guard(env, "bd update x-1 --claim"))


def test_a_claim_on_a_dirty_tree_becomes_a_permission_ask(repo):
    root, env = repo
    (root / "work.py").write_text("x\n")
    (root / "README").write_text("changed\n")
    m = decision(guard(env, "bd update x-1 --claim"))
    assert m.startswith("claim-guard: claiming a new bead while 2 path(s) are uncommitted (README work.py).")
    assert "one bead, one commit, at the boundary" in m


@pytest.mark.parametrize("command", [
    "bd update x-1 --claim",
    "bd update --claim x-1",
    "cd src && bd  update   x-1   --claim",
    "bd update x-1 --claim && bd show x-1",
    "bd update x-1 --claim; git status",      # a separator right after --claim
    "bd update x-1 --claim&&ls",
    "(bd update x-1 --claim)",
    "bd --db foo update x-1 --claim",         # a global flag before the subcommand
    "bd update x-1 \\\n  --claim",            # continued over two lines
])
def test_every_claim_spelling_is_recognized(repo, command):
    root, env = repo
    (root / "work.py").write_text("x\n")
    decision(guard(env, command))


@pytest.mark.parametrize("command", [
    "bd update x-1 --status open",   # update without a claim
    "bd show x-1",
    "echo 'bd update x-1 --claimed'",  # --claim as a prefix of a longer word
    "mybd update x-1 --claim",         # bd as the tail of a longer word
    "bd-update x-1 --claim",           # bd- is not the bd command
    "ls",
])
def test_other_commands_are_not_claims(repo, command):
    """The tree is dirty, so any false match would show as a prompt."""
    root, env = repo
    (root / "work.py").write_text("x\n")
    silent(guard(env, command))


def test_a_quoted_claim_is_accepted_as_a_false_prompt(repo):
    """Known and deliberate: the pattern has no notion of quotes.

    A commit message or doc edit that cites `bd update x --claim` prompts
    once. An ask can afford that; a quote-aware regex could not be trusted
    with a guard.
    """
    root, env = repo
    (root / "work.py").write_text("x\n")
    decision(guard(env, "git commit -m 'note: bd update x-1 --claim is guarded'"))


def test_beads_bookkeeping_alone_is_not_dirty(repo):
    """.beads/ goes dirty from closing a bead and rides along in the next commit."""
    root, env = repo
    (root / ".beads").mkdir()
    (root / ".beads" / "issues.jsonl").write_text("{}\n")
    silent(guard(env, "bd update x-1 --claim"))


def test_more_than_six_paths_are_elided(repo):
    root, env = repo
    for i in range(8):
        (root / f"f{i}.py").write_text("x\n")
    m = decision(guard(env, "bd update x-1 --claim"))
    assert "while 8 path(s) are uncommitted (f0.py f1.py f2.py f3.py f4.py f5.py ...)" in m


def test_the_status_check_takes_no_lock(repo):
    """Another agent's commit must not fail because the guard refreshed the index."""
    root, env = repo
    (root / "work.py").write_text("x\n")
    done = subprocess.run(
        ["bash", "-x", str(GUARD)], input=json.dumps({"tool_input": {"command": "bd update x-1 --claim"}}),
        capture_output=True, text=True, env=env,
    )
    status_lines = [line for line in done.stderr.splitlines() if " status --porcelain" in line]
    assert status_lines and all("--no-optional-locks" in line for line in status_lines), done.stderr


@needs_timeout
def test_in_progress_beads_are_named_as_candidates(fake_bd, repo):
    """Named as candidates, never as owners: every agent claims under one assignee."""
    root, env = repo
    (root / "work.py").write_text("x\n")
    fake_bd.issues([
        {"id": "x-9", "issue_type": "epic"},
        {"id": "x-2", "issue_type": "task"}, {"id": "x-3", "issue_type": "bug"},
        {"id": "x-4", "issue_type": "task"}, {"id": "x-5", "issue_type": "task"},
        {"id": "x-6", "issue_type": "task"},
    ])
    m = decision(guard(env, "bd update x-1 --claim"))
    assert " In progress right now: x-2, x-3, x-4, x-5 and more. Rule:" in m
    assert "x-9" not in m


@needs_timeout
def test_a_failing_bd_just_omits_the_clause(fake_bd, repo):
    root, env = repo
    (root / "work.py").write_text("x\n")
    fake_bd.default(stderr="dolt locked\n", exit_code=1)
    m = decision(guard(env, "bd update x-1 --claim"))
    assert "In progress right now" not in m


def test_outside_a_git_repo_it_is_silent(repo, tmp_path):
    root, env = repo
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path / "not-a-repo")
    (tmp_path / "not-a-repo").mkdir()
    silent(guard(env, "bd update x-1 --claim"))


def test_the_cwd_in_the_payload_is_the_fallback_root(repo):
    root, env = repo
    del env["CLAUDE_PROJECT_DIR"]
    (root / "work.py").write_text("x\n")
    decision(guard(env, "bd update x-1 --claim", cwd=root))
    silent(guard(env, "bd update x-1 --claim"))  # no root at all: nothing to check


# --- defer-hint.sh -----------------------------------------------------------


def hint(prompt):
    return subprocess.run(
        ["bash", str(HINT)], input=json.dumps({"prompt": prompt}),
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("prompt", [
    "Please defer this bead until next quarter",
    "Let's park that issue for now",
    "Shelve the ticket",
    "can we SET ASIDE this task?",
    "I'd punt bd-xyz to later",
    "we parked that issue, right?",        # past tense
    "defer these tasks",                   # plural noun
    "postpone the issues until the review",
])
def test_a_park_verb_with_a_task_noun_points_at_the_skill(prompt):
    done = hint(prompt)
    assert done.returncode == 0
    assert "Follow the /defer skill" in done.stdout
    assert "Never use 'bd close' to park" in done.stdout


@pytest.mark.parametrize("prompt", [
    "deferred tools are now available; a task-notification follows",  # the harness's own wording
    "park the car",                        # verb without a task noun
    "close this bead",                     # task noun without a park verb
    "",
])
def test_ordinary_english_is_silent(prompt):
    done = hint(prompt)
    assert done.returncode == 0
    assert done.stdout == "", done.stdout


def test_known_edge_parking_lot_fires():
    """Documented limitation: `parking` + `issue` fires.

    The regex has no notion of a noun phrase. One stray hint costs a line;
    a missed park costs a bead. This test keeps the edge visible rather than
    pretending the hook is sharper than it is.
    """
    assert "Follow the /defer skill" in hint("the parking lot issue").stdout


def test_an_empty_payload_is_silent():
    done = subprocess.run(["bash", str(HINT)], input="{}", capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == ""
