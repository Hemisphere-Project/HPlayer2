"""hplayer2#t-112: the HELLO tail at payload 20..25 -- linkLost, ms since the last accepted
MEDIA_SYNC, radio watchdog restarts (2.0.5), syncGaps (v2.2) -- is read by length, and a slave's
journal says it: on every HELLO line and in the minute heartbeat. A slave node answers each 2 s
keepalive with a fresh HELLO, so the stream age is live. Older HELLOs parse as before.
Real frames go through the interface's own SysEx handler; nothing is started."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("mido")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                        # noqa: E402
from core.interfaces.nowde import (                             # noqa: E402
    NowdeInterface, encode7, parse_hello, fmt_link, CMD_HELLO, SYNC_AGE_CAP,
)


def payload(role=0, sq=2, link=None, gaps=None, v24=False):
    """HELLO payload after the command byte: 2.0.3 base (20 bytes), then link = (lost, ms, wd)
    for the 2.0.5 tail, gaps for v2.2, v24 for the buildId + 2.4 trailer behind them."""
    up = [0x00, 0x36, 0xEE, 0x80]                   # 3 600 000 ms
    d = encode7(list(b'2.4.1'.ljust(8, b'\x00'))) + encode7(up) + [3, role, 1, sq, 0]
    if link is not None:
        lost, ms, wd = link
        d += [1 if lost else 0, (ms >> 7) & 0x7F, ms & 0x7F, wd]
        if gaps is not None:
            d += [(gaps >> 7) & 0x7F, gaps & 0x7F]
            if v24:
                d += encode7([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0])
                d += [2] + list(b'CD83FC') + [61]
    return d


# ---------------------------------------------------------------- parser


def test_the_2_0_5_tail_reads_by_length():
    info = parse_hello(payload(link=(False, 240, 0)))
    assert len(payload(link=(False, 240, 0))) == 24  # 28 bytes on the wire
    assert info['link_lost'] is False and info['ms_since_sync'] == 240 and info['watchdog_restarts'] == 0
    assert 'sync_gaps' not in info


def test_the_v2_2_gaps_and_the_14_bit_age():
    info = parse_hello(payload(link=(True, 9000, 3), gaps=1234))
    assert info['link_lost'] is True and info['ms_since_sync'] == 9000
    assert info['watchdog_restarts'] == 3 and info['sync_gaps'] == 1234
    capped = parse_hello(payload(link=(False, SYNC_AGE_CAP, 0), gaps=SYNC_AGE_CAP))
    assert capped['ms_since_sync'] == 16383 and capped['sync_gaps'] == 16383


def test_the_full_2_4_frame_still_reads_its_own_trailer():
    d = payload(link=(False, 120, 1), gaps=7, v24=True)
    assert len(d) == 44
    info = parse_hello(d)
    assert info['ms_since_sync'] == 120 and info['sync_gaps'] == 7 and info['watchdog_restarts'] == 1
    assert info['gen'] == 2 and info['node_id'] == 'CD83FC' and info['rssi'] == -61


def test_older_and_cut_hellos_are_unchanged():
    old = parse_hello(payload())                    # 2.0.3: stops at lr
    assert old['lr'] == 0 and not any(k in old for k in ('link_lost', 'ms_since_sync', 'sync_gaps'))
    cut = parse_hello(payload(link=(False, 240, 0))[:23])      # one byte short of the 2.0.5 tail
    assert 'link_lost' not in cut and 'watchdog_restarts' not in cut
    half = parse_hello(payload(link=(False, 240, 0), gaps=5)[:25])
    assert half['ms_since_sync'] == 240 and 'sync_gaps' not in half


# ---------------------------------------------------------------- the line


def test_fmt_link():
    assert fmt_link({}) == ''
    assert fmt_link(parse_hello(payload(link=(False, 240, 0), gaps=12))) == ' stream=0.2s gaps=12 wd=0'
    assert fmt_link(parse_hello(payload(link=(False, 240, 2)))) == ' stream=0.2s wd=2'
    lost = parse_hello(payload(link=(True, SYNC_AGE_CAP, 1), gaps=40))
    assert fmt_link(lost) == ' LINK-LOST stream=16s+ gaps=40 wd=1'
    assert fmt_link(lost, master=True) == ' wd=1'  # a master's node is the sender: no stream to age


# ---------------------------------------------------------------- the journal


class FakePlayer:
    name = 'player'
    playing = False

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


def hello(**kw):
    return [0x7D, CMD_HELLO] + payload(**kw)


def hellos(i):
    return [l for l in i.lines if l.startswith('HELLO')]


def test_every_slave_hello_line_says_the_stream(iface):
    iface._handle_sysex(hello(link=(False, 180, 0), gaps=3))
    assert iface.role == 'slave'
    assert hellos(iface)[-1].endswith(' stream=0.2s gaps=3 wd=0')
    iface._handle_sysex(hello(link=(True, SYNC_AGE_CAP, 2), gaps=9))
    assert hellos(iface)[-1].endswith(' LINK-LOST stream=16s+ gaps=9 wd=2')


def test_a_master_hello_line_says_only_its_watchdog(iface):
    iface._handle_sysex(hello(role=1, link=(False, SYNC_AGE_CAP, 0), gaps=0))
    assert iface.isMaster()
    line = hellos(iface)[-1]
    assert line.endswith(' wd=0') and 'stream=' not in line and 'LINK-LOST' not in line


def test_an_older_node_hello_line_is_unchanged(iface):
    iface._handle_sysex(hello())
    line = hellos(iface)[-1]
    assert 'stream=' not in line and 'wd=' not in line and line.endswith('board=devkit')


def test_the_slave_heartbeat_carries_the_last_hellos_tail(iface):
    t = time.time()
    iface.port, iface.out, iface._connected_at, iface._linkDownSince = FakePort(), FakePort(), t, None
    iface._heartbeat(t)
    for k in range(30):
        iface._handle_sysex(hello(link=(False, 100 + k, 0), gaps=12))
    iface.lastCC, iface.fakeplayer.playing = 3, True
    iface._heartbeat(t + 60)
    line = [l for l in iface.lines if l.startswith('HEARTBEAT')][-1]
    assert line.startswith('HEARTBEAT slave: sq=2 hellos=30 heard=')
    assert ' stream=0.1s gaps=12 wd=0 node-up=60m ' in line and line.endswith('idx=3 playing')


def test_a_shorter_hello_drops_the_last_tail(iface):
    """A node swapped for an older one on the same link: its HELLO must not inherit the tail."""
    iface._handle_sysex(hello(link=(True, 9000, 4), gaps=50))
    assert iface.node['watchdog_restarts'] == 4
    iface._handle_sysex(hello())
    assert not any(k in iface.node for k in ('link_lost', 'ms_since_sync', 'watchdog_restarts', 'sync_gaps'))
    assert fmt_link(iface.node) == ''
