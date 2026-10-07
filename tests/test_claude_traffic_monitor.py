"""claude-traffic-monitor: nettop parsing, per-flow accounting, attribution.

Everything below the curses layer is pure over its inputs -- nettop lines, a
`ps` table, the session registry, transcript files -- so it is tested here
without nettop, a terminal, or the user's real sessions. The nettop lines are
trimmed from a real `nettop -L 0 -x -n -J bytes_in,bytes_out` capture.
"""
from __future__ import annotations

import json

import pytest

from conftest import load_script

ctm = load_script("claude-traffic-monitor")

HEADER = ",bytes_in,bytes_out,"


def blocks(text: str):
    """Feed `text` (blocks separated by headers) and return completed blocks.

    A trailing header is appended so the last block completes, as the next
    sample's header would complete it in the live stream.
    """
    parser = ctm.NettopParser()
    out = []
    for line in (text.strip() + "\n" + HEADER).splitlines():
        b = parser.feed(line + "\n")
        if b is not None:
            out.append(b)
    return out


# --- parsing ------------------------------------------------------------------


REAL = f"""\
{HEADER}
kernel_task.0,1579448206,424396516,
tcp4 192.168.86.24:54481<->192.168.86.40:445,1579448206,424396516,
com.norton.mes..974,21094507,16646631,
tcp4 *:22<->*:*,,,
2.1.292.70303,298663,343520,
tcp4 192.168.86.24:53563<->160.79.104.10:443,2314,7295,
tcp6 fe80::1%en0.53000<->2607:6bc0::10.443,10,20,
"""


def test_parser_splits_processes_on_the_last_dot():
    (block,) = blocks(REAL)
    assert [(p.name, p.pid) for p in block] == [
        ("kernel_task", 0), ("com.norton.mes.", 974), ("2.1.292", 70303)]


def test_parser_attaches_flows_and_reads_empty_counters_as_zero():
    (block,) = blocks(REAL)
    norton = block[1]
    assert [(f.remote, f.bytes_in, f.bytes_out) for f in norton.flows] == [("*", 0, 0)]
    claude = block[2]
    assert [f.remote for f in claude.flows] == ["160.79.104.10", "2607:6bc0::10"]


def test_parser_emits_a_block_only_when_the_next_header_arrives():
    parser = ctm.NettopParser()
    assert parser.feed(HEADER + "\n") is None  # nothing before the first header
    assert parser.feed("a.1,1,2,\n") is None
    done = parser.feed(HEADER + "\n")
    assert [p.pid for p in done] == [1]


@pytest.mark.parametrize("addr,kind", [
    ("160.79.104.10", "internet"),
    ("2607:6bc0::10", "internet"),
    ("192.168.86.40", "local"),
    ("127.0.0.1", "local"),
    ("::1", "local"),
    ("224.0.0.251", "local"),
    ("fe80::1", "local"),
    ("::ffff:10.0.0.1", "local"),
    ("*", "unknown"),
    ("some.host.name", "internet"),
])
def test_remote_kind(addr, kind):
    assert ctm.remote_kind(addr) == kind


# --- per-flow deltas -------------------------------------------------------------


def deltas(*texts):
    tracker = ctm.FlowTracker()
    return [tracker.update(b) for t in texts for b in blocks(t)]


def test_first_block_is_baseline_and_later_growth_counts():
    first, second = deltas(
        f"{HEADER}\np.5,0,0,\ntcp4 a:1<->8.8.8.8:443,100,1000,",
        f"{HEADER}\np.5,0,0,\ntcp4 a:1<->8.8.8.8:443,150,1300,",
    )
    assert first == []
    assert [(d.d_in, d.d_out) for d in second] == [(50, 300)]


def test_a_flow_first_seen_later_counts_in_full():
    _, second = deltas(
        f"{HEADER}\np.5,0,0,",
        f"{HEADER}\np.5,0,0,\ntcp4 a:2<->8.8.8.8:443,70,700,",
    )
    assert [(d.d_in, d.d_out) for d in second] == [(70, 700)]


def test_a_counter_going_backwards_is_a_new_socket():
    _, second = deltas(
        f"{HEADER}\np.5,0,0,\ntcp4 a:1<->8.8.8.8:443,500,500,",
        f"{HEADER}\np.5,0,0,\ntcp4 a:1<->8.8.8.8:443,40,60,",
    )
    assert [(d.d_in, d.d_out) for d in second] == [(40, 60)]


