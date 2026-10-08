"""Staged inputs for the two screenshots that cannot show this machine.

Every other image in docs/img is a real command run against this repo's own
data. These two would show the whole machine instead: `bd-verify-backup -g`
lists every beads repo on it, client names included, and
`claude-traffic-monitor` lists every running Claude session's title and
project plus every other process on the network. So each one gets made-up
input, fed through the real code:

- `stage_backup_repos()` builds a fake HOME of throwaway beads repos (real
  `git`, real `bd init`, real `bd dolt push` to local bare remotes), and the
  real `bd-verify-backup -g` runs against it.
- `traffic_monitor_screen()` feeds synthetic nettop blocks, a process table,
  a session registry and transcripts through the monitor's own `ingest()`,
  and draws the screen with its own `render()`. Only the curses layer is
  skipped, since it needs a terminal.

Both images are reproducible byte for byte: one fixed clock, no randomness,
and nothing in the backup table depends on when it ran. The backup shot needs
`bd` and `dolt` on PATH.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- bd-verify-backup -g -----------------------------------------------------

# (org/repo, what to leave unbacked-up). Each state is one the table reports.
BACKUP_REPOS = [
    ("acme/web-app", None),
    ("acme/billing-api", "uncommitted"),
    ("acme/mobile-app", "unpushed-branch"),
    ("acme/data-pipeline", None),
    ("personal/blog", "unpushed-beads"),
    ("personal/dotfiles", "stash"),
    ("personal/recipes", None),
]


def backup_env(home: Path) -> dict[str, str]:
    """The environment for every process the backup shot runs.

    HOME is what `-g` searches, and XDG_CONFIG_HOME and the git variables keep
    the real user's git config (signing, hooks, default branch) out of it.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "BD_", "BEADS_"))}
    env.update({
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com",
        "GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com",
        "BD_NON_INTERACTIVE": "1",
    })
    return env


def stage_backup_repos(root: Path) -> dict[str, str]:
    """Build the fake HOME under `root`; return the env to run the shot in."""
    # Resolved, because bd-verify-backup shows a repo as ~/... only when its
    # resolved path starts with HOME, and macOS's temp dir is under the
    # /var -> /private/var symlink: unresolved, every row showed the full path.
    root = root.resolve()
    home, remotes = root / "home", root / "remotes"
    env = backup_env(home)

    def run(cwd: Path, *cmd: str) -> None:
        subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True)

    for name, gap in BACKUP_REPOS:
        work, remote = home / "Documents" / name, remotes / f"{Path(name).name}.git"
        work.mkdir(parents=True)
        remote.parent.mkdir(parents=True, exist_ok=True)
        run(root, "git", "init", "-q", "--bare", "-b", "main", str(remote))
        run(work, "git", "init", "-q", "-b", "main")
        (work / "README.md").write_text(f"# {Path(name).name}\n")
        run(work, "git", "add", ".")
        run(work, "git", "commit", "-q", "-m", "Initial commit")
        run(work, "git", "remote", "add", "origin", str(remote))
        run(work, "git", "push", "-q", "-u", "origin", "main")
        # --stealth keeps bd's files out of git, so the tree stays clean.
        run(work, "bd", "init", "--stealth", "--non-interactive", "-p", Path(name).name)
        run(work, "bd", "create", "Write the README", "-q")
        run(work, "bd", "dolt", "remote", "add", "origin", f"git+file://{remote}")
        run(work, "bd", "dolt", "push")
        if gap == "uncommitted":
            (work / "README.md").write_text("# billing-api\n\nDraft.\n")
            (work / "notes.txt").write_text("todo\n")
        elif gap == "unpushed-branch":
            run(work, "git", "checkout", "-q", "-b", "feature/login")
            (work / "login.txt").write_text("wip\n")
            run(work, "git", "add", ".")
            run(work, "git", "commit", "-q", "-m", "Start the login screen")
            run(work, "git", "checkout", "-q", "main")
        elif gap == "unpushed-beads":
            run(work, "bd", "create", "Draft the October post", "-q")
        elif gap == "stash":
            (work / "README.md").write_text("# dotfiles\n\nexperiment\n")
            run(work, "git", "stash", "-q")
    return env


# --- claude-traffic-monitor --------------------------------------------------

