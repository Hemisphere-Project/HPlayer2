# HPlayer2 — Synchronization (current state)

> **Status: early draft — intentionally light.** Sync is the area under the most active rethinking
> (see [`ROADMAP.md`](../ROADMAP.md) Phase 3). This page documents **what exists today** and how to
> use it, plus the **direction** — but it deliberately does *not* prescribe the future converged API,
> which isn't decided yet. Expect this to change.

HPlayer2 has two independent sync mechanisms today, suited to different needs:

| Mechanism | Module | Good for | Transport |
|-----------|--------|----------|-----------|
| **Discrete synced triggers** | `zyre` | "everyone start cue 3 together" over a LAN | wifi / ethernet (ZeroMQ) |
| **Continuous lock** | `nowde` (+ raw `mtc`) | slaving playback frame-by-frame to an external timecode | MIDI / MTC (wired) |

They are not yet coordinated with each other — converging them is the Phase 3 goal.

---

## Discrete synced triggers (Zyre)

`zyre` auto-discovers other HPlayer2 nodes on the network and lets any node broadcast a **timestamped,
scheduled command** that fires on every peer (including the sender) at roughly the same moment.

**Enable it** (pick the network interface to use for discovery):

```python
hplayer.addInterface('zyre', 'eth0')      # or 'wlan0', or omit to auto-pick
```

**Send a trigger** to all peers via the Zyre node, with an optional **delay in milliseconds**. The
delay is the sync window: the command is timestamped and scheduled to run on every peer after it, so
slower-to-arrive nodes still fire together.

```python
zyre = hplayer.interface('zyre')
zyre.node.broadcast('playdir', [3], 200)   # 'playdir' with arg 3, scheduled +200ms
```

**Receive a trigger** — a broadcast `'playdir'` arrives on every node as the event `zyre.playdir`:

```python
@hplayer.on('zyre.playdir')
def _(ev, *data):
    hplayer.playlist.play(...)             # act on the synced cue
```

A few patterns from the real example profiles:

- **Leader election:** every received trigger carries its origin; the sender sees `from == 'self'`,
  which a profile can use to decide who drives the sequence.
  ```python
  @hplayer.on('zyre.event')
  def _(ev, *data): iamLeader = (data[0]['from'] == 'self')
  ```
- **Status sharing:** the `zyre` interface also publishes each node's player status to peers
  automatically.

See [`profiles/multisync.py`](../profiles/multisync.py) for a complete leader/slave sequencer, and
[`profiles/biennale24-rtc.py`](../profiles/biennale24-rtc.py) for another variant.

---

## Continuous lock (MTC / `nowde`)

When you need a player to stay frame-locked to an external clock (a timecode generator, a DAW, a
master player), slave it to MIDI Time Code with `nowde` — a continuous-correction engine (adaptive
speed, dead-zone hysteresis, smoothing).

```python
player = hplayer.addPlayer('mpv', 'player')
hplayer.addInterface('nowde', player)      # optionally: ('nowde', player, port_name)
```

`nowde` selects media from incoming MIDI CC#100 and continuously nudges the player's speed to track
the timecode. For the raw timecode stream without correction, use `mtc` (emits `mtc.qf` / `mtc.ff`)
and handle it yourself. See [`profiles/biennale24-midi.py`](../profiles/biennale24-midi.py).

---

## Known limitation: the trigger→frame gap

A Zyre trigger fires the *event* on time, but the actual first frame/audio sample appears later —
player startup, codec init, and A/V buffering add an unmodeled, hardware-dependent delay (roughly
150–600 ms), and there is currently no measurement or feedback to compensate. The `broadcast(...)`
delay argument is the only lever today (hence the `# WARNING LATENCY` notes in profiles).

Other rough edges to be aware of:
- Zyre shutdown can hang (`zyre.py:602`) — see ROADMAP Phase 1.
- Timing relies on a busy-wait, which adds jitter.

---

## Where this is heading (not yet decided)

Phase 3 of the [roadmap](../ROADMAP.md) aims to converge the two mechanisms into one sync service
that supports **both**:

- a **preroll-locked start** — preload, hold on the first frame, release on a shared clock (closing
  the trigger→frame gap), with correction for missed triggers and inter-machine drift; and
- a **freewheel** mode — gapless looping with continuous drift correction (no preroll),

aiming for frame-locked precision while tolerating a slightly divergent instant-start when preroll
isn't possible — over wifi or ethernet, across mixed hardware, with telemetry on real onset.

**The API for this is not finalized.** Until it lands, use the per-mechanism setup above and treat
the converged design as open. If you're building something that depends on tight sync, it's worth
discussing your use case before committing to one path — your constraints should inform the design.