def test_identical_connection_strings_are_tracked_separately():
    # Two unconnected sockets print the same string; keyed together, the
    # second would be diffed against the first and report 900 - 100.
    _, second = deltas(
        f"{HEADER}\np.5,0,0,\nudp4 *:*<->*:*,100,0,\nudp4 *:*<->*:*,900,0,",
        f"{HEADER}\np.5,0,0,\nudp4 *:*<->*:*,110,0,\nudp4 *:*<->*:*,905,0,",
    )
    assert sorted(d.d_in for d in second) == [5, 10]


# --- attribution --------------------------------------------------------------


CLAUDE, CHILD, OTHER = 100, 200, 300
PS = {CLAUDE: (1, "claude"), CHILD: (CLAUDE, "node"), OTHER: (1, "Dropbox")}
REG = {CLAUDE: {"pid": CLAUDE, "sessionId": "s1", "cwd": "/x/proj", "name": "my session"}}


def sample(*rows):
    """A nettop block: rows of (name, pid, remote, in, out)."""
    lines = [HEADER]
    for name, pid, remote, b_in, b_out in rows:
        lines += [f"{name}.{pid},0,0,", f"tcp4 l:1<->{remote}:443,{b_in},{b_out},"]
    (b,) = blocks("\n".join(lines))
    return b


@pytest.fixture
def mon(tmp_path):
    return ctm.Monitor(sessions_dir=tmp_path / "sessions",
                       projects_dir=tmp_path / "projects", api_ips={"160.79.104.10"})


def feed(mon, *samples, ps=PS, reg=REG):
    for i, b in enumerate(samples):
        mon.ingest(b, ps, reg, now=1000.0 + i)


def test_session_traffic_includes_children_and_splits_api(mon):
    zero = sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 0),
                  ("node", CHILD, "34.1.1.1", 0, 0))
    feed(mon, zero, sample(("2.1.292", CLAUDE, "160.79.104.10", 10, 300),
                           ("node", CHILD, "34.1.1.1", 0, 100)))
    s = mon.sessions[CLAUDE]
    assert (s.traffic.total_in, s.traffic.total_out) == (10, 400)
    assert s.api_bytes == 310
    assert s.children["node"].total_out == 100
    assert s.label == "my session" and s.project == "proj"
    assert mon.claude_total.total == 410 and mon.other_total.total == 0


def test_lan_and_loopback_traffic_is_not_counted(mon):
    feed(mon, sample(("2.1.292", CLAUDE, "192.168.1.5", 0, 0)),
         sample(("2.1.292", CLAUDE, "192.168.1.5", 999, 999)))
    assert mon.sessions[CLAUDE].traffic.total == 0
    assert mon.claude_total.total == 0


def test_non_claude_traffic_goes_to_others_under_the_ps_name(mon):
    feed(mon, sample(("Dropbox.trunc", OTHER, "8.8.8.8", 0, 0)),
         sample(("Dropbox.trunc", OTHER, "8.8.8.8", 5, 50)))
    assert mon.others["Dropbox"].total == 55
    assert mon.other_total.total == 55


def test_a_child_that_exits_stays_attributed(mon):
    feed(mon, sample(("node", CHILD, "34.1.1.1", 0, 0)))
    gone = {k: v for k, v in PS.items() if k != CHILD}
    mon.ingest(sample(("node", CHILD, "34.1.1.1", 0, 70)), gone, REG, now=1001.0)
    assert mon.sessions[CLAUDE].traffic.total_out == 70
    assert mon.other_total.total == 0


def test_a_session_whose_process_exits_is_kept_as_ended(mon):
    feed(mon, sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 0)))
    mon.ingest(sample(), {OTHER: PS[OTHER]}, REG, now=1001.0)
    assert mon.sessions[CLAUDE].alive is False


def test_an_unregistered_claude_process_still_gets_a_row(mon):
    feed(mon, sample(("2.1.300", 555, "160.79.104.10", 0, 0)),
         sample(("2.1.300", 555, "160.79.104.10", 0, 40)), reg={})
    assert mon.sessions[555].label == "(unregistered claude)"
    assert mon.sessions[555].traffic.total_out == 40


