"""claude-traffic-monitor: nettop parsing, per-flow accounting, attribution.

Everything below the curses layer is pure over its inputs -- nettop lines, a
`ps` table, the session registry, transcript files -- so it is tested here
without nettop, a terminal, or the user's real sessions. The nettop lines are
trimmed from a real `nettop -L 0 -x -n -J bytes_in,bytes_out` capture.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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


def test_a_comma_in_a_process_name_does_not_misattach_its_flows():
    """Splitting from the left cut 'Foo, Inc.42' at its comma, failed the pid
    check, and dropped the process line, so its flows were appended to the
    *previous* process, which could be a Claude session."""
    (block,) = blocks(f"""{HEADER}
2.1.292.100,0,0,
tcp4 a:1<->160.79.104.10:443,1,1,
Foo, Inc.42,0,0,
tcp4 a:2<->8.8.8.8:443,5,5,
""")
    assert [(p.name, p.pid, len(p.flows)) for p in block] == [
        ("2.1.292", 100, 1), ("Foo, Inc", 42, 1)]


def test_reader_signals_the_end_even_when_the_stream_breaks():
    """A strict UTF-8 decode error once killed the reader thread without
    sending the end marker, so the screen froze on stale numbers silently."""
    import queue

    class Broken:
        def __iter__(self):
            yield HEADER + "\n"
            raise UnicodeDecodeError("utf-8", b"\xc3", 0, 1, "truncated name")

    class Proc:
        stdout = Broken()

    out = queue.Queue()
    with pytest.raises(UnicodeDecodeError):
        ctm.reader(Proc(), out)
    assert out.get_nowait() is None


@pytest.mark.parametrize("addr,kind", [
    ("160.79.104.10", "internet"),
    ("2607:6bc0::10", "internet"),
    ("192.168.86.40", "local"),
    ("127.0.0.1", "local"),
    ("::1", "local"),
    ("224.0.0.251", "local"),
    ("fe80::1", "local"),
    ("::ffff:10.0.0.1", "local"),
    ("100.101.102.103", "local"),  # Tailscale: metered as its outer flow
    ("100.128.0.1", "internet"),
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


def test_a_recycled_child_pid_is_not_credited_to_the_session(mon):
    """macOS recycles pids. The owner cache once trusted a pid forever, so an
    unrelated process inheriting a dead MCP child's pid billed its traffic to
    the Claude session -- inflating exactly the number the tool exists for."""
    feed(mon, sample(("node", CHILD, "34.1.1.1", 0, 0)))
    gone = {k: v for k, v in PS.items() if k != CHILD}
    mon.ingest(sample(), gone, REG, now=1001.0)
    reborn = {**gone, CHILD: (1, "Dropbox")}
    mon.ingest(sample(("Dropbox", CHILD, "8.8.8.8", 0, 90)), reborn, REG, now=1002.0)
    assert mon.sessions[CLAUDE].traffic.total == 0
    assert mon.others["Dropbox"].total_out == 90


def test_a_recycled_session_pid_is_not_credited_to_the_ended_session(mon):
    """An ended session stays on screen, so its pid stays in `sessions`; a
    process later given that pid must not be walked into the dead row."""
    feed(mon, sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 0)))
    mon.ingest(sample(), {OTHER: PS[OTHER]}, {}, now=1001.0)
    reborn = {OTHER: PS[OTHER], CLAUDE: (1, "curl")}
    mon.ingest(sample(("curl", CLAUDE, "8.8.8.8", 0, 30)), reborn, {}, now=1002.0)
    assert mon.sessions[CLAUDE].traffic.total == 0
    assert mon.others["curl"].total_out == 30


def test_a_session_whose_process_exits_is_kept_as_ended(mon):
    feed(mon, sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 0)))
    mon.ingest(sample(), {OTHER: PS[OTHER]}, REG, now=1001.0)
    assert mon.sessions[CLAUDE].alive is False


def test_an_unregistered_claude_process_still_gets_a_row(mon):
    feed(mon, sample(("2.1.300", 555, "160.79.104.10", 0, 0)),
         sample(("2.1.300", 555, "160.79.104.10", 0, 40)),
         ps={**PS, 555: (1, "claude")}, reg={})
    assert mon.sessions[555].label == "(unregistered claude)"
    assert mon.sessions[555].traffic.total_out == 40


def test_peak_is_the_busiest_tick_per_second(mon):
    mon.ingest(sample(("Dropbox", OTHER, "8.8.8.8", 0, 0)), PS, REG, now=1000.0)
    mon.ingest(sample(("Dropbox", OTHER, "8.8.8.8", 0, 400)), PS, REG, now=1002.0)
    assert mon.other_total.peak(1002.0) == (0, 200)  # 400 bytes over a 2 s tick


# --- rolling rates ------------------------------------------------------------


def ticks(*rows):
    """A Counter fed (now, seconds, out_bytes) ticks."""
    c = ctm.Counter()
    for now, seconds, out in rows:
        c.add(0, out)
        c.close_tick(now, seconds)
    return c


def test_each_tier_averages_only_its_own_window():
    c = ticks((100.0, 1, 6000), (190.0, 1, 600), (199.0, 1, 50))
    now, span = 200.0, 1000.0
    assert c.rate(5, now, span)[1] == 50 / 5
    assert c.rate(60, now, span)[1] == 650 / 60
    assert c.rate(900, now, span)[1] == 6650 / 900


def test_a_young_monitor_divides_by_time_counted_not_the_full_window():
    """Dividing by 900 s after 10 s of counting would show a 15-minute rate
    90x too low, and the tier would read as near zero for its first minutes."""
    c = ticks((10.0, 1, 1000))
    assert c.rate(900, 10.0, span=10.0)[1] == 100


def test_peak_survives_after_the_short_average_has_dropped():
    """The point of the peak: one request's burst stays visible for a minute."""
    c = ticks((100.0, 1, 900_000))
    assert c.rate(5, 130.0, 1000.0)[1] == 0
    assert c.peak(130.0)[1] == 900_000
    assert c.peak(161.0)[1] == 0  # older than PEAK_WINDOW


