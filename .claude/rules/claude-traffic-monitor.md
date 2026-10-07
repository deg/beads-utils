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
- **Tailscale's 100.64/10 (CGNAT) addresses are local.** A flow to a peer's
  overlay address is tunnelled, so the same bytes leave the machine again as
  Tailscale's own flow to the peer's real address (or a relay). That outer
  flow is the metered one. Counting both would bill the bytes twice. The
  cost is that they are billed to Tailscale, not to the app that sent them.
  **Unverified:** that nettop shows the Tailscale network extension's outer
  flow (it does show Norton's extension's flows). Tailscale was not connected
  on 2026-10-07.
- **Known gap: a full-tunnel VPN doubles the totals.** Apps' flows carry
  public addresses, and so does the VPN client's encrypted flow that
  carries them. Not handled yet.
- **nettop cuts names at a byte count**, which can split a UTF-8 character
  (seen in review). The stream is decoded with `errors="replace"`, and the
  reader thread sends its end marker from `finally`, so a dead reader ends
  the screen with an error instead of freezing it silently. Process lines
  are split from the right, because a name may contain a comma.
- **The interface line is the raw `netstat -ib` `<Link#>` counter** for the
  default-route interface. It is re-resolved every tick because the route
  moves between Ethernet and Wi-Fi. Counters are read by their position
  from the end of the row: a `utun` (VPN) row leaves Address blank, which
  shifts every later field one place left. It includes LAN traffic, so it matches
  the per-flow sums only when the LAN is quiet.

## Attribution

- Sessions come from `~/.claude/sessions/<pid>.json`, read every tick, using
  the same registry as `claudeutils.live_session_pid`.
  - A registry file whose pid is absent from `ps` is treated as a crash
    leftover.
  - **Assumed, not yet verified:** `/clear` changes the registry's
    `sessionId` for the same pid. The row is keyed by pid, so if that holds,
    the row stays and the transcript watcher switches to the new transcript.
    If it does not hold, CTX and IMAGES go stale right after a `/clear`,
    which is the very step the tool exists to prompt. To check, diff a
    session's `~/.claude/sessions/<pid>.json` from before and after `/clear`.
    Tracked as beads-utils-6tf (verify the registry's sessionId follows
    /clear). `/clear` does start a new transcript with a new id, verified on
    two throwaway sessions.
  - A nettop process named like a version (`2.1.300`) that is not in the
    registry still gets a row, labelled `(unregistered claude)`.
- Each session's whole process tree counts toward it: MCP servers, Bash-tool
  commands and hooks. One `ps -A -o pid=,ppid=,comm=` per tick is walked
  upward from each pid, stopping only at a session that is still alive.
  The owner is **sticky only once a pid has exited**: every pid in the table
  is resolved each tick, so a child that later exits keeps its session. A
  pid that `ps` still shows is always walked again, because macOS recycles
  pids. The first version trusted its cache forever, and an unrelated
  process that inherited a dead child's pid (or a dead session's) was
  billed to that session.
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

## Rates and the NEXT column

Added for beads-utils-7hb (tiered rolling rates) and beads-utils-sfm
(estimated upload cost of the next request).

- **Rates come in three tiers, 5 s, 1 min and 15 min, plus a peak**, for
  both directions. Conversational traffic is bursty: a request uploads its
  whole context in a second or two, then the link is idle. Any average
  dilutes that burst, so the **peak** (the busiest single tick in the last
  minute) keeps it visible after the 5 s figure has dropped back to zero.
  - David asked for both directions "to see how it fits". The rows come to
    about 145 columns.
  - The tier lengths were Claude's pick, since David had no strong view.
    Change them in `RATE_WINDOWS` if they read wrong in use.
- **A young monitor divides by the time it has actually counted.** Each
  average divides by the shorter of its window and that time. Otherwise the
  15 min tier would read near zero for its first several minutes.
- **A `Counter` keeps only ticks that moved bytes**, and only for the longest
  window. An idle process stores nothing.
