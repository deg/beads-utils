---
paths:
  - "tests/**"
  - "pytest.ini"
---

# Test-suite design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

Tests are a pytest suite under `tests/`, run through `uv` so nothing is
installed into any global environment (`pytest.ini` is config, not packaging —
a `pyproject.toml` would read as packaging the collection).

Design of the suite, and the traps it exists to survive:

- `tests/conftest.py` provides `load_script("bd-log")` — the scripts are
  executables with no `.py` extension and hyphens in their names, so a normal
  import can't reach them. `pytest.ini` sets `pythonpath = . tests`, which is
  what makes the scripts' own `from bdutils import ...` resolve.
- **No real external state.** `bd` and `dolt` are replaced by programmable
  fakes on `PATH` (`fake_bd` / `fake_dolt`, matching rules against argv in the
  order added — a bare token can shadow a longer one, so register the specific
  rule first). Claude session history is synthetic `.jsonl` under `tmp_path`
  with `claudeutils.CLAUDE_PROJECTS` monkeypatched, or a fake `HOME` for
  subprocess runs. Nothing reads a real beads project or the user's sessions.
  `git` is the exception that runs for real, always in `tmp_path` repos
  (`bd-verify-backup`'s tests, against a bare local remote, with
  `GIT_CONFIG_GLOBAL=/dev/null`).
- `bdutils.error()` calls `sys.exit(str)`; the message is printed by the
  interpreter's top-level handler, which never runs under `pytest.raises`, so
  assert on `excinfo.value.code`. `warn()` writes to stderr directly and *is*
  visible to `capsys`. Two different assertion styles, same module.
- `format_ts()` renders **local** time via `.astimezone()`, so a session
  fixture pins `TZ=UTC` (with `time.tzset()`, which is what actually makes it
  take). Without it, literal-timestamp assertions pass on a Mac and fail in CI.
- `have_dolt()` is `@functools.cache`d: an autouse fixture clears it around
  every test, or a monkeypatched `shutil.which` either does nothing (warm
  cache) or leaks into later tests.
- Scripts do `from bdutils import X`, so patches must target the **script**
  module's attribute, not `bdutils`'.
- Piping stdout inverts two defaults — `want_color("auto")` is False and
  `_open_pager()` returns None — so end-to-end output is plain and unpaged
  unless a flag says otherwise. Color is tested with `--color=always`.
- `tests/test_e2e.py` runs each script as `sys.executable ./<script>`, not
  `./<script>`: the latter sends `bd-view` back through its `uv run --script`
  shebang, which re-resolves `rich` per call.
- `bd-view`'s rich-path tests are `skipif(not HAVE_RICH)` rather than silently
  exercising only the plain-text fallback; CI passes `--with rich` so the
  branch a user actually gets is the one covered.
