"""Shared fixtures and the script loader for the beads-utils test suite.

The scripts under test are executables at the repo root with no `.py`
extension and hyphens in their names (`bd-log`, `claude-session-list`, ...),
so `import bd_log` cannot find them. `load_script()` below imports them by
path; test modules do `from conftest import load_script` (pytest puts this
directory on sys.path, and pytest.ini's `pythonpath` makes that explicit).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The repo root must precede everything so `import bdutils` inside a loaded
# script resolves to the checkout under test rather than to anything installed.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Imported after the sys.path insert above -- these are the checkout's own
# modules, and without it they would resolve to whatever else is installed.
import bdutils  # noqa: E402
import claudeutils  # noqa: E402


def load_script(filename: str):
    """Import a repo-root script that has no importable filename.

    `bd-log` becomes module `bd_log`. Modules are cached in sys.modules under
    that name, so repeated calls (and monkeypatching of module attributes)
    behave exactly like a normal import.
    """
    module_name = filename.replace("-", "_")
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    path = ROOT / filename
    if not path.is_file():
        raise FileNotFoundError(f"no such script: {path}")
    loader = SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_file_location(module_name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so a script that imports itself (none do today)
    # can't recurse, matching normal import semantics.
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


# --- Environment normalization -------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def _utc_timezone():
    """Pin the process timezone to UTC for the whole session.

    bdutils.format_ts() renders in *local* time via .astimezone(), so any test
    asserting a literal formatted timestamp would pass on a developer's machine
    and fail in CI (which runs UTC), or vice versa. Pinning makes the expected
    strings well-defined everywhere. time.tzset() is what actually makes the
    change take -- setting os.environ['TZ'] alone does not re-read the zone.
    """
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    _tzset()
    yield
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    _tzset()


def _tzset() -> None:
    """time.tzset() where it exists (POSIX); a no-op on Windows."""
    if hasattr(time, "tzset"):
        time.tzset()


@pytest.fixture(autouse=True)
def _reset_caches():
    """Clear bdutils' cached dolt probe around every test.

    have_dolt() is @functools.cache'd, so a test that monkeypatches
    shutil.which either has no effect (warm cache) or leaves a poisoned value
    behind for every later test. Clearing on both sides makes the order of
    tests irrelevant.
    """
    bdutils.have_dolt.cache_clear()
    yield
    bdutils.have_dolt.cache_clear()


@pytest.fixture(autouse=True)
def _neutral_output_env(monkeypatch):
    """Remove the environment knobs that would skew color and paging.

    A developer with NO_COLOR or PAGER exported would otherwise get different
    results from CI. Tests that care about these set them explicitly.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("PAGER", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")


# --- Fake external CLIs (`bd`, `dolt`) ------------------------------------

# A tiny stand-in for a real CLI, written into a temp dir that is prepended to
# PATH. Rules are matched against argv, so one fake can serve a script that
# shells out several times with different subcommands.
#
# This works because every script invokes its tools through subprocess with
# only `cwd=` overridden -- os.environ (and therefore PATH) is inherited.
_FAKE_CLI_SOURCE = '''\
#!/usr/bin/env python3
"""Test double for the `{name}` CLI. Behavior comes from ${data_var}."""
import json
import os
import sys

argv = sys.argv[1:]
with open(os.environ["{data_var}"]) as f:
    data = json.load(f)

log = os.environ.get("{log_var}")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(argv) + "\\n")

for rule in data.get("rules", []):
    # A rule matches when every one of its tokens appears as a substring of
    # some argv entry -- so ["list", "--all"] matches `bd list --all --json`,
    # and ["--id="] matches `bd list --id=x,y` without spelling out the value.
    if all(any(tok in arg for arg in argv) for tok in rule.get("match", [])):
        sys.stdout.write(rule.get("stdout", ""))
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(rule.get("exit", 0))

sys.stdout.write(data.get("stdout", ""))
sys.stderr.write(data.get("stderr", ""))
sys.exit(data.get("exit", 0))
'''


class FakeCli:
    """Handle for a fake CLI on PATH: program its replies, read its calls."""

    def __init__(self, bindir: Path, data_path: Path, log_path: Path):
        self.bindir = bindir
        self.data_path = data_path
        self.log_path = log_path
        self._data: dict = {"rules": [], "stdout": "", "stderr": "", "exit": 0}
        self._flush()

    def _flush(self) -> None:
        self.data_path.write_text(json.dumps(self._data))

    def rule(self, *match: str, stdout: str = "", stderr: str = "", exit_code: int = 0):
        """Reply with `stdout` when every token in `match` appears in argv.

        Rules are tried in the order added; the first match wins.
        """
        self._data["rules"].append(
            {"match": list(match), "stdout": stdout, "stderr": stderr, "exit": exit_code}
        )
        self._flush()
        return self

    def json_rule(self, *match: str, payload=None, exit_code: int = 0):
        """Like rule(), but serializes `payload` as the JSON reply."""
        return self.rule(*match, stdout=json.dumps(payload), exit_code=exit_code)

    def default(self, stdout: str = "", stderr: str = "", exit_code: int = 0):
        """Reply used when no rule matches (default: empty output, exit 0)."""
        self._data.update({"stdout": stdout, "stderr": stderr, "exit": exit_code})
        self._flush()
        return self

    def issues(self, issues: list[dict]):
        """Shorthand: any `bd list` returns this issue array as JSON."""
        return self.default(stdout=json.dumps(issues))

    @property
    def calls(self) -> list[list[str]]:
        """Every argv the fake was invoked with, in order."""
        if not self.log_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text().splitlines()
            if line.strip()
        ]


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """Factory: install a programmable executable of any name, first on PATH.

    The fake bin dir is *prepended*, so a fake shadows any real tool of the
    same name (a developer with dolt installed gets the same result as CI,
    which has none) while `git` and friends stay reachable. A test that needs
    a tool to be genuinely absent sets PATH itself.
    """
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    def _install(name: str) -> FakeCli:
        safe = name.replace("-", "_").upper()
        data_var, log_var = f"FAKE_{safe}_DATA", f"FAKE_{safe}_LOG"
        script = bindir / name
        script.write_text(
            _FAKE_CLI_SOURCE.format(name=name, data_var=data_var, log_var=log_var)
        )
        script.chmod(0o755)

        data_path = tmp_path / f"fake-{name}-data.json"
        log_path = tmp_path / f"fake-{name}-calls.log"
        monkeypatch.setenv(data_var, str(data_path))
        monkeypatch.setenv(log_var, str(log_path))
        return FakeCli(bindir, data_path, log_path)

    return _install


