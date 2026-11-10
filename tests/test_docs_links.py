"""Every relative link and image in the README and docs/ must resolve.

The README became a front page with the prose moved to docs/ pages, and the
index works only while its links do: a renamed heading or a moved image would
otherwise rot in silence, since nothing else reads the Markdown. Anchors are
checked against the target's headings using GitHub's slug rules (lowercase,
punctuation dropped, spaces to hyphens), which is what the links are written
against.
"""
from __future__ import annotations

import re

import pytest

from conftest import ROOT

PAGES = sorted([ROOT / "README.md", *(ROOT / "docs").glob("*.md")])
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.M)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, keep word chars, spaces and hyphens."""
    text = heading.replace("`", "")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", text)


def anchors(page) -> set[str]:
    return {slug(h) for h in HEADING.findall(page.read_text())}


def links(page):
    for target in LINK.findall(page.read_text()):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        yield target


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_relative_link_resolves(page):
    for target in links(page):
        path_part, _, anchor = target.partition("#")
        resolved = (page.parent / path_part).resolve() if path_part else page
        assert resolved.exists(), f"{page.name}: {target} -> {resolved} does not exist"
        if anchor and resolved.suffix == ".md":
            assert anchor in anchors(resolved), f"{page.name}: {target} has no heading '{anchor}'"


def test_the_pages_are_all_linked_from_the_readme():
    """A docs page nobody links to is a page nobody finds."""
    readme = (ROOT / "README.md").read_text()
    for page in (ROOT / "docs").glob("*.md"):
        assert f"docs/{page.name}" in readme, page.name


def test_slug_follows_githubs_rules():
    assert slug("bd-dolt-check and bd-dolt-diff") == "bd-dolt-check-and-bd-dolt-diff"
    assert slug("The hooks") == "the-hooks"
    assert slug("Looking at `beads`!") == "looking-at-beads"