- **NEXT is the estimated upload of a session's next request**: `CTX x 0.7 B`
  plus the image bytes x 0.75. Both factors are fixed constants. The 0.7
  comes from the 2026-10-07 brainstorm, which read one-shot nettop process
  totals. Those miss the bytes of connections already closed, so 0.7 is
  probably an undercount.
- **The footer shows the measured ratio, so the constant can be corrected.**
  It is API upload since start divided by the context tokens of the requests
  the transcripts recorded since start, **over sessions that carried no
  images**.
  - An earlier version subtracted an estimated image share instead. On a
    live run it read 5.01 B per token, where the transcripts implied about
    1.2. When images are 90% of the bytes, a small error in that estimate
    swamps the token signal.
  - Requests are deduplicated by message id, because one response spans
    several transcript entries that each repeat its `usage`.
  - Only requests timestamped after the monitor started count.
  - Only sessions that have a transcript count, for the bytes as well as the
    tokens. An unregistered `claude -p` would otherwise inflate the ratio.
  - Known bias: it reads high. Requests missing from a main transcript
    (subagents, title generation, compaction) still upload.
- **NEXT checked out on a live run (2026-10-07).** `novalty-56` (21 images,
  6.4 MB of base64, 377k tokens) made exactly 3 requests in a 4-minute
  sample. NEXT predicted 5.1 MB per request. The measured upload was 15.4 MB,
  or 5.13 MB each, so the 0.75 image factor holds. The 1-minute peak also
  read 5.1M, because each request went out within about a second.

## Keys

Added for beads-utils-84u (top-style interactive keys), with the key set
David approved:

| Key | Action |
|---|---|
| `s` | cycle the sort: total, then 1-minute rate, then name |
| `c` | hide or show child-process rows |
| `o` | hide or show the list of other processes |
| `r` | reset the totals |
| `p` | pause the display |
| `?` | show or hide the key help line |
| `q` | quit |

- `handle_key()` is pure: it changes a `View` and returns what the loop must
  do. The view only changes what is drawn, never what is counted.
- **Rate sort uses the 1-minute average.** The 5 s figure would reshuffle
  the rows every second. Live sessions always stay above ended ones.
- **Hiding children (`c`) keeps their bytes in the session's row.** Hiding
  others (`o`) keeps their total line and an "… and N more" count.
- **`r` zeroes everything**: totals, rolling rates, the bytes-per-token
  measurement and the interface baseline. It also restarts the title's
  counting clock.
  - It drops ended sessions and the other processes, since zeroed they say
    nothing.
  - It keeps the flow baselines and pid ownership, because those describe
    connections and processes, not counts.
  - It also prunes owner-cache entries that point at dropped sessions.
    Without that, an exited child's last bytes looked up a session that was
    gone and crashed the screen. The mutation test caught it.
  - Rates restart from the **last block ingested**, not from the keypress.
    A block already queued when `r` was pressed carries deltas since that
    block; dividing them by the milliseconds since the keypress showed tens
    of MB/s.
  - A watcher created after a reset counts requests from the reset, not
    from the monitor's start. Otherwise pre-reset tokens would be set
    against post-reset bytes in the footer.
- **`p` freezes the drawing; counting continues.** A view key pressed while
  paused redraws once, with current numbers.
- Checking the keys in a pty: curses rewrites only the characters that
  changed, so look for fragments ("rate" -> "name" writes only `n` and `m`).

## Scope of the first pass

Totals live in memory only and start when the monitor starts. There is no
state file, which keeps to the repo's "no state" convention. Deliberately
deferred:
- beads-utils-hrc (background logger so traffic counts while closed)
- beads-utils-7fe (`--once` / `--log`)
- beads-utils-84u (interactive keys), since done; see Keys above

## Manual checks

```bash
./claude-traffic-monitor                 # live screen; ? lists the keys, q quits
./claude-traffic-monitor -s 2 --top 15   # slower sampling, more processes
pgrep -fl 'nettop -L 0'                  # after quitting: must print nothing
```