@pytest.fixture
def fake_bd(fake_cli) -> FakeCli:
    """A programmable `bd` executable, first on PATH for the duration."""
    return fake_cli("bd")


@pytest.fixture
def fake_dolt(fake_cli) -> FakeCli:
    """A programmable `dolt` executable, first on PATH for the duration."""
    return fake_cli("dolt")


@pytest.fixture
def project(tmp_path) -> Path:
    """A directory that passes bdutils.resolve_project_path()'s .beads/ check."""
    root = tmp_path / "project"
    beads = root / ".beads"
    beads.mkdir(parents=True)
    (beads / "metadata.json").write_text(
        json.dumps({"dolt_database": "testdb", "dolt_mode": "embedded"})
    )
    return root


# --- End-to-end runner ----------------------------------------------------


@pytest.fixture
def run_script(project):
    """Run a repo-root script as a real subprocess and capture the result.

    Invoked as `sys.executable <root>/<script>` rather than `./<script>`: that
    keeps bd-view off its `uv run --script` shebang, which would re-resolve
    `rich` per call (slow on a cold cache) and test a different interpreter
    than the rest of the suite. Passing the script path still puts the repo
    root on sys.path[0], so the `from bdutils import ...` sibling import
    resolves exactly as it does in real use.
    """

    def _run(script: str, *args: str, cwd: Path | None = None, env: dict | None = None):
        full_env = dict(os.environ)
        full_env["TZ"] = "UTC"
        # An inherited PYTHONPATH could shadow the checkout's bdutils.
        full_env.pop("PYTHONPATH", None)
        if env:
            full_env.update(env)
        return subprocess.run(
            [sys.executable, str(ROOT / script), *args],
            cwd=str(cwd or project),
            capture_output=True,
            text=True,
            env=full_env,
        )

    return _run


# --- Session fixtures (Claude Code JSONL) ---------------------------------


@pytest.fixture
def claude_home(tmp_path, monkeypatch) -> Path:
    """An empty stand-in for ~/.claude/projects, wired into claudeutils.

    Every session-reading test uses this so the suite never reads (or is
    perturbed by) the developer's real session history.

    Patching `claudeutils` alone is sufficient, and that is a property worth
    keeping: it holds only because `claudeutils.CLAUDE_PROJECTS` is the single
    binding every consumer reads through. When claude-session-find carried its
    own copy (beads-utils-8ju), this fixture silently missed it — the patch
    succeeded and changed nothing, so a test would have read the developer's
    real directory. test_claude_session_find.py asserts the single-binding
    invariant directly, which is what keeps this one-liner honest.
    """
    projects = tmp_path / "claude-projects"
    projects.mkdir()
    monkeypatch.setattr(claudeutils, "CLAUDE_PROJECTS", projects)
    return projects


def write_session(project_dir: Path, uuid: str, entries: list[dict]) -> Path:
    """Write `entries` as a session JSONL and return its path."""
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def user_entry(text: str, **extra) -> dict:
    """A `type=user` session entry carrying `text` as its message content."""
    entry = {"type": "user", "message": {"role": "user", "content": text}}
    entry.update(extra)
    return entry


def assistant_entry(text: str, **extra) -> dict:
    """A `type=assistant` session entry with a single text block."""
    entry = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }
    entry.update(extra)
    return entry
