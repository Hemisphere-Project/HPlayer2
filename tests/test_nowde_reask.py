"""hplayer2#t-108: a player in auto whose node is a master must end up MASTER whatever the timing of
its start. A 2.x node answers a probe with its HELLO only when the host speaks after >= 5 s of silence
(Nowde `hostResumed`, HOST_LINK_TIMEOUT_MS 5000); a sender otherwise answers with its slave table.
The fake node below implements that rule as the 2.4 firmware does (src/midi.cpp, src/sysex.cpp) and
the interface's own probe tick is driven on a simulated clock: nothing is started, no port is opened."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("mido")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                        # noqa: E402
from core.interfaces.nowde import (                             # noqa: E402
    NowdeInterface, encode7, CMD_HELLO, CMD_RUNNING_STATE, CMD_QUERY_RUNNING_STATE, CMD_QUERY_CONFIG,
)

HOST_LINK_TIMEOUT = 5.0     # the node's HOST_LINK_TIMEOUT_MS
STEP = 0.02                 # the emitter's pass


def hello(role):
    up = encode7([0, 0, 0x27, 0x10])
    return [0x7D, CMD_HELLO] + encode7(list(b'2.4.1'.ljust(8, b'\x00'))) + up + [3, role, 1, 2, 0]


def running_state():
    rec = ([0xA0, 0xB1, 0xC2, 0xD3, 0xE4, 0x01] + list(b'hplayer2'.ljust(16, b'\x00'))
           + list(b'2.4.1'.ljust(8, b'\x00')) + [0, 0, 0x01, 0xF4, 1, 3, 2, 0, 5])
    return [0x7D, CMD_RUNNING_STATE] + encode7([0, 0, 0x27, 0x10]) + [1, 1, 0, 1, 1] + encode7(rec)


class Clock:
    t = 1000.0


class FakeNode:
    """The interface's `out`. kind: 'master' (a sender), 'slave201' (a 2.0.1+ resolved slave: HELLO on
    every probe), 'slave200' (2.0.0: HELLO only on the probe after a silence), 'v1' (a v1.2 receiver:
    silent). last_rx = when a host last spoke to it (None = it just booted). drop = HELLOs lost on
    the way back (a reboot while our input was not read yet)."""

    def __init__(self, clock, kind='master', last_rx=None, drop=0):
        self.clock, self.kind, self.last_rx, self.drop = clock, kind, last_rx, drop
        self.resumed = False
        self.iface = None
        self.rx = []                                # (t, cmd) of every host frame

    def send(self, msg):
        data, t = list(msg.data), self.clock.t
        self.rx.append((t, data[1]))
        if self.last_rx is None or t - self.last_rx >= HOST_LINK_TIMEOUT:
            self.resumed = True                     # first packet after a silence
        self.last_rx = t
        if self.kind == 'v1':
            return
        role = 1 if self.kind == 'master' else 0
        if data[1] == CMD_QUERY_CONFIG:
            self.resumed = False
            self._back(hello(role))
        elif data[1] == CMD_QUERY_RUNNING_STATE:
            sent = False
            if self.resumed:
                self.resumed = False
                self._back(hello(role))
                sent = True
            if self.kind == 'master':
                self._back(running_state())
            elif not sent and self.kind == 'slave201':
                self._back(hello(role))

    def _back(self, frame):
        if frame[1] == CMD_HELLO and self.drop:
            self.drop -= 1
            return
        self.iface._handle_sysex(frame)

    def close(self):
        pass

    def probes(self, since=0.0):
        return [t for t, c in self.rx if c == CMD_QUERY_RUNNING_STATE and t >= since]


class FakePlayer:
    name = 'player'

    def status(self, entry=None):
        st = {'isPlaying': False, 'isPaused': False, 'media': None, 'time': 0.0, 'duration': 0.0}
        return st[entry] if entry else st

    def isPlaying(self):
        return False

    def stop(self):
        pass

    def speed(self, s):
        pass


def make(monkeypatch, node, mode='auto'):
    hplayer = HPlayer2(mediaPath=[])
    player = FakePlayer()
    hplayer._players['player'] = player
    i = NowdeInterface(hplayer, player, mode=mode)
    i.lines, i.events = [], []
    monkeypatch.setattr(i, 'log', lambda *a: i.lines.append(' '.join(str(x) for x in a)))
    monkeypatch.setattr(i, 'emit', lambda ev, *a: i.events.append((ev,) + a))
    node.iface = i
    i.port, i.out = node, node                      # linked, as the listener leaves it after a connect
    i._connected_at = node.clock.t
    return i


def run(i, clock, seconds, until=None):
    """Drive the probe tick like the emitter thread does; returns the time `until(i)` first held."""
    end = clock.t + seconds
    while clock.t < end:
        clock.t += STEP
        if i.isMaster():
            if until and until(i):
                return clock.t
            continue                                # the master leg polls; not under test here
        i._probe_tick(clock.t)
        if until and until(i):
            return clock.t
    return None


def roles(i):
    return [e[1] for e in i.events if e[0] == 'role']


# ---------------------------------------------------------------- the rig's two failures


@pytest.mark.parametrize('gap', [0.5, 1.0, 3.0, 4.9])
def test_a_restart_within_5s_of_the_last_probe_still_ends_master(monkeypatch, gap):
    """25/11 17:55: a player started a few seconds after the previous instance's last probe. The
    node answered with its table, never its HELLO, and the player stayed « v1 slave » for good."""
    clock = Clock()
    node = FakeNode(clock, 'master', last_rx=clock.t - gap)
    i = make(monkeypatch, node)
    t0 = clock.t
    at = run(i, clock, 30, until=lambda i: i.isMaster())
    assert at is not None, i.lines
    assert at - t0 < 8.0                            # one probe, 6 s quiet, one probe
    assert roles(i) == ['master']                   # never flipped to slave on the way
    assert any("sender's table" in l for l in i.lines)
    assert any('role re-ask 1 answered' in l for l in i.lines)


def test_a_hello_lost_after_a_node_reboot_is_asked_again(monkeypatch):
    """25/11 17:25: node A rebooted (COM reset); its one HELLO did not reach the reconnected player."""
    clock = Clock()
    node = FakeNode(clock, 'master', last_rx=None, drop=1)
    i = make(monkeypatch, node)
    t0 = clock.t
    at = run(i, clock, 30, until=lambda i: i.isMaster())
    assert at is not None and at - t0 < 8.0
    assert roles(i) == ['master']


@pytest.mark.parametrize('gap', [None, 1.0, 3.0, 6.0, 12.0])
@pytest.mark.parametrize('drop', [0, 1])
def test_every_start_timing_ends_master(monkeypatch, gap, drop):
    """The rig recipe's restart gaps (1, 3, 6, 12 s; None = a fresh node) with or without a lost HELLO.
    Losing the re-ask's own HELLO (gap < 5 s: the first HELLO the node sends IS the re-ask's) costs a
    slave detour until the next re-ask, 30 s later; every other case is master at once."""
    clock = Clock()
    node = FakeNode(clock, 'master', last_rx=None if gap is None else clock.t - gap, drop=drop)
    i = make(monkeypatch, node)
    t0 = clock.t
    at = run(i, clock, 60, until=lambda i: i.isMaster())
    assert at is not None, i.lines
    run(i, clock, 60)
    detour = drop and gap is not None and gap < HOST_LINK_TIMEOUT
    assert i.isMaster() and roles(i) == (['slave', 'master'] if detour else ['master'])
    assert at - t0 < (6.0 + 6.0 + 30.0 + 6.0 + 1.0 if detour else 8.0)


def test_a_2_0_0_slave_whose_hello_was_lost_is_re_asked_once(monkeypatch):
    """2.0.0 slaves answer only the probe after a silence: the v1 guess stands (the right leg), and
    one re-ask turns the guess into the node's word; then no more quiet windows."""
    clock = Clock()
    node = FakeNode(clock, 'slave200', last_rx=None, drop=1)
    i = make(monkeypatch, node)
    run(i, clock, 20)
    assert i.isSlave() and i._nodeIntroduced and not i._roleAssumed
    assert roles(i) == ['slave']
    since = clock.t
    run(i, clock, 120)
    p = node.probes(since)
    assert max(b - a for a, b in zip(p, p[1:])) < 2.1      # plain 2 s probes, no quiet window


