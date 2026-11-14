"""A draining status reader must not read as a late player (hplayer2#t-093).

Anna-03, pass F (07/11, a 6 s 2.4 GHz drop): the follower's drift CSV showed a 3-row plateau at
+1661 ms, speed 2.0, a collapse to +29 ms in 0.25 s, a swing to -303 ms and a slow climb back. The
clock was fine (model off +1 ms). The cause is the follower's OWN position: mpv's status reader
stalled ~2 s, then drained its backlog, and each drained time-pos — old — was stamped on arrival.

These tests replay that on a fake clock, with the real Drifter and the real wallclock latch:
  - stall + slow drain: no tick reads itself late (the guard skips the drain);
  - the same with the guard off: the burst is there (the test reproduces the bench shape);
  - a REAL 1.66 s mpv lag: still read, within ~2 events of the player coming back;
  - the leader: no clock packet goes out while its own reader drains.
"""

import time

from core.engine.drifter import Drifter
from core.interfaces import wallclock
from core.interfaces.wallclock import WallclockInterface

EVENT = 0.040       # mpv time-pos cadence on 25 fps video
TICK = 0.045        # the follower's servo cadence
STALL_AT = 10.0
STALL = 2.2         # the reader is silent this long (the desk model's 2.0-2.3 s)
DRAIN = 0.006       # then delivers its backlog one event per 6 ms


class FakePlayer:
    name = 'player'

    def __init__(self):
        self.pos = 0.0

    def position(self):
        return self.pos

    def isPaused(self):
        return False

    def isPlaying(self):
        return True

    def resume(self):
        pass

    def speed(self, s):
        pass

    def seekTo(self, ms, exact=False):
        pass

    def status(self, k=None):
        return None


def _follower():
    w = WallclockInterface.__new__(WallclockInterface)     # only the latch + guard state
    w.elected = False
    w._latch = None
    w._posPrev = None
    w._posHold = 0
    return w


def _deliveries(lag=0.0, drain=True, until=16.0):
    """(arrival, pos) for every time-pos event. drain: the reader stalls and drains (the
    position is true when emitted, late when delivered). Not drain: mpv itself stalls `lag`
    seconds (no events, then events of a player that really is `lag` behind)."""
    out, k, backlog_free = [], 1, 0.0
    while True:
        emitted = k * EVENT
        if emitted > until:
            return out
        k += 1
        if drain:
            if STALL_AT <= emitted < STALL_AT + STALL:
                arrival = max(STALL_AT + STALL, backlog_free) + DRAIN
            elif emitted >= STALL_AT + STALL and backlog_free > emitted:
                arrival = backlog_free + DRAIN
            else:
                arrival = emitted
            backlog_free = arrival
            out.append((arrival, round(emitted, 2)))
        else:
            if STALL_AT <= emitted < STALL_AT + lag:
                continue
            out.append((emitted, round(emitted - (lag if emitted >= STALL_AT else 0.0), 2)))


def _run(monkeypatch, deliveries, guard=True, until=16.0):
    """Replay the deliveries and servo ticks in time order; the master clock is the true time.
    Returns [(t, telemetry)] for every tick the Drifter reported."""
    now = [0.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    if not guard:
        monkeypatch.setattr(wallclock, 'DRAIN_HOLD', 0)
    player, w = FakePlayer(), _follower()
    d = Drifter(player, log=lambda *a: None)
    d.posAge = w._ownPosAge
    d.arm()
    d.kickStart = 0
    ticks = [(round(i * TICK, 6), 'tick', None) for i in range(1, int(until / TICK))]
    events = [(a, 'pos', p) for a, p in deliveries]
    out = []
    for t, kind, p in sorted(events + ticks, key=lambda e: (e[0], e[1] == 'tick')):
        now[0] = t
        if kind == 'pos':
            player.pos = p
            w._onPlayerStatus('player.status', 'time', p)
        else:
            res = d.tick(t)
            if res:
                out.append((t, res))
    return out


def _after(out, t0):
    return [(t, r) for t, r in out if t >= t0]


def test_drain_is_skipped(monkeypatch):
    out = _after(_run(monkeypatch, _deliveries()), STALL_AT)
    assert out, 'the servo never ticked again after the drop'
    worst = max(abs(r['diff']) for _, r in out)
    assert worst < 0.080, 'a drained position read as %.3f s off' % worst
    assert not any(r['jumped'] for _, r in out)
    assert max(r['speed'] for _, r in out) < 1.2


def test_without_the_guard_the_burst_is_there(monkeypatch):
    """The desk test reproduces the bench: the same drain, the guard off, reads late by > 1 s."""
    out = _after(_run(monkeypatch, _deliveries(), guard=False), STALL_AT)
    assert max(r['diff'] for _, r in out) > 1.0


def test_a_real_lag_is_still_read(monkeypatch):
    lag = 1.66
    out = _after(_run(monkeypatch, _deliveries(lag=lag, drain=False)), STALL_AT + lag)
    late = [t for t, r in out if r['diff'] > 1.0 or r['jumped']]
    assert late, 'a real 1.66 s lag was never read'
    assert late[0] - (STALL_AT + lag) < 0.5, 'the guard held a real lag %.2f s' % (late[0] - STALL_AT - lag)


def test_hold_counts_normal_events_after_the_burst(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    w = _follower()
    seq = [0.00, 0.04, 0.08,            # normal
           0.40,                        # a 0.32 s silence: suspect
           0.403, 0.406,                # the backlog
           0.446, 0.486,                # two normally spaced events: still held
           0.526]                       # back at its cadence: trusted
    held = []
    for i, t in enumerate(seq):
        now[0] = t
        w._onPlayerStatus('player.status', 'time', 1.0 + i * 0.04)
        held.append(w._ownPosAge(1.0 + i * 0.04) is wallclock.POS_STALE)
    assert held == [False, False, False, True, True, True, True, True, False]


def test_jitter_under_the_burst_spacing_alone_holds_nothing(monkeypatch):
    """A < 10 ms pair with no silence before it is mpv jitter, not a drain."""
    now = [0.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    w = _follower()
    for i, t in enumerate([0.00, 0.04, 0.045, 0.085]):
        now[0] = t
        w._onPlayerStatus('player.status', 'time', 1.0 + i * 0.04)
        assert w._ownPosAge(1.0 + i * 0.04) is not wallclock.POS_STALE


def test_leader_sends_nothing_while_draining():
    """The leader's send loop reads the same guard: a drained position must not go out under a
    fresh `at` (the whole fleet would read itself ahead and slow down). Checked on the source,
    since the send loop is a thread over a socket."""
    import inspect
    src = inspect.getsource(WallclockInterface._runMaster)
    assert 'if self._posHold:\n                fresh = False' in src
