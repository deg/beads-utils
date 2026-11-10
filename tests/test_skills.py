"""Tests for the beads-workflow skills under skills/.

A skill is a directory holding SKILL.md, linked into ~/.claude/skills/<name>
by `make install-claude` so it answers to /<name>. These tests hold the
shape Claude Code needs (frontmatter with a matching name and a description),
the conventions the skills share (extensions read from the user's directory
and then the project's), and the promise the port made: nothing in the
public text names the owner, their machine, or the private repo the skills
came from.
"""
from __future__ import annotations

import re

import pytest

from conftest import ROOT

SKILLS_DIR = ROOT / "skills"
SKILLS = sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())
WITH_EXTENSIONS = ["start-task", "finalize", "defer", "close-shop"]

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def frontmatter(name: str) -> dict[str, str]:
    text = (SKILLS_DIR / name / "SKILL.md").read_text()
    m = FRONTMATTER.match(text)
    assert m, f"{name}: no frontmatter"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def body(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text()


def test_the_expected_skills_are_shipped():
    assert SKILLS == ["changelog", "close-shop", "defer", "finalize", "start-task", "status"]


@pytest.mark.parametrize("name", SKILLS)
def test_frontmatter_names_the_skill_after_its_directory(name):
    """The name decides the slash command; a mismatch would answer to the wrong word."""
    fields = frontmatter(name)
    assert fields["name"] == name
    assert len(fields["description"]) > 40, "the description is what lets Claude pick the skill"
    # Unquoted YAML scalars may not hold `: ` or ` #`; the naive parse above would miss it.
    assert ": " not in fields["description"] and " #" not in fields["description"]


@pytest.mark.parametrize("name", WITH_EXTENSIONS)
def test_extensions_are_read_from_the_user_then_the_project(name):
    """Both places, user first: the user's carries their standing conventions."""
    text = body(name)
    user = f"~/.claude/skill-extensions/{name}.md"
    # The user path contains the project path, so the project one is found
    # only where no `~/` precedes it.
    project = re.compile(rf"(?<!~/)\.claude/skill-extensions/{re.escape(name)}\.md")
    standalone = [m.start() for m in project.finditer(text)]
    assert user in text
    assert standalone, "the project path must appear on its own too"
    assert text.index(user) < standalone[0]


def test_close_shop_calls_the_tools_by_their_installed_names():
    text = body("close-shop")
    assert "bd-find-live --lean" in text
    assert "bd-find-live | wc -c" in text
    assert "claude-memory-check" in text
    assert "~/.claude/hooks/commit-memories.sh" in text
    for old in ("audited-beads", "check-memory-links", "python3 ~/"):
        assert old not in text, old


SELF_GRANT = re.compile(
    r"carve-out|need(s)? no (further )?(approval|permission)|without asking|pre-authori[sz]ed",
    re.I,
)


def test_close_shop_grants_no_standing_permission_of_its_own():
    """Pushing is the user's call; a carve-out lives in their extension, not here.

    Any wording that has the skill granting itself a permission is caught,
    not just the two phrases the port removed.
    """
    text = body("close-shop")
    assert not SELF_GRANT.search(text), SELF_GRANT.search(text).group(0)
    assert "Pushing is the user's call" in text


# The files this port wrote or rewrote. Older rule files describe the owner's
# own machine (bd-verify-backup.md names their repos) and are not in scope.
PORTED_RULES = ["skills.md", "hooks.md", "claude-memory.md", "bd-find-live.md"]
PUBLIC_TEXT = sorted(
    [p for p in SKILLS_DIR.glob("*/SKILL.md")]
    + [ROOT / ".claude" / "rules" / r for r in PORTED_RULES]
    + [ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "CONTRIBUTING.md"]
)


@pytest.mark.parametrize("path", PUBLIC_TEXT, ids=lambda p: str(p.relative_to(ROOT)))
def test_nothing_personal_is_in_the_public_text(path):
    """The skills came from a private dotfiles repo; the generic markers of it must be gone.

    The rule files and the top-level docs describe the port, so they are
    scanned too; the first review found the private path quoted in one.
    """
    text = path.read_text()
    # A home-relative repo path with a claude/ directory is the shape the
    # private dotfiles had; the name itself is deliberately not written here.
    for marker in (r"~/[A-Za-z0-9._-]+/claude/", r"/Users/", r"~/CLAUDE\.md", r"\bDavid\b"):
        m = re.search(marker, text)
        assert not m, f"{path.name}: {m.group(0)}"
