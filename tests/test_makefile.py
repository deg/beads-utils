"""Tests for the Makefile's install/uninstall targets and its discovery vars.

Why this file exists: `make install PREFIX=~/bin` once created a directory
literally *named* `~` in the repo instead of installing to ~/bin, and shipped
to the user because nothing in a 938-test suite invoked make at all. The
dry-run tier below would have caught it outright, for free.

Two tiers, cheap first:

* `make -n` assertions read the recipe make *would* run. No filesystem
  mutation, no reliance on the target existing, and they catch the whole
  class of variable-expansion bug that escaped.
* Real-filesystem tests install into `tmp_path` and check the behaviours that
  only show up when the links exist.

Rules for anything added here:

* Never invoke `make test` or `make ci` -- that recurses into this suite.
* Always pass an explicit PREFIX under `tmp_path`. A test that let PREFIX
  default would install into the developer's real ~/.local/bin.
* Recipes use `$(CURDIR)`, so make must run with cwd at the repo root.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BIN, ROOT

# make is a new test-time dependency for a suite that otherwise needs only
# python and uv. It is there in CI and on any dev machine, but skipping beats
# a confusing failure on one that lacks it.
HAVE_MAKE = shutil.which("make") is not None

pytestmark = [
    pytest.mark.makefile,
    pytest.mark.skipif(not HAVE_MAKE, reason="make not installed"),
]

SCRIPT_COUNT = 16


def run_make(*args: str, expect_ok: bool = True) -> subprocess.CompletedProcess:
    """Run make at the repo root and return the finished process."""
    done = subprocess.run(
        ["make", *args], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if expect_ok:
        assert done.returncode == 0, f"make {' '.join(args)} failed:\n{done.stdout}"
    return done


def dry_run(*args: str) -> str:
    """Return the shell make *would* run, without running any of it."""
    return run_make("-n", *args).stdout


# --------------------------------------------------------------------------
# Tier 1 -- PREFIX handling, read off the recipe make would run
# --------------------------------------------------------------------------

def test_leading_tilde_is_expanded():
    """The f066e16 regression, pinned.

    zsh does not tilde-expand an argument that merely looks like an
    assignment, so make receives a literal `~` and substitutes it into the
    recipe inside double quotes, where the shell will not expand it either.
    `mkdir -p "~/bin"` then creates a directory named `~` in the repo -- which
    .gitignore's `*~` pattern hides, so it goes unnoticed.
    """
    out = dry_run("install", "PREFIX=~/bin")
    assert f'mkdir -p "{Path.home()}/bin"' in out
    assert '"~/bin"' not in out


def test_bare_tilde_is_expanded():
    """`PREFIX=~` is the same bug with nothing after the tilde to anchor on."""
    assert f'mkdir -p "{Path.home()}"' in dry_run("install", "PREFIX=~")


def test_absolute_prefix_passes_through_untouched():
    """Normalization must not corrupt the ordinary case it does not apply to."""
    assert 'mkdir -p "/tmp/xyz"' in dry_run("install", "PREFIX=/tmp/xyz")


def test_trailing_slash_does_not_break_the_path_check():
    """A trailing slash made the PATH test compare `/x/bin/` against `/x/bin`.

    It can never match, so install reported a directory as missing from a
    PATH it was already on -- advice that sends you editing a working rc file.
    """
    out = dry_run("install", "PREFIX=/tmp/xyz/")
    assert '":/tmp/xyz:"' in out
    assert '":/tmp/xyz/:"' not in out


def test_prefix_containing_spaces_stays_quoted():
    """Word splitting here would scatter symlinks across two directories."""
    assert 'mkdir -p "/my dir/bin"' in dry_run("install", "PREFIX=/my dir/bin")


@pytest.mark.parametrize("prefix", ["", "~root/bin", "~+", "~-"])
def test_unexpandable_prefix_is_refused(prefix):
    """Forms make cannot expand must be refused, never guessed at.

    `~user` is the literal-`~`-directory bug wearing a different hat: make has
    no way to look up another user's home, so expanding it would mean
    inventing one. Empty is a typo that would otherwise target `/bd-log`.
    """
    done = run_make("install", f"PREFIX={prefix}", expect_ok=False)
    assert done.returncode != 0
    assert "error:" in done.stdout
    assert not (ROOT / "~").exists(), "a literal ~ directory leaked into the repo"


# --------------------------------------------------------------------------
# Tier 2 -- install/uninstall against a real directory
# --------------------------------------------------------------------------

def test_install_links_every_script(tmp_path):
    """All ten, as symlinks pointing back at this checkout."""
    run_make("install", f"PREFIX={tmp_path}")
    links = sorted(p for p in tmp_path.iterdir() if p.is_symlink())
    assert len(links) == SCRIPT_COUNT
    assert all(Path(os.readlink(p)).parent == BIN for p in links)


def test_installed_script_runs_from_outside_the_repo(tmp_path):
    """The property the whole symlink approach rests on.

    Each script does `from bdutils import ...`, which resolves only because
    Python puts the script's directory on sys.path[0] -- and it uses the
    *resolved* directory, so the sibling import survives the link. If that
    ever stopped being true, `make install` would produce ten scripts that
    all die on import, and nothing else in the suite would notice.
    """
    run_make("install", f"PREFIX={tmp_path}")
    done = subprocess.run(
        [str(tmp_path / "bd-log"), "--version"], cwd="/", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert done.returncode == 0, done.stdout
    assert done.stdout.startswith("bd-log ")


def test_install_is_idempotent(tmp_path):
    """Re-running must refresh the links, not trip its own non-symlink guard."""
    run_make("install", f"PREFIX={tmp_path}")
    run_make("install", f"PREFIX={tmp_path}")
    assert len([p for p in tmp_path.iterdir() if p.is_symlink()]) == SCRIPT_COUNT


def test_install_refuses_to_replace_a_real_file(tmp_path):
    """Someone else's `bd-log` in ~/.local/bin is not ours to overwrite."""
    (tmp_path / "bd-log").write_text("precious\n")
    done = run_make("install", f"PREFIX={tmp_path}", expect_ok=False)
    assert done.returncode != 0
    assert "refusing to replace non-symlink" in done.stdout
    assert (tmp_path / "bd-log").read_text() == "precious\n"