def test_old_ticks_are_dropped():
    c = ticks((0.0, 1, 10), (1000.0, 1, 20))
    assert [t[0] for t in c._ticks] == [1000.0]


def test_idle_ticks_are_not_stored():
    """Most counters are idle most of the time; storing their empty ticks
    would keep 900 entries apiece for nothing."""
    c = ticks((0.0, 1, 10), (5.0, 1, 0))
    assert [t[0] for t in c._ticks] == [0.0]


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


def assistant(msg_id, ctx, ts="2026-10-07T12:00:00Z"):
    usage = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": ctx}
    return json.dumps({"type": "assistant", "timestamp": ts,
                       "message": {"id": msg_id, "usage": usage}}) + "\n"


def test_watcher_counts_each_request_once_and_only_after_since(tmp_path):
    """A response written as several entries repeats its usage; counting each
    would multiply the tokens and push the measured bytes/token down."""
    since = ctm._epoch("2026-10-07T12:00:00Z")
    path = tmp_path / "s.jsonl"
    path.write_text(assistant("old", 999, ts="2026-10-07T11:59:59Z")
                    + entry("user", [IMAGE])
                    + assistant("m1", 100) + assistant("m1", 100) + assistant("m2", 300))
    w = ctm.TranscriptWatcher(path, since)
    w.poll()
    assert (w.requests, w.sent_tokens, w.sent_image_bytes) == (2, 400, 2000)


