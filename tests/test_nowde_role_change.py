"""hplayer2#t-106: a Nowde whose role changes while linked switches this player's leg on its
HELLO alone (Nowde 3 pushes one on every role change), and the 2.4 / Nowde 3 HELLO trailer
(gen, nodeId, LR mode, RSSI) plus RUNNING_STATE's slave RSSI are read by length. Real frames
go through the interface's own SysEx handler; nothing is started, no port is opened."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("mido")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                        # noqa: E402
from core.interfaces.nowde import (                             # noqa: E402
    NowdeInterface, encode7, parse_hello, parse_running_state,
    CMD_HELLO, CMD_RUNNING_STATE, CMD_QUERY_CONFIG, CMD_SET_LR,
)


def hello_payload(uptime_ms=3_600_000, role=0, board=1, sq=2, lr=0, v24=None):
    """HELLO payload after the command byte. v24 = (gen, node_id, rssi_minus_dbm) appends the
    2.0.5 / v2.2 / v2.1 tails (zeros) and then the 2.4 trailer, as the rc firmware lays it out."""
    up = [(uptime_ms >> 24) & 0xFF, (uptime_ms >> 16) & 0xFF, (uptime_ms >> 8) & 0xFF, uptime_ms & 0xFF]
    d = encode7(list(b'2.4-rc1'.ljust(8, b'\x00'))) + encode7(up) + [3, role, board, sq, lr]
    if v24 is not None:
        gen, node_id, rssi = v24
        d += [0, 0x7F, 0x7F, 0]                     # [20] linkLost [21..22] stream age [23] wd restarts
        d += [0, 0]                                 # [24..25] syncGaps
        d += encode7([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0])   # [26..35] buildId
        d += [gen] + list(node_id.encode('ascii')) + [rssi]
    return d


def hello(**kw):
    return [0x7D, CMD_HELLO] + hello_payload(**kw)


def record(mac_last, rssi=None, gaps=True):
    rec = ([0xA0, 0xB1, 0xC2, 0xD3, 0xE4, mac_last] + list(b'hplayer2'.ljust(16, b'\x00'))
           + list(b'2.4-rc1'.ljust(8, b'\x00')) + [0, 0, 0x01, 0xF4, 1, 3, 2])
    if gaps:
        rec += [0, 5]                               # v2.2 syncGaps
    if rssi is not None:
        rec += [rssi]                               # 2.4: -dBm
    return rec


def running_state(records):
    up = encode7([0, 0, 0x27, 0x10])
    return [[0x7D, CMD_RUNNING_STATE] + up + [1, len(records), i, len(records), 1] + encode7(rec)
            for i, rec in enumerate(records)]


# ---------------------------------------------------------------- parsers


def test_hello_reads_the_24_trailer_by_length():
    d = hello_payload(role=3, lr=2, v24=(3, '26B8F8', 67))
    assert len(d) == 44                             # 48 bytes on the wire with F0 7D 20 .. F7
    info = parse_hello(d)
    assert info['role'] == 'standby' and info['board'] == 'devkit'
    assert info['lr'] == 2
    assert info['gen'] == 3 and info['node_id'] == '26B8F8' and info['rssi'] == -67


def test_hello_rssi_zero_is_unknown_and_old_frames_stay_valid():
    assert parse_hello(hello_payload(v24=(2, 'CD83FC', 0)))['rssi'] is None
    v203 = parse_hello(hello_payload(lr=1))         # 2.0.3: 20-byte payload, lr on/off
    assert v203['lr'] == 1 and 'gen' not in v203 and 'node_id' not in v203 and 'rssi' not in v203
    longer = parse_hello(hello_payload(v24=(3, '26B8F8', 70)) + [9, 9, 9])   # a later trailer
    assert longer['rssi'] == -70 and longer['node_id'] == '26B8F8'
    cut = parse_hello(hello_payload(v24=(3, '26B8F8', 70))[:40])            # gen + 3 id chars
    assert cut['gen'] == 3 and 'node_id' not in cut and 'rssi' not in cut


def test_running_state_reads_the_slave_rssi():
    meta, rs = parse_running_state(running_state([record(1, rssi=72)])[0][2:])
    assert len(encode7(record(1, rssi=72))) == 46
    assert rs[0]['rssi'] == -72 and rs[0]['index'] == 3 and rs[0]['sync_quality'] == 2
    assert parse_running_state(running_state([record(1, rssi=0)])[0][2:])[1][0]['rssi'] is None
    assert parse_running_state(running_state([record(1)])[0][2:])[1][0]['rssi'] is None       # v2.2
    assert parse_running_state(running_state([record(1, gaps=False)])[0][2:])[1][0]['rssi'] is None


# ---------------------------------------------------------------- the live leg switch


class FakePlayer:
    def __init__(self):
        self.name = 'player'
        self.playing = False
        self.speeds = []

    def status(self, entry=None):
        st = {'isPlaying': self.playing, 'isPaused': False, 'media': '/data/media/03_cue.mp4' if self.playing else None,
              'time': 12.0, 'duration': 60.0}
        return st[entry] if entry else st

    def isPlaying(self):
        return self.playing

    def stop(self):
        self.playing = False

    def speed(self, s):
        self.speeds.append(s)


class FakeOut:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(list(msg.data))

    def close(self):
        pass


def make(monkeypatch, mode='auto'):
    hplayer = HPlayer2(mediaPath=[])
    player = FakePlayer()
    hplayer._players['player'] = player
    i = NowdeInterface(hplayer, player, mode=mode)
    i.lines, i.events = [], []
    monkeypatch.setattr(i, 'log', lambda *a: i.lines.append(' '.join(str(x) for x in a)))
    monkeypatch.setattr(i, 'emit', lambda ev, *a: i.events.append((ev,) + a))
    i.fakeplayer = player
    i.port, i.out = FakeOut(), FakeOut()            # linked: what the listener holds after a connect
    i._connected_at = time.time()
    return i


def test_slave_promoted_on_a_live_link_drops_the_slave_leg(monkeypatch):
    i = make(monkeypatch)
    port = i.port
    i._handle_sysex(hello(role=0))
    assert i.role == 'slave'
    # mid-chase: the servo holds 1.05x, a CC#100 is in force, a guard clock is running
    i.fakeplayer.playing = True
    i.drifter.lastSpeed = 1.05
    i.lastCC, i._sqZeroSince, i._guardStopped = 3, time.time(), True
    i.out.sent.clear()

    i._handle_sysex(hello(role=1))                  # the node turned master, no relink

    assert i.role == 'master' and i.port is port
    assert ('role', 'master') in i.events
    assert i.fakeplayer.speeds == [1.0]             # the servo gave the speed back
    assert i.lastCC is None and i._sqZeroSince is None and not i._guardStopped
    assert [0x7D, CMD_QUERY_CONFIG] in i.out.sent   # the master leg's handshake
    assert any('was SLAVE on this link' in l for l in i.lines)
    i.out.sent.clear()
    i._master_send()                                # the first MEDIA_SYNC goes at once
    assert i.out.sent and i.out.sent[0][1] == 0x10


def test_master_demoted_to_standby_runs_the_slave_leg(monkeypatch):
    i = make(monkeypatch)
    i._handle_sysex(hello(role=1, v24=(3, '26B8F8', 0)))
    assert i.role == 'master'
    i.fakeplayer.playing = True
    for f in running_state([record(1, rssi=60), record(2, rssi=81)]):
        i._handle_sysex(f)
    assert len(i.receivers) == 2
    i._master_send()
    assert i._lastSent is not None
    i.events.clear()

    i._handle_sysex(hello(role=3, v24=(3, '26B8F8', 58)))     # yielded: standby

    assert i.role == 'slave' and i.node['role'] == 'standby'
    assert i.receivers == [] and i._lastSent is None and not i.mesh_synced
    assert ('receivers', []) in i.events and ('role', 'slave') in i.events
    i.out.sent.clear()
    i._master_send()
    assert i.out.sent == []                         # no MEDIA_SYNC from a slave
    i.handle_media_selection(0)                     # the new master's CC#100 acts
    assert i.lastCC == 0


def test_a_repeated_role_is_not_a_switch(monkeypatch):
    i = make(monkeypatch)
    i._handle_sysex(hello(role=0))
    i.lastCC = 5
    i.events.clear()
    for _ in range(3):
        i._handle_sysex(hello(role=0))
    i._handle_sysex(hello(role=3))                  # standby is the slave leg already
    assert i.role == 'slave' and i.lastCC == 5
    assert not any(e[0] == 'role' for e in i.events)


def test_forced_slave_never_follows_a_master_node(monkeypatch):
    i = make(monkeypatch, mode='slave')             # the Millumin setting
    i._handle_sysex(hello(role=1))
    assert i.role == 'slave'
    assert [0x7D, CMD_QUERY_CONFIG] not in i.out.sent


def test_soft_reset_sends_back_the_lr_mode_it_read(monkeypatch):
    i = make(monkeypatch)
    i._handle_sysex(hello(role=0, lr=2, v24=(2, 'CD83FC', 0)))
    i.out.sent.clear()
    assert i._node_soft_reset('test')
    assert i.out.sent == [[0x7D, CMD_SET_LR, 2]]    # 500k stays 500k, never 1 = 250k


def test_status_carries_the_hello_identity(monkeypatch):
    i = make(monkeypatch)
    i._handle_sysex(hello(role=1, lr=1, v24=(2, 'CD83FC', 0)))
    for f in running_state([record(1, rssi=60), record(2, rssi=81), record(3)]):
        i._handle_sysex(f)
    i._lastStatus = 0.0
    i._push_status()
    st = [e[1] for e in i.events if e[0] == 'status'][-1]
    assert st['ident'] == {'gen': 2, 'node_id': 'CD83FC', 'lr': 1, 'rssi': None}
    assert st['weakest_rssi'] == -81