def test_rates_are_per_second_of_the_last_interval(mon):
    mon.ingest(sample(("Dropbox", OTHER, "8.8.8.8", 0, 0)), PS, REG, now=1000.0)
    mon.ingest(sample(("Dropbox", OTHER, "8.8.8.8", 0, 400)), PS, REG, now=1002.0)
    assert mon.other_total.rate_out == 200


# --- transcripts --------------------------------------------------------------


def entry(type_, content=None, **extra):
    obj = {"type": type_, **extra}
    if content is not None:
        obj["message"] = {"role": type_, "content": content}
    return json.dumps(obj) + "\n"


IMAGE = {"type": "image", "source": {"type": "base64", "data": "A" * 1000}}


def test_watcher_tracks_images_until_compaction(tmp_path):
    path = tmp_path / "s.jsonl"
    tool_result = {"type": "tool_result", "content": [IMAGE]}
    path.write_text(entry("user", [IMAGE]) + entry("user", [tool_result]))
    w = ctm.TranscriptWatcher(path)
    w.poll()
    assert w.images == [1000, 1000]
    with path.open("a") as f:
        f.write(entry("system", subtype="compact_boundary"))
    w.poll()
    assert w.images == []


def test_watcher_ignores_sidechains_and_waits_for_whole_lines(tmp_path):
    path = tmp_path / "s.jsonl"
    whole = entry("user", [IMAGE], isSidechain=True)
    partial = entry("user", [IMAGE])
    path.write_text(whole + partial[:20])
    w = ctm.TranscriptWatcher(path)
    w.poll()
    assert w.images == []
    with path.open("a") as f:
        f.write(partial[20:])
    w.poll()
    assert w.images == [1000]


def test_watcher_reads_context_size_and_prefers_the_custom_title(tmp_path):
    path = tmp_path / "s.jsonl"
    usage = {"input_tokens": 5, "cache_creation_input_tokens": 100,
             "cache_read_input_tokens": 9000}
    assistant = json.dumps({"type": "assistant", "message": {"usage": usage}}) + "\n"
    path.write_text(
        json.dumps({"type": "custom-title", "customTitle": "mine"}) + "\n"
        + json.dumps({"type": "ai-title", "aiTitle": "auto"}) + "\n"
        + assistant)
    w = ctm.TranscriptWatcher(path)
    w.poll()
    assert w.context_tokens == 9105
    assert w.title == "mine"


def test_monitor_follows_a_sessions_transcript(tmp_path, mon):
    proj = tmp_path / "projects" / "-x-proj"
    proj.mkdir(parents=True)
    (proj / "s1.jsonl").write_text(entry("user", [IMAGE]))
    feed(mon, sample())
    assert mon.sessions[CLAUDE].watcher.images == [1000]


# --- rendering and CLI ----------------------------------------------------------


@pytest.mark.parametrize("n,text", [
    (0, "0 B"), (999, "999 B"), (1500, "1.5 KB"), (2_340_000, "2.3 MB"),
    (5e9, "5.0 GB"),
])
def test_human(n, text):
    assert ctm.human(n) == text


def test_render_shows_sessions_children_and_others(mon):
    zero = sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 0),
                  ("node", CHILD, "34.1.1.1", 0, 0), ("Dropbox", OTHER, "8.8.8.8", 0, 0))
    feed(mon, zero, sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 3000),
                           ("node", CHILD, "34.1.1.1", 0, 1000),
                           ("Dropbox", OTHER, "8.8.8.8", 0, 2000)))
    text = "\n".join(t for t, _ in ctm.render(mon, ctm.InterfaceMeter(), 1010.0, top=5))
    assert "my session" in text and "└ node" in text and "Dropbox" in text
    session_row = next(t for t, _ in ctm.render(mon, ctm.InterfaceMeter(), 1010.0, 5)
                       if t.startswith("my session"))
    assert "4.0 KB" in session_row and " 75 " in session_row  # API share 3000/4000


def test_interval_below_one_is_refused():
    with pytest.raises(SystemExit) as excinfo:
        ctm.main(["--interval", "0"])
    assert "interval" in str(excinfo.value.code)


def test_refuses_to_run_without_a_terminal(monkeypatch):
    monkeypatch.setattr(ctm.sys.stdout, "isatty", lambda: False)
    with pytest.raises(SystemExit) as excinfo:
        ctm.main([])
    assert "terminal" in str(excinfo.value.code)