def test_next_request_estimate_combines_context_and_images(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(entry("user", [IMAGE]) + assistant("m1", 10_000))
    w = ctm.TranscriptWatcher(path)
    w.poll()
    expected = 10_000 * ctm.BYTES_PER_TOKEN + 1000 * ctm.IMAGE_GZIP_RATIO
    assert w.next_request_bytes() == pytest.approx(expected)


def test_measured_ratio_is_api_upload_over_tokens(mon):
    w = ctm.TranscriptWatcher(Path("/nonexistent"))
    w.requests, w.sent_tokens = 2, 1000
    mon.sessions[CLAUDE] = ctm.Session(CLAUDE, api_out=1300, watcher=w)
    assert mon.measured_bytes_per_token() == (1.3, 2)


def test_measured_ratio_skips_sessions_that_sent_images(mon):
    """Image bytes dwarf token bytes; estimating and subtracting them made
    the ratio read 5.01 where the transcripts implied about 1.2."""
    plain = ctm.TranscriptWatcher(Path("/nonexistent"))
    plain.requests, plain.sent_tokens = 1, 1000
    pics = ctm.TranscriptWatcher(Path("/nonexistent"))
    pics.requests, pics.sent_tokens, pics.sent_image_bytes = 3, 1000, 19_000_000
    mon.sessions[CLAUDE] = ctm.Session(CLAUDE, api_out=900, watcher=plain)
    mon.sessions[555] = ctm.Session(555, api_out=15_000_000, watcher=pics)
    assert mon.measured_bytes_per_token() == (0.9, 1)


def test_measured_ratio_ignores_upload_from_sessions_without_a_transcript(mon):
    """An unregistered `claude -p` uploads but records no tokens we can see;
    counting its bytes would inflate the ratio the footer offers as the
    correction for BYTES_PER_TOKEN."""
    w = ctm.TranscriptWatcher(Path("/nonexistent"))
    w.requests, w.sent_tokens = 1, 1000
    mon.sessions[CLAUDE] = ctm.Session(CLAUDE, api_out=700, watcher=w)
    mon.sessions[555] = ctm.Session(555, label=ctm.UNREGISTERED, api_out=50_000)
    assert mon.measured_bytes_per_token()[0] == pytest.approx(0.7)


def test_monitor_follows_a_sessions_transcript(tmp_path, mon):
    proj = tmp_path / "projects" / "-x-proj"
    proj.mkdir(parents=True)
    (proj / "s1.jsonl").write_text(entry("user", [IMAGE]))
    feed(mon, sample())
    assert mon.sessions[CLAUDE].watcher.images == [1000]


# --- unconnected UDP and tunnels --------------------------------------------------


@pytest.mark.parametrize("conn,expected", [
    ("tcp4 192.168.86.24:53563<->160.79.104.10:443", ("192.168.86.24", "53563", "160.79.104.10", "443")),
    ("tcp6 fe80::1%en0.53000<->2607:6bc0::10.443", ("fe80::1", "53000", "2607:6bc0::10", "443")),
    ("udp4 *:41641<->*:*", ("*", "41641", "*", "*")),
    ("udp6 *.5353<->*.*", ("*", "5353", "*", "*")),
])
def test_endpoints(conn, expected):
    assert ctm.endpoints(conn) == expected


@pytest.mark.parametrize("conn,kind", [
    ("udp4 *:41641<->*:*", "internet"),   # Tailscale's WireGuard socket
    ("udp4 *:5353<->*:*", "unknown"),     # mDNS never leaves the LAN
    ("udp6 *.67<->*.*", "unknown"),       # DHCP
    ("tcp4 *:22<->*:*", "unknown"),       # a listener carries no bytes
])
def test_unconnected_udp_counts_unless_its_port_is_lan_only(conn, kind):
    _, lport, remote, _ = ctm.endpoints(conn)
    assert ctm.flow_kind(conn, remote, lport) == kind


def test_tailscale_wireguard_traffic_is_counted(mon):
    """Live capture, 2026-10-07: Tailscale's tunnel runs over an unconnected
    UDP socket. Treated as 'unknown', and with the inner 100.x flow local,
    traffic to a Tailscale peer was counted zero times."""
    def tick(n):
        (b,) = blocks(f"{HEADER}\nio.tailscale.ip.700,0,0,\nudp4 *:41641<->*:*,{n},{n},")
        return b
    ps = {**PS, 700: (1, "io.tailscale.ipn.macsys.network-extension")}
    feed(mon, tick(0), tick(500), ps=ps)
    assert mon.other_total.total == 1000


IFCONFIG = """\
en7: flags=8963<UP,BROADCAST,SMART,RUNNING> mtu 1500
\tinet 192.168.86.24 netmask 0xffffff00 broadcast 192.168.86.255
utun6: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1280
\tinet 100.75.6.123 --> 100.75.6.123 netmask 0xffffffff
\tinet6 fd7a:115c:a1e0::d139:67b prefixlen 48
\tinet6 fe80::1%utun6 prefixlen 64 scopeid 0x13
bridge100: flags=8a63<UP,BROADCAST> mtu 1500
\tinet 192.168.64.1 netmask 0xffffff00
"""


def test_tunnel_addresses_come_only_from_tunnel_interfaces():
    assert ctm.tunnel_addresses(IFCONFIG) == {
        "100.75.6.123", "fd7a:115c:a1e0::d139:67b", "fe80::1"}


def test_traffic_sent_from_a_tunnel_address_is_reported_as_counted_twice(mon):
    mon.tunnel_ips = {"100.75.6.123"}
    def tick(n):
        (b,) = blocks(f"{HEADER}\n2.1.292.{CLAUDE},0,0,\n"
                      f"tcp4 100.75.6.123:5000<->160.79.104.10:443,0,{n},\n"
                      f"tcp4 192.168.86.24:5001<->160.79.104.10:443,0,{n},")
        return b
    feed(mon, tick(0), tick(300))
    assert mon.sessions[CLAUDE].traffic.total_out == 600  # still credited to its app
    assert mon.tunnelled.total_out == 300                 # only the tunnel-side flow
    note = [t for t in screen(mon) if t.startswith("Tunnelled")]
    assert len(note) == 1 and "sent twice" in note[0]
    # The note is about every row, so it survives hiding the other processes.
    assert any(t.startswith("Tunnelled") for t in screen(mon, ctm.View(others=False)))


def test_no_tunnel_note_without_tunnelled_traffic(mon):
    busy(mon)
    assert not any(t.startswith("Tunnelled") for t in screen(mon))
    assert not any(t.startswith("Tunnelled") for t in screen(mon, ctm.View(others=False)))


# --- rendering and CLI ----------------------------------------------------------


@pytest.mark.parametrize("n,text", [
    (0, "0"), (0.4, "0"), (7, "7"), (999, "999"), (1500, "1.5K"),
    (15_000, "15K"), (999_000, "999K"), (2_340_000, "2.3M"), (5e9, "5.0G"),
])
def test_short_fits_five_characters(n, text):
    assert ctm.short(n) == text
    assert len(ctm.short(n)) <= ctm.RATE_W


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


# --- keys and view --------------------------------------------------------------


def screen(mon, view=None, now=1010.0):
    return [t for t, _ in ctm.render(mon, ctm.InterfaceMeter(), now, 5, view)]


def busy(mon):
    """A session with a child, and two other processes of different weight."""
    zero = sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 0), ("node", CHILD, "34.1.1.1", 0, 0),
                  ("Dropbox", OTHER, "8.8.8.8", 0, 0), ("Zoom", 400, "9.9.9.9", 0, 0))
    ps = {**PS, 400: (1, "Zoom")}
    feed(mon, zero, sample(("2.1.292", CLAUDE, "160.79.104.10", 0, 3000),
                           ("node", CHILD, "34.1.1.1", 0, 1000),
                           ("Dropbox", OTHER, "8.8.8.8", 0, 100),
                           ("Zoom", 400, "9.9.9.9", 0, 5000)), ps=ps)