T0 = 1_791_460_800.0      # 2026-10-08 10:00 UTC; any fixed instant would do
DURATION = 1260           # 21 minutes, so the 15-minute rates are full
API = "160.79.104.10"     # one of the monitor's fallback API addresses
LOCAL = "192.168.1.20"

# pid: (ppid, ps name). The sessions are children of a shell (pid 100).
PS = {
    100: (1, "zsh"),
    201: (100, "claude"), 202: (100, "claude"), 203: (100, "claude"),
    204: (100, "claude"),
    311: (201, "node"), 312: (201, "gh"), 321: (202, "uv"),
    401: (1, "Google Chrome Helper"), 402: (1, "Slack Helper"),
    403: (1, "Dropbox"), 404: (1, "Spotify"), 405: (1, "Mail"),
    406: (1, "softwareupdated"), 407: (1, "zoom.us"),
}
# nettop's own name for a process: 15 characters, and Claude as its version.
NETTOP_NAME = {pid: "2.1.292" if name == "claude" else name[:15] for pid, (_, name) in PS.items()}

# pid: (session id, project dir, title, context tokens, image bytes,
#       seconds between requests, seconds the session ends at or None)
SESSIONS = {
    201: ("5f0c6a2e-1111-4a6b-9c1e-0a1b2c3d4e01", "web-app", "Activity feed pager",
          148_000, 0, 41, None),
    202: ("5f0c6a2e-2222-4a6b-9c1e-0a1b2c3d4e02", "pipeline", "Speed up nightly import",
          61_000, 0, 23, None),
    203: ("5f0c6a2e-3333-4a6b-9c1e-0a1b2c3d4e03", "mobile-app", "Login screen layout",
          92_000, 410_000, 67, None),
    204: ("5f0c6a2e-4444-4a6b-9c1e-0a1b2c3d4e04", "blog", "Draft the October post",
          38_000, 0, 55, 700),
}

# Other processes: pid -> (remote, steady down B/s, steady up B/s, burst every
# N s or 0, burst bytes down).
OTHERS = {
    401: ("142.250.74.110", 5_200, 900, 37, 2_400_000),
    402: ("54.230.10.15", 1_100, 300, 0, 0),
    403: ("162.125.19.131", 300, 14_000, 0, 0),
    404: ("35.186.224.25", 40_000, 400, 0, 0),
    405: ("17.42.251.41", 150, 60, 300, 1_800_000),
    406: ("17.253.13.203", 0, 0, 450, 64_000_000),
    407: ("170.114.52.2", 0, 0, 0, 0),
}
CHILDREN = {  # pid -> (remote, every N s, bytes down per burst)
    311: ("104.16.24.34", 90, 3_600_000),
    312: ("140.82.112.6", 130, 180_000),
    321: ("151.101.0.223", 300, 26_000_000),
}


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def _request_times(every: int, end: int | None, phase: int) -> list[int]:
    stop = DURATION if end is None else end
    return list(range(phase, stop, every))