def test_refusal_links_nothing_at_all(tmp_path):
    """The pre-flight is a separate loop so a refusal is not a half-install.

    Fold the check into the linking loop and this fails: the scripts sorted
    before the conflicting one are already linked when it bails.
    """
    (tmp_path / "bd-view").write_text("precious\n")
    run_make("install", f"PREFIX={tmp_path}", expect_ok=False)
    assert [p for p in tmp_path.iterdir() if p.is_symlink()] == []


def test_uninstall_leaves_everything_else_alone(tmp_path):
    """It must remove its own links and nothing that merely shares the dir."""
    run_make("install", f"PREFIX={tmp_path}")
    (tmp_path / "plain-file").write_text("mine\n")
    (tmp_path / "foreign-link").symlink_to("/bin/echo")

    done = run_make("uninstall", f"PREFIX={tmp_path}")
    assert f"Removed {SCRIPT_COUNT} symlink(s)" in done.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["foreign-link", "plain-file"]


def test_uninstall_removes_a_link_whose_script_is_gone(tmp_path):
    """Uninstall must not iterate only the scripts that exist *now*.

    Install at one revision, rename or drop a script, uninstall: a target list
    built from the current tree skips that name, leaving a dangling link
    behind while the count claims a complete removal.
    """
    run_make("install", f"PREFIX={tmp_path}")
    (tmp_path / "bd-departed").symlink_to(BIN / "bd-departed")

    done = run_make("uninstall", f"PREFIX={tmp_path}")
    assert f"Removed {SCRIPT_COUNT + 1} symlink(s)" in done.stdout
    assert list(tmp_path.iterdir()) == []