def test_s_cycles_the_sort_through_every_order():
    view = ctm.View()
    seen = [view.sort]
    for _ in ctm.SORTS:
        assert ctm.handle_key(view, "s") == "redraw"
        seen.append(view.sort)
    assert seen == ["total", "rate", "name", "total"]


@pytest.mark.parametrize("key,action", [("q", "quit"), ("Q", "quit"), ("r", "reset"), ("x", None)])
def test_keys_that_the_loop_acts_on(key, action):
    assert ctm.handle_key(ctm.View(), key) == action


@pytest.mark.parametrize("key,attr", [("c", "children"), ("o", "others"),
                                      ("p", "paused"), ("?", "help")])
def test_toggle_keys_flip_their_setting_and_back(key, attr):
    view = ctm.View()
    before = getattr(view, attr)
    ctm.handle_key(view, key)
    assert getattr(view, attr) is not before
    ctm.handle_key(view, key)
    assert getattr(view, attr) is before


def test_sorting_by_name_reorders_other_processes(mon):
    busy(mon)
    by_total = [t.split()[0] for t in screen(mon) if t.startswith(("Dropbox", "Zoom"))]
    by_name = [t.split()[0] for t in screen(mon, ctm.View(sort="name"))
               if t.startswith(("Dropbox", "Zoom"))]
    assert by_total == ["Zoom", "Dropbox"] and by_name == ["Dropbox", "Zoom"]


