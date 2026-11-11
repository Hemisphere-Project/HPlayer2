"""The Nowde heartbeat: one line a minute on both roles, so a journal alone says whether the
link was alive at a given minute. Real HELLO / RUNNING_STATE frames go through the interface's
own SysEx handler; the clock is driven by hand, nothing is started."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("mido")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                        # noqa: E402
from core.interfaces.nowde import (                             # noqa: E402
    NowdeInterface, encode7, fmt_age, CMD_HELLO, CMD_RUNNING_STATE,
)


class FakePlayer:
    def __init__(self):
        self.name = 'player'
        self.playing = False

    def status(self, entry=None):
        st = {'isPlaying': self.playing, 'isPaused': False, 'media': None, 'time': 0.0, 'duration': 0}
        return st[entry] if entry else st

    def isPlaying(self):
        return self.playing

    def stop(self):
        self.playing = False


class FakePort:
    def send(self, msg):
        pass

    def close(self):
        pass


def hello(uptime_ms, role=0, sq=2):
    """v2 HELLO with the 2.0.1 syncQuality and 2.0.3 lr trailers (payload after F0, before F7)."""
    up = [(uptime_ms >> 24) & 0xFF, (uptime_ms >> 16) & 0xFF, (uptime_ms >> 8) & 0xFF, uptime_ms & 0xFF]
    return [0x7D, CMD_HELLO] + encode7(list(b'2.0.5'.ljust(8, b'\x00'))) + encode7(up) + [1, role, 2, sq, 0]


def running_state(uptime_ms, slaves):
    """One RUNNING_STATE table, one chunk per slave as the firmware sends it; slaves = [(last_seen_ms, sq)].
    No slave = one empty chunk."""
    up = encode7([(uptime_ms >> 24) & 0xFF, (uptime_ms >> 16) & 0xFF, (uptime_ms >> 8) & 0xFF, uptime_ms & 0xFF])
    if not slaves:
        return [[0x7D, CMD_RUNNING_STATE] + up + [1, 0, 0, 1, 0]]
    frames = []
    for i, (seen, sq) in enumerate(slaves):
        rec = ([0xA0, 0xB1, 0xC2, 0xD3, 0xE4, i] + list(b'hplayer2'.ljust(16, b'\x00'))
               + list(b'2.0.5'.ljust(8, b'\x00'))
               + [(seen >> 24) & 0xFF, (seen >> 16) & 0xFF, (seen >> 8) & 0xFF, seen & 0xFF, 1, 3, sq])
        frames.append([0x7D, CMD_RUNNING_STATE] + up + [1, len(slaves), i, len(slaves), 1] + encode7(rec))
    return frames


@pytest.fixture
def iface(monkeypatch):
    hplayer = HPlayer2(mediaPath=[])
    player = FakePlayer()
    hplayer._players['player'] = player
    i = NowdeInterface(hplayer, player, mode='auto')
    lines = []
    monkeypatch.setattr(i, 'log', lambda *a: lines.append(' '.join(str(x) for x in a)))
    i.lines = lines
    i.fakeplayer = player
    return i


def beats(i):
    return [l for l in i.lines if l.startswith('HEARTBEAT')]


def link(i, at, out=True):
    """What the listener does on a successful connect, minus the ports."""
    i.port = FakePort()
    i.out = FakePort() if out else None
    i._connected_at = at
    i._linkDownSince = None


def test_fmt_age():
    assert [fmt_age(x) for x in (None, 0.4, 42, 61, 1020, 7200 + 180)] == ['-', '0.4s', '42s', '61s', '17m', '2h03m']


def test_silent_before_the_first_link(iface):
    t = time.time()
    for k in range(5):
        iface._heartbeat(t + k * 61)
    assert beats(iface) == []


def test_slave_one_line_a_minute_with_sq_uptime_and_hellos(iface):
    t = time.time()
    link(iface, t)
    iface._heartbeat(t)                         # arms the clock: first line one interval after the link
    for k in range(30):                         # a 2.0.1+ slave node answers each 2 s probe with a HELLO
        iface._handle_sysex(hello(3_600_000 + k * 2000, role=0, sq=2))
    assert iface.role == 'slave'
    iface.lastCC, iface.fakeplayer.playing = 3, True
    iface._heartbeat(t + 59)
    assert beats(iface) == []                   # not yet a minute
    iface._heartbeat(t + 60)
    b = beats(iface)
    assert len(b) == 1
    assert b[0].startswith('HEARTBEAT slave: sq=2 hellos=30 heard=')
    assert 'node-up=60m' in b[0] and b[0].endswith('idx=3 playing')
    # the next minute counts afresh, and only one line per minute however often it is called
    for k in range(300):
        iface._heartbeat(t + 60 + k * 0.2)
    assert len(beats(iface)) == 1
    iface._heartbeat(t + 120)
    assert 'hellos=0' in beats(iface)[-1]


def test_slave_sq_zero_and_silence_guard_show(iface):
    t = time.time()
    link(iface, t)
    iface._heartbeat(t)
    iface._handle_sysex(hello(5000, role=0, sq=0))
    iface._guardStopped = True
    iface.isStopped = True
    iface._heartbeat(t + 60)
    line = beats(iface)[-1]
    assert 'sq=0 hellos=1' in line and line.endswith('stopped (silence guard)')


def test_master_counts_slaves_locked_and_the_stalest(iface):
    t = time.time()
    link(iface, t)
    iface._heartbeat(t)
    iface._handle_sysex(hello(1000, role=1))
    assert iface.isMaster()
    for _ in range(58):                         # 1 Hz poll, one table each
        for f in running_state(7_380_000, [(300, 2), (1200, 2), (9000, 1)]):
            iface._handle_sysex(f)
    iface._lastSent = (3, True, None)
    iface._heartbeat(t + 60)
    line = beats(iface)[-1]
    assert line.startswith('HEARTBEAT master: slaves=3 locked=2 oldest=9.0s tables=58 heard=')
    assert 'node-up=2h03m' in line and line.endswith('idx=3 playing')


def test_master_empty_mesh_still_counts_tables(iface):
    t = time.time()
    link(iface, t)
    iface._heartbeat(t)
    iface._handle_sysex(hello(1000, role=1))
    for _ in range(60):
        for f in running_state(65_000, []):
            iface._handle_sysex(f)
    iface._heartbeat(t + 60)
    line = beats(iface)[-1]
    assert 'slaves=0 locked=0 oldest=- tables=60' in line
    assert line.endswith('idx=- (nothing sent)')


def test_link_down_is_said_every_minute(iface):
    t = time.time()
    link(iface, t)
    iface._heartbeat(t)
    iface._handle_sysex(hello(1000, role=0))
    iface._close_ports()
    iface._linkDownSince = t + 5                # pin the clocks the close stamped with time.time()
    iface._lastHeardAt = t + 4
    iface._heartbeat(t + 60)
    iface._heartbeat(t + 120)
    b = beats(iface)
    assert len(b) == 2
    assert b[0] == 'HEARTBEAT slave: link DOWN 55s, node last heard 56s ago'
    assert b[1] == 'HEARTBEAT slave: link DOWN 115s, node last heard 116s ago'