def test_uninstall_removes_links_from_before_bin(tmp_path):
    """The scripts lived at the repo root until they moved into bin/.

    An install made then links to `<clone>/bd-log`, which now dangles; an
    uninstall that recognised only bin/ targets would leave every one behind.
    A link to something deeper in the clone is still not ours.
    """
    (tmp_path / "bd-log").symlink_to(ROOT / "bd-log")
    (tmp_path / "a-doc").symlink_to(ROOT / "docs" / "beads.md")

    done = run_make("uninstall", f"PREFIX={tmp_path}")
    assert "Removed 1 symlink(s)" in done.stdout
    assert [p.name for p in tmp_path.iterdir()] == ["a-doc"]


def test_uninstall_on_a_clean_directory_reports_zero(tmp_path):
    """Must succeed and say so, not fail on the empty glob."""
    assert "Removed 0 symlink(s)" in run_make("uninstall", f"PREFIX={tmp_path}").stdout


def test_uninstall_reports_failure_it_cannot_recover_from(tmp_path):
    """Counting attempts rather than successes made uninstall unable to fail.

    A read-only PREFIX used to print "Removed 10" and exit 0 having removed
    nothing -- the report and the exit status both lying.
    """
    run_make("install", f"PREFIX={tmp_path}")
    tmp_path.chmod(0o555)
    try:
        done = run_make("uninstall", f"PREFIX={tmp_path}", expect_ok=False)
    finally:
        tmp_path.chmod(0o755)
    assert done.returncode != 0
    assert "could not be removed" in done.stdout
    assert len([p for p in tmp_path.iterdir() if p.is_symlink()]) == SCRIPT_COUNT


# --------------------------------------------------------------------------
# Tier 3 -- the discovery variables everything else is built on
# --------------------------------------------------------------------------

def make_variable(name: str) -> str:
    """Read an expanded variable out of make's own database."""
    for line in run_make("-np").stdout.splitlines():
        if line.startswith(f"{name} :=") or line.startswith(f"{name} ="):
            return line.split("=", 1)[1].strip()
    pytest.fail(f"{name} not found in make's database")


def executables(directory: Path) -> set[str]:
    return {
        p.name for p in directory.iterdir()
        if p.is_file() and os.access(p, os.X_OK)
        and p.read_bytes()[:2] == b"#!"
    }


def test_scripts_finds_exactly_the_bin_executables():
    """Shebang discovery is what `smoke`, `install` and lint all iterate.

    It must find every script in bin/ and nothing in a subdirectory -- a
    helper there would be dragged into `make smoke`, which runs `--version`
    on whatever it finds. The names are bare, because `install` links each
    one into PREFIX under that name.
    """
    found = set(make_variable("SCRIPTS").split())
    assert found == executables(BIN)
    assert len(found) == SCRIPT_COUNT
    assert not any("/" in name for name in found)


def test_no_script_is_left_at_the_root():
    """Discovery reads only bin/, so a script added at the root by habit
    would be silently left out of lint, the smoke test and the install."""
    assert executables(ROOT) == set()


def test_lint_targets_cover_every_python_file():
    """The gap that left claudeutils.py unlinted, and that tools/ hit again.

    Shebang discovery finds neither the helper modules (no shebang) nor
    anything in a subdirectory, so LINT_TARGETS names those by hand -- and a
    hand-maintained list silently rots when a directory is added.
    """
    targets = make_variable("LINT_TARGETS").split()
    covered_dirs = {t.rstrip("/") for t in targets if t.endswith("/")}
    named = set(targets)
    # A directory target covers everything under it; a file must be named.
    # (An earlier cut also accepted a literal `*.py` target for root-level
    # files, without the depth condition, and so passed with tools/ missing.)
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part.startswith(".") for part in rel.parts):
            continue
        covered = rel.parts[0] in covered_dirs or str(rel) in named
        assert covered, f"{rel} is not covered by LINT_TARGETS"


# --------------------------------------------------------------------------
# install-claude / uninstall-claude -- the skills and hooks, into CLAUDE_HOME
# --------------------------------------------------------------------------

HOOK_COUNT = 4
SKILL_COUNT = 6