def test_hiding_children_keeps_their_bytes_in_the_session_row(mon):
    busy(mon)
    rows = screen(mon, ctm.View(children=False))
    assert not any("└ node" in t for t in rows)
    session = next(t for t in rows if t.startswith("my session"))
    assert "4.0 KB" in session  # 3000 own + 1000 from the hidden child


def test_hiding_others_collapses_them_to_one_aligned_row(mon):
    """The first version kept the section header and an "… and N more" line,
    which read as leftover text in a mode meant to remove the section."""
    busy(mon)
    rows = screen(mon, ctm.View(others=False))
    assert not any(t.startswith(("Dropbox", "Zoom", "OTHER PROCESSES", "Everything else"))
                   for t in rows)
    assert not any("more" in t for t in rows)
    (row,) = [t for t in rows if t.startswith("Other processes")]
    assert "2 hidden" in row and "5.1 KB" in row  # 5000 + 100 bytes up
    claude = next(t for t in rows if t.startswith("Claude total"))
    assert row.index("5.1 KB") + len("5.1 KB") == claude.index("4.0 KB") + len("4.0 KB")


def test_status_line_shows_the_state_and_how_to_get_help():
    (status,) = ctm.status_lines(ctm.View(sort="rate", children=False, paused=True))
    text, style = status
    assert style == "status"
    for part in ("sort: rate", "children: hidden", "others: shown", "PAUSED", "? keys", "q quit"):
        assert part in text


def test_status_line_does_not_shift_when_a_mode_changes():
    """'total' is longer than 'rate', and 'hidden' than 'shown': unpadded,
    each keypress slid the rest of the bar by a character."""
    def hint_column(view):
        (text, _), = ctm.status_lines(view)
        return text.index("? keys")
    base = hint_column(ctm.View())
    for view in (ctm.View(sort="rate"), ctm.View(sort="name"),
                 ctm.View(children=False), ctm.View(others=False), ctm.View(paused=True)):
        assert hint_column(view) == base


def test_help_adds_the_key_list_above_the_status_line():
    help_line, status = ctm.status_lines(ctm.View(help=True))
    assert help_line == (ctm.KEY_HELP, "dim")
    assert "? hides keys" in status[0]


def test_the_title_no_longer_carries_state(mon):
    assert "sort:" not in screen(mon, ctm.View(paused=True))[0]


def test_reset_zeroes_counts_and_drops_ended_sessions(mon):
    busy(mon)
    mon.sessions[999] = ctm.Session(999, alive=False)
    w = ctm.TranscriptWatcher(Path("/nonexistent"))
    w.requests, w.sent_tokens = 4, 800
    mon.sessions[CLAUDE].watcher = w
    mon.reset(2000.0)
    s = mon.sessions[CLAUDE]
    assert (w.requests, w.sent_tokens, w.since) == (0, 0, 2000.0)
    assert 999 not in mon.sessions
    assert (s.traffic.total, s.api_bytes, s.children, mon.others) == (0, 0, {}, {})
    assert mon.claude_total.total == 0
    assert mon.first_block == mon.last_block  # rates span from the last block seen
    assert mon.counting_since == 2000.0