def _write_transcripts(projects: Path) -> None:
    """One transcript per session: its title, its requests, any image."""
    for i, (pid, (sid, project, title, ctx, image, every, end)) in enumerate(SESSIONS.items()):
        lines = [{"type": "custom-title", "customTitle": title, "sessionId": sid}]
        if image:
            data = "A" * image  # only the length is read
            lines.append({"type": "user", "timestamp": _iso(T0 + 5), "message": {
                "role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "data": data}}]}})
        for n, t in enumerate(_request_times(every, end, 3 + 7 * i)):
            lines.append({"type": "assistant", "timestamp": _iso(T0 + t), "message": {
                "id": f"msg_{pid}_{n}", "role": "assistant",
                "usage": {"input_tokens": 2, "cache_creation_input_tokens": 900,
                          "cache_read_input_tokens": ctx - 902}}})
        d = projects / f"-demo-{project}"
        d.mkdir(parents=True)
        (d / f"{sid}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))


def _traffic(t: int) -> dict[tuple[int, str], tuple[int, int]]:
    """Bytes (down, up) moved in second `t`, keyed by (pid, remote)."""
    moved: dict[tuple[int, str], tuple[int, int]] = {}

    def add(pid: int, remote: str, down: int, up: int) -> None:
        d, u = moved.get((pid, remote), (0, 0))
        moved[(pid, remote)] = (d + down, u + up)

    for i, (pid, (_, _, _, ctx, image, every, end)) in enumerate(SESSIONS.items()):
        if end is not None and t >= end:
            continue
        add(pid, "34.149.66.137", 40, 25)  # telemetry and update checks
        times = _request_times(every, end, 3 + 7 * i)
        for start in times:
            if start == t:  # the upload: the whole context, and any image
                add(pid, API, 1_800, int(ctx * 0.72 + image * 0.75))
            elif 0 < t - start <= 8:  # the reply streams back
                add(pid, API, 2_600, 120)
    for pid, (remote, down, up, every, burst) in OTHERS.items():
        wobble = 1 + (t * 7 + pid) % 5 / 10
        if pid == 407:  # a call that started a few minutes before the end
            if t > DURATION - 240:
                add(pid, remote, 190_000, 160_000)
            continue
        add(pid, remote, int(down * wobble), int(up * wobble))
        if every and t % every == every // 2:
            add(pid, remote, burst, burst // 40)
    for pid, (remote, every, burst) in CHILDREN.items():
        if t % every == every // 3:
            add(pid, remote, burst, burst // 50)
    return moved


def _blocks():
    """One nettop block per second, as the parser builds them from nettop."""
    ctm = load_monitor()
    totals: dict[tuple[int, str], list[int]] = {}
    for t in range(DURATION + 1):
        for key, (down, up) in _traffic(t).items():
            acc = totals.setdefault(key, [0, 0])
            acc[0] += down
            acc[1] += up
        ended = {pid for pid, s in SESSIONS.items() if s[6] is not None and t >= s[6]}
        block = []
        for pid in sorted({p for p, _ in totals} - ended):
            flows = [ctm.Flow(f"tcp4 {LOCAL}:{50000 + n}<->{remote}:443", remote,
                              *totals[(pid, remote)], LOCAL, str(50000 + n), "443")
                     for n, remote in enumerate(sorted(r for p, r in totals if p == pid))]
            block.append(ctm.ProcSample(
                NETTOP_NAME[pid], pid, flows,
                sum(f.bytes_in for f in flows), sum(f.bytes_out for f in flows)))
        yield t, block, ended


def load_monitor():
    """claude-traffic-monitor as a module (it has no .py, so import by path)."""
    if "ctm" not in sys.modules:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))  # its own `import claudeutils`
        loader = SourceFileLoader("ctm", str(REPO / "claude-traffic-monitor"))
        mod = module_from_spec(spec_from_loader("ctm", loader))
        sys.modules["ctm"] = mod  # before exec: @dataclass looks itself up there
        loader.exec_module(mod)
    return sys.modules["ctm"]


ANSI = {"": "", "bold": "\x1b[1m", "dim": "\x1b[2m", "status": "\x1b[7m"}


def traffic_monitor_screen(root: Path) -> str:
    """The monitor's screen after DURATION seconds of staged traffic, as ANSI."""
    ctm = load_monitor()
    projects, sessions = root / "projects", root / "sessions"
    _write_transcripts(projects)
    mon = ctm.Monitor(sessions_dir=sessions, projects_dir=projects, api_ips={API})
    mon.started = mon.counting_since = T0
    for t, block, ended in _blocks():
        ps = {pid: v for pid, v in PS.items() if pid not in ended}
        registry = {pid: {"pid": pid, "sessionId": s[0], "cwd": f"/demo/{s[1]}"}
                    for pid, s in SESSIONS.items()}
        mon.ingest(block, ps, registry, T0 + t)
    meter = ctm.InterfaceMeter()
    meter.iface = "en0"
    # The raw interface count includes LAN traffic, so it reads a bit higher.
    meter.since = (int((mon.claude_total.total_in + mon.other_total.total_in) * 1.04),
                   int((mon.claude_total.total_out + mon.other_total.total_out) * 1.03))
    now = T0 + DURATION + 0.4
    lines = ctm.render(mon, meter, now, top=8) + [("", "")] + ctm.status_lines(ctm.View())
    width = max(len(text) for text, _ in lines) + 1
    out = []
    for text, style in lines:
        if style == "status":
            text = text.ljust(width)  # a full-width bar, as draw() paints it
        out.append(f"{ANSI[style]}{text}\x1b[0m" if style and text else text)
    return "\n".join(out)