def test_install_claude_links_every_hook_and_skill(tmp_path):
    """Hooks into CLAUDE_HOME/hooks, skill directories into CLAUDE_HOME/skills."""
    run_make("install-claude", f"CLAUDE_HOME={tmp_path}")
    hooks = sorted(p for p in (tmp_path / "hooks").iterdir() if p.is_symlink())
    skills = sorted(p for p in (tmp_path / "skills").iterdir() if p.is_symlink())
    assert len(hooks) == HOOK_COUNT
    assert len(skills) == SKILL_COUNT
    assert all(Path(os.readlink(p)).parent == ROOT / "hooks" for p in hooks)
    assert all(Path(os.readlink(p)).parent == ROOT / "skills" for p in skills)
    assert all((p / "SKILL.md").is_file() for p in skills)  # the link resolves to the skill


def test_install_claude_refuses_to_replace_a_real_skill(tmp_path):
    """A hand-written ~/.claude/skills/finalize is the user's, not ours to replace."""
    (tmp_path / "skills" / "finalize").mkdir(parents=True)
    (tmp_path / "skills" / "finalize" / "SKILL.md").write_text("precious\n")
    done = run_make("install-claude", f"CLAUDE_HOME={tmp_path}", expect_ok=False)
    assert done.returncode != 0
    assert "refusing to replace non-symlink" in done.stdout
    assert (tmp_path / "skills" / "finalize" / "SKILL.md").read_text() == "precious\n"
    assert not (tmp_path / "hooks").exists()  # nothing linked at all


def test_install_claude_refuses_to_replace_a_real_file(tmp_path):
    """A hook script someone wrote by hand in ~/.claude/hooks is not ours."""
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "commit-memories.sh").write_text("precious\n")
    done = run_make("install-claude", f"CLAUDE_HOME={tmp_path}", expect_ok=False)
    assert done.returncode != 0
    assert "refusing to replace non-symlink" in done.stdout
    assert (tmp_path / "hooks" / "commit-memories.sh").read_text() == "precious\n"
    assert [p for p in (tmp_path / "hooks").iterdir() if p.is_symlink()] == []


def test_uninstall_claude_removes_only_our_links(tmp_path):
    run_make("install-claude", f"CLAUDE_HOME={tmp_path}")
    (tmp_path / "hooks" / "theirs.sh").write_text("mine\n")
    (tmp_path / "hooks" / "foreign-link").symlink_to("/bin/echo")
    (tmp_path / "skills" / "theirs").mkdir()
    done = run_make("uninstall-claude", f"CLAUDE_HOME={tmp_path}")
    assert f"Removed {HOOK_COUNT + SKILL_COUNT} symlink(s)" in done.stdout
    assert sorted(p.name for p in (tmp_path / "hooks").iterdir()) == ["foreign-link", "theirs.sh"]
    assert sorted(p.name for p in (tmp_path / "skills").iterdir()) == ["theirs"]


def test_install_claude_refuses_a_tilde_home(tmp_path):
    done = run_make("install-claude", "CLAUDE_HOME=~/nope", expect_ok=False)
    assert "cannot expand" in done.stdout


def test_install_claude_refuses_without_jq(tmp_path):
    """Hooks that cannot run are not installed; from a pipe nothing is offered either."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)   # the doctor itself needs python3
    done = run_make("install-claude", f"CLAUDE_HOME={tmp_path}", f"PATH={bin_dir}", "DOCTOR_RUN=echo",
                    expect_ok=False)
    assert done.returncode != 0
    assert "the hooks need jq; nothing was linked" in done.stdout
    assert "Install " not in done.stdout   # a pipe is never prompted
    assert not (tmp_path / "hooks").exists()


def test_install_runs_the_doctor_for_the_scripts_tools(tmp_path):
    done = run_make("install", f"PREFIX={tmp_path}", "DOCTOR_RUN=echo")
    assert "Required:" in done.stdout and "python3" in done.stdout
    assert "jq" not in done.stdout   # jq is the hooks' concern, not the scripts'

