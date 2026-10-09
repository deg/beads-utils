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

- **Totals come from process lines; kinds come from connection lines.**
  - A **one-shot** nettop (`-L 1`) knows only the connections open at that
    moment. A session three days old showed 2 KB that way (2026-10-07).
  - A **streaming** nettop's process line keeps growing for as long as
    nettop runs, closed connections included. Verified on 2026-10-08
    (beads-utils-8pt): a process that stayed alive after a 20 MB download
    kept 20.03 MB on its process line once its connection line was gone.
  - A **connection line** vanishes when the connection closes, taking its
    last second of bytes with it. The first version counted only
    connection lines and recorded curl's 20 MB download as 9.6 MB.
  - So `FlowTracker` counts each connection line's growth, with its kind,
    and recovers whatever the process line grew beyond that. The process
    line is a floor, not a cap: connection growth above it is kept. The
    recovered remainder belongs to connections that closed during the
    interval. It is split
    among the connections that vanished from that process, by size, and
    inherits their kind (internet, local, API, tunnel).
  - If none vanished, a connection opened and closed between two samples and
    was never shown. Its bytes count as internet and also feed the dim "Too
    brief to classify" line.
  - Re-measured afterwards: 20.03 MB counted for the 20 MB download.
  - Baseline rules, for processes and connections alike: the first block is
    the baseline, anything first seen later counts in full, and a counter
    that goes backwards means a reused connection string or pid.
  - `-s` takes whole seconds only: `-s 0.2` produced no samples at all.
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
  which would otherwise top the list.
- **Unconnected UDP sockets count as internet.** nettop shows such a socket
  with a wildcard remote (`udp4 *:41641<->*:*`), so where its bytes went is
  unknown.
  - The exception is a socket bound to a LAN-only port: mDNS, DHCP, SSDP,
    NetBIOS or LLMNR (`LAN_ONLY_UDP_PORTS`). A wildcard TCP socket is a
    listener and carries nothing.
  - Found live on 2026-10-07 (beads-utils-d31, count VPN/tunnel traffic
    once): Tailscale's WireGuard traffic runs over such a socket. Treating it
    as unknown, while also treating the inner 100.x flow as local, meant
    traffic to a Tailscale peer was counted **zero** times.
  - After the fix, 150 requests to a peer, about 82 KB of responses, showed
    as 84 KB down under the Tailscale extension.
  - This errs toward overcounting: a peer on the same LAN reached this way
    is counted as internet.
- **Tailscale's 100.64/10 (CGNAT) addresses are local.** A flow to a peer's
  overlay address is the inner copy. The outer copy, the WireGuard socket
  above, is the one metered, so it is counted there, once, under the
  Tailscale process.
- **Tunnelled traffic is reported, not subtracted.** A flow whose local
  address is on a tunnel interface (`utun`, `ipsec`, `ppp`, `tun`, `tap`,
  `wg`, read from `ifconfig` every tick) stays credited to its app. A dim
  "Tunnelled, in rows above / sent twice" line under the totals shows those
  bytes, because the tunnel's process sends them again, encrypted.
  - Option C (a "VPN overhead" row) was dropped: nothing in nettop, ps or
    ifconfig says which process carries a tunnel.
  - **Untested:** a full tunnel (exit node). That is the case where apps'
    internet flows leave from the tunnel address. David has no exit node
    configured. Without one, only flows to 100.x peers use the tunnel, and
    those are local.
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
- **Names come from `ps`, remembered per pid.** nettop truncates names to
  15 characters, so `ps`'s full name is preferred. But `ps` shows an exiting
  process as `(name)` and a zombie as `<defunct>`. Used verbatim, they split
  one app across two rows (`idrive_ver_001` and `(idrive_ver_001)`; a curl
  download landed half under `curl`, half under `<defunct>`;
  beads-utils-mz7). So parentheses are unwrapped, and the last good name is
  kept for when `ps` has none. nettop's name is the last resort.
- **Transparent proxies are counted once, under the app**
  (`ProxyDetector`, beads-utils-7z7). Norton's network extension relays
  Chrome's traffic, and nettop shows those bytes twice. They appear on
  Chrome's *process* line, while its connection lines stay near zero, and
  again on Norton's own connections to the same servers. Over 30 s on
  2026-10-08, Chrome's process line grew 3.5 MB against 7 KB on its
  connection lines, and 94% of its endpoints were also Norton's.
  - **Detection:** an app counts as relayed by process P when at least 80%
    of its internet endpoints (address:port) are also P's, its connection
    lines account for under 10% of its growth, and that growth exceeds
    100 KB.
  - **Why overlap alone isn't enough:** Claude sessions share the API
    endpoint with Norton but carry their bytes on their own connection
    lines.
  - **Accounting:** the app keeps its bytes. P's internet bytes are reduced
    by the same amount, carried across blocks until P moves them, so P's row
    shows only its overhead. A dim line under P's row names the apps it
    relays.
  - **Live check, 60 s:** Chrome 8.22 MB, Norton 1.87 MB (overhead plus
    anything it relays undetected). Totals 10.3 MB, under the interface's
    11.9 MB. "Too brief to classify" fell from about 1 MB to 0.15 MB.
  - **Until an app passes 100 KB**, its relayed bytes are briefly counted
    twice.
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
  Its column is labelled `max1m`, built from `PEAK_WINDOW`. A bare "peak"
  did not say what period it covered (David).
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
| `c` | cycle the child rows: active, then all, then none |
| `o` | hide or show the list of other processes |
| `r` | reset the totals |
| `p` | pause the display |
| `?` | show or hide the key help line |
| `q` | quit |

- `handle_key()` is pure: it changes a `View` and returns what the loop must
  do. The view only changes what is drawn, never what is counted.
- **Rate sort uses the 1-minute average.** The 5 s figure would reshuffle
  the rows every second. Live sessions always stay above ended ones.
- **A status bar is pinned to the bottom row** in reverse video, as in `top`.
  It shows the sort mode, whether children and others are hidden, PAUSED,
  and the `? keys` / `q quit` hints. `?` adds the key list above it. David
  asked for this; the state first lived in the title line, where it was easy
  to miss.
- **Hiding children (`c`) keeps their bytes in the session's row.**
- **`active`, the default, hides a child row once it has exited and idled
  for 15 minutes** (beads-utils-1z7). After a day's run each session listed
  every child that ever moved a byte (curl, ssh, gh, uv...), 6-7 rows of
  zeros apiece.
  - The idle threshold is the longest rate window, `max(RATE_WINDOWS)`: by
    then every rate cell reads zero, so hiding the row loses only its total,
    which is still in the session's row. `Counter.idle` is just "no ticks
    kept", since ticks are pruned past that window.
  - Rows are keyed by name, so "exited" means no live pid of that name is
    in the session's tree (`Session.live_children`, rebuilt each tick from
    the same `ps` walk that assigns owners).
  - A live but idle child (an MCP server) stays: it is still running, and
    its row says so. David agreed.
  - A dim `└ N exited, idle 15m+` line explains why the visible
    children no longer add up to the session's total.
- **Hiding others (`o`) collapses the whole section into one row**:
  `Other processes`, `N hidden`, and their totals, aligned with the session
  columns above it. The first version kept the section header and an
  "… and N more" line, which David found read as leftover text.
- **`curses.use_default_colors()`** keeps the terminal's own theme. Without
  it, `curses.wrapper` painted every cell white on black, which a pty check
  showed as `ESC[37m ESC[40m` on every write.
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