def test_reset_then_a_late_byte_from_a_dropped_sessions_child_does_not_crash(mon):
    """reset() drops ended sessions, but an exited child could still map to
    one in the owner cache; its last bytes then hit a KeyError."""
    feed(mon, sample(("node", CHILD, "34.1.1.1", 0, 0)))
    mon.ingest(sample(("node", CHILD, "34.1.1.1", 0, 0)), {OTHER: PS[OTHER]}, {}, now=1001.0)
    mon.reset(1002.0)
    mon.ingest(sample(("node", CHILD, "34.1.1.1", 0, 80)), {OTHER: PS[OTHER]}, {}, now=1003.0)
    assert mon.others["node"].total_out == 80


def test_a_block_queued_before_reset_does_not_spike_the_rates(mon):
    """The loop resets at time.time() but may then ingest a block stamped
    before it. Spanning from the reset made the 5 s rate divide 5 KB by a
    few milliseconds."""
    mon.ingest(sample(("Dropbox", OTHER, "8.8.8.8", 0, 0)), PS, REG, now=1000.0)
    mon.reset(1001.3)
    mon.ingest(sample(("Dropbox", OTHER, "8.8.8.8", 0, 5000)), PS, REG, now=1001.0)
    up_5s = mon.other_total.rate(5, 1001.31, mon.span(1001.31))[1]
    assert up_5s <= 5000


def test_a_session_found_after_reset_counts_requests_from_the_reset(tmp_path, mon):
    """New watchers took the monitor's start time, so a session appearing
    after `r` counted pre-reset tokens against post-reset bytes."""
    proj = tmp_path / "projects" / "-x-proj"
    proj.mkdir(parents=True)
    early = datetime.fromtimestamp(mon.started + 10, timezone.utc).isoformat()
    (proj / "s1.jsonl").write_text(assistant("m1", 5000, ts=early))
    mon.reset(mon.started + 20)
    mon.ingest(sample(), PS, REG, now=mon.started + 21)
    assert mon.sessions[CLAUDE].watcher.requests == 0


def test_reset_restarts_the_request_count(tmp_path):
    w = ctm.TranscriptWatcher(tmp_path / "none.jsonl")
    w.requests, w.sent_tokens, w.sent_image_bytes = 3, 900, 50
    w.restart_count(5000.0)
    assert (w.requests, w.sent_tokens, w.sent_image_bytes, w.since) == (0, 0, 0, 5000.0)


NETSTAT_HEADER = ("Name       Mtu   Network       Address            Ipkts Ierrs     "
                  "Ibytes    Opkts Oerrs     Obytes  Coll")


@pytest.mark.parametrize("row", [
    "en0        1500  <Link#15>   72:ba:53:fb:ce:6c   362578     0  142735868    80949     0    8438812     0",
    # A VPN row has no Address; matching the header's field count rejected it.
    "utun0      1500  <Link#19>                       362578     0  142735868    80949     0    8438812     0",
])
def test_interface_bytes_reads_ethernet_and_vpn_rows(monkeypatch, row):
    out = f"{NETSTAT_HEADER}\n{row}\n"
    monkeypatch.setattr(ctm.subprocess, "run",
                        lambda *a, **k: ctm.subprocess.CompletedProcess(a, 0, out, ""))
    assert ctm.interface_bytes("x") == (142735868, 8438812)


def test_negative_top_is_refused():
    with pytest.raises(SystemExit) as excinfo:
        ctm.main(["--top", "-1"])
    assert "--top" in str(excinfo.value.code)


def test_interval_below_one_is_refused():
    with pytest.raises(SystemExit) as excinfo:
        ctm.main(["--interval", "0"])
    assert "interval" in str(excinfo.value.code)


def test_refuses_to_run_without_a_terminal(monkeypatch):
    monkeypatch.setattr(ctm.sys.stdout, "isatty", lambda: False)
    with pytest.raises(SystemExit) as excinfo:
        ctm.main([])
    assert "terminal" in str(excinfo.value.code)
