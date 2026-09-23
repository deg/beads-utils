---
paths:
  - "bdutils.py"
  - "tests/test_bdutils.py"
---

# bdutils.py design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

`bdutils.py` — `error()`, `warn()`, `resolve_project_path()`,
`format_ts()`, `format_priority()`, and `paged_output()` (context manager
that pipes through `$PAGER` or `less -FRX` when stdout is a tty; `-F` makes
short output indistinguishable from direct-to-stdout). Color lives here
too: the `COLORS`/`RESET` SGR constants, `add_color_arg()`,
`want_color(mode)` (`auto` = tty **and** `NO_COLOR` unset **and** `TERM !=
dumb`), and `paint(text, color, enabled)`, whose `color` is one or more
space-separated `COLORS` names so attributes compose (`"bold blue"`);
unknown names are skipped, never raised. Stick to the plain 30–37 hues:
the bright slots (90–97) are repurposed as *greys* by Solarized, and
`bold` reaches those same slots on terminals set to "draw bold text in
bright colors" — so bolting `bold` onto a hue can silently remove the
hue. Both were tried against a real Solarized Light terminal and backed
out. Widen the colored *area* or pick a better-separated hue instead.
Imported by scripts in this repo; keep small and stdlib-only.