# ---------------------------------------------------------------- what must not change


def test_a_v1_receiver_costs_a_quiet_window_now_and_then_and_little_journal(monkeypatch):
    clock = Clock()
    node = FakeNode(clock, 'v1')
    i = make(monkeypatch, node)
    t0 = clock.t
    run(i, clock, 6.5)
    assert i.isSlave() and roles(i) == ['slave']    # the v1 guess at 6 s, as before
    run(i, clock, 600 - 6.5)
    # re-asks at ~12 s, ~48 s, then every ~126 s: 12, 48, 174, 300, 426, 552
    assert 5 <= i._reasks <= 6
    assert sum('role re-ask' in l for l in i.lines) == i.REASK_LOGGED
    p = node.probes(t0)
    gaps = [b - a for a, b in zip(p, p[1:])]
    assert sum(g > 5.0 for g in gaps) == i._reasks  # each re-ask = one silence >= 5 s, no other
    assert all(g < 2.1 or g >= 5.0 for g in gaps)
    assert roles(i) == ['slave']


def test_a_node_that_said_who_it_is_is_never_re_asked(monkeypatch):
    clock = Clock()
    node = FakeNode(clock, 'slave201', last_rx=clock.t - 1.0)   # no HELLO-after-silence, yet one each probe
    i = make(monkeypatch, node)
    run(i, clock, 120)
    assert i.isSlave() and i._reasks == 0 and i._quietUntil == 0.0
    p = node.probes()
    assert len(p) >= 59 and max(b - a for a, b in zip(p, p[1:])) < 2.1


@pytest.mark.parametrize('mode', ['slave', 'master'])
def test_a_forced_role_never_goes_quiet(monkeypatch, mode):
    clock = Clock()
    node = FakeNode(clock, 'master', last_rx=clock.t - 1.0)
    i = make(monkeypatch, node, mode=mode)
    if mode == 'master':
        assert i.isMaster()
        return                                      # the master leg's 1 s poll is untouched
    run(i, clock, 60)
    assert i.isSlave() and i._reasks == 0
    p = node.probes()
    assert max(b - a for a, b in zip(p, p[1:])) < 2.1


def test_a_relink_starts_the_introduction_again(monkeypatch):
    clock = Clock()
    node = FakeNode(clock, 'v1')
    i = make(monkeypatch, node)
    run(i, clock, 20)
    assert i._roleAssumed and i._reasks >= 1
    i._close_ports()
    assert i.role is None
    assert (i._nodeIntroduced, i._roleAssumed, i._senderHeard, i._quietUntil, i._reasks) == (False, False, False, 0.0, 0)
