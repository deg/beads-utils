"""Tests for tools/doctor.py, the dependency report behind make doctor / install.

The property that matters: it installs nothing without a `y`, and it never
prompts a pipe. Everything that would run an installer is exercised with
`--run echo`, so the command is printed and nothing on the machine changes.
"""
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader

import pytest

from conftest import ROOT

DOCTOR = ROOT / "tools" / "doctor.py"

loader = SourceFileLoader("doctor", str(DOCTOR))
spec = importlib.util.spec_from_file_location("doctor", DOCTOR, loader=loader)
doctor = importlib.util.module_from_spec(spec)
# Registered before exec, as conftest's load_script does: @dataclass looks the
# class's module up in sys.modules while the module is still executing.
sys.modules["doctor"] = doctor
loader.exec_module(doctor)


def tool(name="x", optional=False, brew="x", apt="x", url="", alternates=()):
    return doctor.Tool(name, "purpose of " + name, "more about " + name, brew=brew, apt=apt,
                       url=url, needed_by=frozenset({"install"}), optional=optional, alternates=alternates)


# --- report ----------------------------------------------------------------


def test_report_marks_present_and_missing(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: "/bin/x" if n == "here" else None)
    out = io.StringIO()
    missing = doctor.report([tool("here"), tool("gone", optional=True)], "brew", out)
    text = out.getvalue()
    assert "[ok]       here" in text and "Required:" in text
    assert "[missing]  gone" in text and "Optional:" in text and "install: brew install x" in text
    assert [t.name for t in missing] == ["gone"]


def test_an_alternate_name_counts_as_present(monkeypatch):
    """gtimeout is GNU timeout under Homebrew's name."""
    monkeypatch.setattr(doctor.shutil, "which", lambda n: "/bin/g" if n == "gtimeout" else None)
    assert doctor.present(tool("timeout", alternates=("gtimeout",)))


def test_the_hint_follows_the_package_manager():
    t = tool(brew="b", apt="a", url="https://example")
    assert doctor.install_command(t, "brew") == "brew install b"
    assert doctor.install_command(t, "apt") == "sudo apt-get install -y a"
    assert doctor.install_command(t, None) is None
    assert doctor.hint(t, None) == "see https://example"
    assert doctor.hint(tool(brew="", apt="", url=""), "brew") == "no package known for this platform"


# --- offer -----------------------------------------------------------------


def test_offer_runs_only_after_a_yes(monkeypatch):
    calls = []
    monkeypatch.setattr(doctor.subprocess, "call", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    out = io.StringIO()
    still = doctor.offer([tool("a"), tool("b")], "brew", "echo", io.StringIO("n\ny\n"), out)
    assert calls == [["echo", "brew", "install", "x"]]
    assert [t.name for t in still] == ["a"]
    assert "Install a (brew install x)? [y/N/?]" in out.getvalue()


def test_a_question_mark_explains_and_asks_again(monkeypatch):
    monkeypatch.setattr(doctor.subprocess, "call", lambda argv: 0)
    out = io.StringIO()
    still = doctor.offer([tool("a")], "brew", "echo", io.StringIO("?\nn\n"), out)
    text = out.getvalue()
    assert "more about a" in text
    assert text.count("Install a (brew install x)?") == 2
    assert [t.name for t in still] == ["a"]


@pytest.mark.parametrize("answer", ["", "\n", "maybe\n"], ids=["end-of-input", "bare-enter", "anything-else"])
def test_anything_but_yes_means_no(monkeypatch, answer):
    """[y/N]: the capital is the default, so Enter must not install."""
    calls = []
    monkeypatch.setattr(doctor.subprocess, "call", lambda argv: calls.append(argv) or 0)
    still = doctor.offer([tool("a")], "brew", "echo", io.StringIO(answer), io.StringIO())
    assert calls == [] and [t.name for t in still] == ["a"]


def test_a_tool_without_a_package_is_not_offered(monkeypatch):
    calls = []
    monkeypatch.setattr(doctor.subprocess, "call", lambda argv: calls.append(argv) or 0)
    out = io.StringIO()
    still = doctor.offer([tool("a", brew="", apt="", url="https://a")], "brew", "echo", io.StringIO("y\n"), out)
    assert calls == [] and [t.name for t in still] == ["a"]
    assert "see https://a" in out.getvalue()


def test_an_installer_that_cannot_run_is_reported_not_raised(monkeypatch):
    def boom(argv):
        raise FileNotFoundError(2, "No such file or directory")
    monkeypatch.setattr(doctor.subprocess, "call", boom)
    out = io.StringIO()
    still = doctor.offer([tool("a")], "brew", "", io.StringIO("y\n"), out)
    assert [t.name for t in still] == ["a"]
    assert "could not run brew: No such file or directory" in out.getvalue()


def test_a_failed_install_is_reported_as_still_missing(monkeypatch):
    monkeypatch.setattr(doctor.subprocess, "call", lambda argv: 1)
    out = io.StringIO()
    still = doctor.offer([tool("a")], "brew", "echo", io.StringIO("y\n"), out)
    assert [t.name for t in still] == ["a"]
    assert "did not succeed (exit 1)" in out.getvalue()


# --- the script end to end -------------------------------------------------


@pytest.fixture
def bare_path(tmp_path):
    """A PATH with python3 and a stand-in brew, so every tool is missing but installable.

    The brew is never run: every test that answers yes passes `--run echo`.
    It only makes the doctor see a package manager, as it would on a Mac.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)
    (bin_dir / "brew").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "brew").chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir)
    env.pop("PYTHONPATH", None)
    return env


def run(env, *args, stdin=""):
    return subprocess.run([sys.executable, str(DOCTOR), *args], input=stdin,
                          capture_output=True, text=True, env=env, cwd=ROOT)


def test_offer_never_prompts_a_pipe(bare_path):
    """CI and scripts get the report alone; a prompt nobody answers would hang them."""
    done = run(bare_path, "--offer", "--run", "/bin/echo", stdin="y\ny\ny\ny\ny\ny\n")
    assert done.returncode == 0
    assert "Install " not in done.stdout and "running:" not in done.stdout
    assert "missing (" in done.stdout and "nothing was installed without a yes" in done.stdout


def test_interactive_reads_answers_and_runs_through_the_prefix(bare_path):
    # install-claude asks about git, then jq, then timeout, in that order.
    done = run(bare_path, "--interactive", "--run", "/bin/echo", "--for", "install-claude", stdin="n\ny\nn\n")
    assert done.returncode == 0, done.stderr   # jq was "installed" (echoed), so the target may go on
    assert "running: /bin/echo brew install jq" in done.stdout
    assert "running: /bin/echo brew install git" not in done.stdout


def test_install_claude_fails_when_jq_is_declined(bare_path):
    done = run(bare_path, "--interactive", "--run", "/bin/echo", "--for", "install-claude", stdin="n\nn\nn\n")
    assert done.returncode == 1
    assert "the hooks need jq; nothing was linked" in done.stderr


def test_all_present_says_so():
    """On a machine with everything (this one, if the suite's own tools are there)."""
    done = run(dict(os.environ), "--for", "install")
    assert done.returncode == 0
    assert ("All present." in done.stdout) or ("missing (" in done.stdout)
    assert "python3" in done.stdout and "[ok]       python3" in done.stdout


def test_make_doctor_is_report_only_from_a_pipe():
    done = subprocess.run(["make", "doctor", "DOCTOR_RUN=echo"], cwd=ROOT, capture_output=True, text=True, input="y\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Required:" in done.stdout and "Install " not in done.stdout
