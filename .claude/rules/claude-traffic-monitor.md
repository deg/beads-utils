---
paths:
  - "claude-traffic-monitor"
  - "tests/test_claude_traffic_monitor.py"
---

# claude-traffic-monitor design notes

Path-scoped: Claude Code loads this file when a matching path is read.
The one-paragraph summary lives in the root `CLAUDE.md`; this is the
rationale an editor needs. Keep new design notes here, not there.

Built for a cruise with metered Wi-Fi (beads-utils-br0, which has the design
discussion). It is a live `top`-style screen in stdlib `curses`. It shows,
per running Claude Code session, upload and download rate, totals since the
monitor started, the API share, context tokens, and the images in context.
Below that come the busiest non-Claude processes.

## Data sources, and what was verified

- **nettop counts only sockets that are open now. It does not count a
  process's lifetime.** This was verified on 2026-10-07: a session that had
  been running for three days showed 2 KB, because only one idle keep-alive
  socket was open. A closed connection's bytes drop out of the next sample.
  So totals are built from **per-flow deltas** and never from nettop's
  process line:
  - Flows present in the first block are the baseline.
  - A flow first seen in a later block counts in full.
  - A counter that goes backwards means the connection string was reused by
    a new socket.
  - Bytes sent in a socket's last interval before it closes are lost. That
    is why the interval is 1 s.
- **Several flows can print the same connection string.** For example, a
  process may have five unconnected `udp4 *:*<->*:*` sockets. So a flow's key
  includes its position among the identical strings in that process's block.
- **nettop is run once, streaming** (`-L 0 -s N -x -n -J bytes_in,bytes_out`)
  and read by a reader thread. A block is complete only when the next header
  arrives, so the screen runs one interval behind. A one-shot `nettop -L 1`
  per tick costs about 0.12 s of CPU each time. The streaming process used
  about 3% of one core (8.5 s of CPU over 4.5 minutes, measured 2026-10-07),
  which matters for a laptop on battery. `-n` keeps remote addresses
  numeric, which the classification below needs.
- **Process lines are split on the last dot**, because names contain dots:
  `com.norton.mes..974`, and Claude itself appears as `2.1.292.70303`.
  nettop truncates names to 15 characters, so the full name comes from `ps`.
- **Only internet traffic is counted.** A remote address that is loopback,
  private, link-local, multicast or unspecified is "local" and is dropped. On
  the developer's machine, `kernel_task` carries GB of SMB traffic to a NAS,
  which would otherwise top the list. A wildcard remote (`*`) is an
  unconnected socket and is dropped too, which also drops mDNS chatter.
- **The interface line is the raw `netstat -ib` `<Link#>` counter** for the
  default-route interface. It is re-resolved every tick because the route
  moves between Ethernet and Wi-Fi. It includes LAN traffic, so it matches
  the per-flow sums only when the LAN is quiet.

## Attribution

- Sessions come from `~/.claude/sessions/<pid>.json`, read every tick, using
  the same registry as `claudeutils.live_session_pid`.
  - A registry file whose pid is absent from `ps` is treated as a crash
    leftover.
  - `/clear` changes the `sessionId` for the same pid. The row is keyed by
    pid, so the row stays and the transcript watcher switches to the new
    transcript.
  - A nettop process named like a version (`2.1.300`) that is not in the
    registry still gets a row, labelled `(unregistered claude)`.
- Each session's whole process tree counts toward it: MCP servers, Bash-tool
  commands and hooks. One `ps -A -o pid=,ppid=,comm=` per tick is walked
  upward from each pid. The owner found is **sticky**: every pid in the
  table is resolved each tick, so a child that later exits keeps its session.
  A process born and gone between two `ps` snapshots goes unattributed and
  lands under the other processes.
- A session whose pid disappears stays on screen, dimmed, as `(ended)`, so
  the totals never drop.
- **API%** is the share of a session's bytes whose remote address is one of
  `api.anthropic.com`'s addresses. Those are resolved at startup and every
  5 minutes, seeded with the addresses observed on 2026-10-07. Most of the
  rest is telemetry: on the first live run, one session sent 82 KB to a
  Google Cloud address.

## Transcript columns

`TranscriptWatcher` follows `~/.claude/projects/*/<sessionId>.jsonl`.
- It reads only what was appended, by byte offset, and never consumes a
  partial last line.
- It skips lines that contain none of the interesting tags before calling
  `json.loads`.
- It skips sidechain entries.
- CTX is the context size from the latest main-thread `usage`:
  `input_tokens`, plus `cache_creation_input_tokens`, plus
  `cache_read_input_tokens`.
- IMAGES is a count and the base64 bytes of image blocks since the last
  `compact_boundary`. That includes images nested in tool results, such as
  screenshots. They are re-sent with every request until then. Verified: 16
  of 483 transcripts carry a `compact_boundary` entry.
- The first poll reads the whole transcript, which takes about 0.3 s across
  five sessions.

## Scope of the first pass

Totals live in memory only and start when the monitor starts. There is no
state file, which keeps to the repo's "no state" convention. Deliberately
deferred:
- beads-utils-hrc (background logger so traffic counts while closed)
- beads-utils-7fe (`--once` / `--log`)
- beads-utils-84u (interactive keys)

## Manual checks

```bash
./claude-traffic-monitor                 # live screen; q quits
./claude-traffic-monitor -s 2 --top 15   # slower sampling, more processes
pgrep -fl 'nettop -L 0'                  # after quitting: must print nothing
```
