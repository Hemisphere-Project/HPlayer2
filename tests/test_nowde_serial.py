"""Nowde over serial (hplayer2#t-105): the byte stream a node writes on its UART -> the very
messages the USB-MIDI callback receives. No hardware: bytes in, messages out."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mido = pytest.importorskip("mido")

from core.interfaces.nowde import (  # noqa: E402
    NowdeStreamParser, SERIAL_SYSEX_MAX, CMD_HELLO, encode7, parse_hello,
)


def hello_frame(uptime_ms=3_600_000, role=0, board=1):
    version = list(b'2.4.0'.ljust(8, b'\x00'))
    up = [(uptime_ms >> s) & 0xFF for s in (24, 16, 8, 0)]
    return [0xF0, 0x7D, CMD_HELLO] + encode7(version) + encode7(up) + [1, role, board, 2, 0] + [0xF7]


def feed_bytewise(parser, data):
    out = []
    for b in data:
        out.extend(parser.messages([b]))
    return out


def test_hello_reassembled_from_single_bytes():
    p = NowdeStreamParser()
    msgs = feed_bytewise(p, hello_frame())
    assert [m.type for m in msgs] == ['sysex']
    data = list(msgs[0].data)
    assert data[0] == 0x7D and data[1] == CMD_HELLO
    info = parse_hello(data[2:])
    assert info['version'] == '2.4.0' and info['uptime'] == 3_600_000 and info['role'] == 'slave'
    assert p.dropped == 0


def test_cc100_cc7_and_transport():
    msgs = NowdeStreamParser().messages([0xB0, 100, 3, 0xB0, 7, 80, 0xFA, 0xFC])
    assert [(m.type, getattr(m, 'control', None), getattr(m, 'value', None)) for m in msgs] == [
        ('control_change', 100, 3), ('control_change', 7, 80), ('start', None, None), ('stop', None, None)]


def test_mtc_quarter_frames():
    pieces = [0xF1, 0x00, 0xF1, 0x12, 0xF1, 0x24, 0xF1, 0x30, 0xF1, 0x41, 0xF1, 0x50, 0xF1, 0x60, 0xF1, 0x72]
    msgs = NowdeStreamParser().messages(pieces)
    assert [(m.type, m.frame_type, m.frame_value) for m in msgs] == [
        ('quarter_frame', i, v) for i, v in enumerate([0, 2, 4, 0, 1, 0, 0, 2])]


def test_300_byte_sysex_in_odd_slices():
    body = [(i * 7) & 0x7F for i in range(298)]
    frame = [0xF0] + body + [0xF7]
    assert len(frame) == 300
    p = NowdeStreamParser()
    msgs = []
    for i in range(0, len(frame), 13):
        msgs.extend(p.messages(frame[i:i + 13]))
    assert len(msgs) == 1 and list(msgs[0].data) == body and p.dropped == 0


def test_sysex_at_the_cap_passes_one_more_byte_is_dropped_whole():
    p = NowdeStreamParser()
    at_cap = [0xF0] + [0x11] * (SERIAL_SYSEX_MAX - 2) + [0xF7]
    over = [0xF0] + [0x22] * (SERIAL_SYSEX_MAX - 1) + [0xF7]
    msgs = p.messages(at_cap + over + [0xB0, 100, 2])
    assert [m.type for m in msgs] == ['sysex', 'control_change']
    assert len(msgs[0].data) == SERIAL_SYSEX_MAX - 2
    assert p.oversize == 1 and p.dropped == len(over)


def test_running_status_accepted():
    msgs = NowdeStreamParser().messages([0xB0, 100, 3, 100, 5, 7, 90])
    assert [(m.control, m.value) for m in msgs] == [(100, 3), (100, 5), (7, 90)]


def test_system_common_cancels_running_status():
    p = NowdeStreamParser()
    msgs = p.messages([0xB0, 100, 1, 0xF1, 0x23, 0x05])
    assert [m.type for m in msgs] == ['control_change', 'quarter_frame']
    assert p.dropped == 1


def test_realtime_inside_sysex_and_inside_a_cc():
    p = NowdeStreamParser()
    frame = hello_frame()
    stream = frame[:5] + [0xF8] + frame[5:] + [0xB0, 0xFE, 100, 4]
    msgs = p.messages(stream)
    assert [m.type for m in msgs] == ['clock', 'sysex', 'active_sensing', 'control_change']
    assert list(msgs[1].data) == frame[1:-1] and msgs[3].value == 4 and p.dropped == 0


def test_garbage_before_any_status_is_dropped_and_counted():
    p = NowdeStreamParser()
    msgs = p.messages([0x12, 0x34, 0xF7, 0xB0, 100, 1])
    assert [(m.control, m.value) for m in msgs] == [(100, 1)]
    assert p.dropped == 3


def test_sysex_cut_by_a_status_is_dropped_then_the_status_reads():
    p = NowdeStreamParser()
    msgs = p.messages([0xF0, 0x7D, 0x01, 0xB0, 100, 2] + hello_frame())
    assert [m.type for m in msgs] == ['control_change', 'sysex']
    assert p.dropped == 3


def test_message_cut_short_by_a_new_status():
    p = NowdeStreamParser()
    msgs = p.messages([0xB0, 100, 0xB0, 100, 6])
    assert [(m.control, m.value) for m in msgs] == [(100, 6)]
    assert p.dropped == 2


# ---- the link on a pty pair: the test holds the node's end -------------------------------------

import select  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

pytest.importorskip("serial")

from core.interfaces.nowde import NowdeSerialLink, CMD_QUERY_RUNNING_STATE, build_simple  # noqa: E402


class PtyNode:
    """The node's end of a pty pair: what it writes, the link reads; what the link writes, it reads."""

    def __init__(self):
        self.master, self._slave = os.openpty()
        self.path = os.ttyname(self._slave)

    def write(self, data):
        os.write(self.master, bytes(data))

    def read(self, n, timeout=2.0):
        out = b''
        end = time.time() + timeout
        while len(out) < n and time.time() < end:
            r, _, _ = select.select([self.master], [], [], 0.05)
            if r:
                out += os.read(self.master, n - len(out))
        return out

    def unplug(self):
        os.close(self.master)
        os.close(self._slave)


@pytest.fixture
def node():
    n = PtyNode()
    yield n
    for fd in (n.master, n._slave):
        try:
            os.close(fd)
        except OSError:
            pass


def wait_for(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def test_link_reads_hello_cc100_and_mtc(node):
    got = []
    link = NowdeSerialLink(node.path, got.append, log=lambda *a: None).open()
    try:
        node.write(hello_frame() + [0xB0, 100, 7] + [0xF1, 0x00, 0xF1, 0x12])
        assert wait_for(lambda: len(got) == 4)
        assert [m.type for m in got] == ['sysex', 'control_change', 'quarter_frame', 'quarter_frame']
        assert got[1].value == 7
    finally:
        link.close()


def test_link_writes_sysex_raw(node):
    link = NowdeSerialLink(node.path, lambda m: None, log=lambda *a: None).open()
    try:
        assert link.send(mido.Message('sysex', data=build_simple(CMD_QUERY_RUNNING_STATE)))
        assert node.read(4) == bytes([0xF0, 0x7D, CMD_QUERY_RUNNING_STATE, 0xF7])
    finally:
        link.close()


def test_link_300_byte_sysex_through_the_tty(node):
    got = []
    link = NowdeSerialLink(node.path, got.append, log=lambda *a: None).open()
    try:
        body = [(i * 5) & 0x7F for i in range(298)]
        node.write([0xF0] + body[:100])
        time.sleep(0.05)
        node.write(body[100:] + [0xF7])
        assert wait_for(lambda: len(got) == 1)
        assert list(got[0].data) == body
    finally:
        link.close()


def test_unplug_marks_the_link_broken_and_close_is_idempotent(node):
    logs = []
    link = NowdeSerialLink(node.path, lambda m: None, log=lambda *a: logs.append(' '.join(map(str, a)))).open()
    node.unplug()
    assert wait_for(lambda: link.broken, 3.0)
    assert any('lost' in line for line in logs)
    with pytest.raises(OSError):
        link.write([0xFA])
    link.close()
    link.close()


def test_booted_after_open_reads_the_hello_uptime():
    link = NowdeSerialLink('/dev/null', lambda m: None)
    assert not link.booted_after_open(10)          # never opened: no verdict
    link.opened_at = 100.0
    assert link.booted_after_open(250, now=100.4)       # up 250 ms, opened 400 ms ago: our open reset it
    assert not link.booted_after_open(3_600_000, now=100.4)
    assert not link.booted_after_open(900, now=100.4)   # booted before the open (a fresh plug-in)


class _LineStates:
    """A pyserial Serial that records (DTR, RTS) as the node's auto-reset circuit sees it. open()
    does what the kernel and pyserial 3.5 do: the kernel asserts both, then serialposix.open()
    applies dtr, THEN rts (each its own ioctl)."""
    states = []

    def __init__(self):
        self.port = self.baudrate = self.timeout = None
        self._dtr, self._rts, self._open = True, True, False
        self.in_waiting = 0

    def _set(self, dtr, rts):
        self._dtr, self._rts = dtr, rts
        if self._open:
            self.states.append((dtr, rts))

    dtr = property(lambda self: self._dtr, lambda self, v: self._set(v, self._rts))
    rts = property(lambda self: self._rts, lambda self, v: self._set(self._dtr, v))

    def open(self):
        want_dtr, want_rts = self._dtr, self._rts
        self._open = True
        self.states.append((True, True))        # the kernel raises both on open
        self._set(want_dtr, self._rts)          # pyserial: dtr first ...
        self._set(self._dtr, want_rts)          # ... then rts

    def read(self, n):
        time.sleep(0.01)
        return b''

    def close(self):
        self._open = False


def test_open_never_passes_through_the_reset_state(monkeypatch):
    """EN is pulled low (the node resets) only while RTS is asserted and DTR is not."""
    import core.interfaces.nowde as nowde_mod

    class FakeSerialModule:
        Serial = _LineStates

    _LineStates.states = []
    monkeypatch.setattr(nowde_mod, '_serial', FakeSerialModule)
    link = NowdeSerialLink('/dev/ttyFAKE', lambda m: None, log=lambda *a: None).open()
    link.close()
    assert (False, True) not in _LineStates.states
    assert _LineStates.states[-1] == (False, False)


# ---- the interface on a pinned tty: the same legs as the USB-MIDI loopback -----------------------

from core.engine.hplayer import HPlayer2  # noqa: E402
from core.interfaces.nowde import NowdeInterface, CMD_QUERY_CONFIG, CMD_MEDIA_SYNC  # noqa: E402


class _Player:
    name = 'player'

    def status(self, entry=None):
        st = {'isPlaying': False, 'isPaused': False, 'media': None, 'time': 0.0}
        return st[entry] if entry else st

    def isPlaying(self):
        return False


def _node_cmds(node, seconds):
    """Every SysEx command byte the interface wrote to the node within `seconds`."""
    p, cmds, end = NowdeStreamParser(), [], time.time() + seconds
    while time.time() < end:
        for m in p.messages(node.read(256, timeout=0.05)):
            if m.type == 'sysex' and len(m.data) >= 2 and m.data[0] == 0x7D:
                cmds.append(m.data[1])
    return cmds


def _serial_iface(node, **kw):
    hplayer = HPlayer2(mediaPath=[])
    hplayer.appRunning = True
    player = _Player()
    hplayer._players['player'] = player
    iface = NowdeInterface(hplayer, player, link='serial', serial=node.path, **kw)
    iface.PORT_LOOKUP_INTERVAL = 0.2
    iface.CONNECTION_CHECK_INTERVAL = 0.1
    return hplayer, iface


def test_interface_on_a_pinned_tty_probes_then_runs_the_master_leg(node):
    hplayer, iface = _serial_iface(node)
    roles = []
    hplayer.on('nowde.role')(lambda ev, *a: roles.append(a[0]))
    iface.start()
    try:
        assert wait_for(lambda: iface.isLinked(), 3.0), "the interface did not open the pinned tty"
        assert iface.out is iface.port and iface._resolved_port_name == node.path
        first = _node_cmds(node, 0.5)
        assert CMD_QUERY_RUNNING_STATE in first and CMD_QUERY_CONFIG not in first   # role probe only
        node.write(hello_frame(role=1))
        assert wait_for(lambda: iface.role == 'master', 3.0), "HELLO over serial did not set the role"
        assert roles == ['master']
        later = _node_cmds(node, 1.0)
        assert CMD_QUERY_CONFIG in later and CMD_MEDIA_SYNC in later
    finally:
        iface.quit()


def test_interface_cc100_over_serial_reaches_the_shared_handler(node):
    hplayer, iface = _serial_iface(node, mode='slave')
    seen = []
    iface.handle_media_selection = seen.append
    iface.start()
    try:
        assert wait_for(lambda: iface.isLinked(), 3.0)
        node.write([0xB0, 100, 4])
        assert wait_for(lambda: seen == [4], 2.0)
    finally:
        iface.quit()


def test_interface_unlinks_when_the_tty_goes(node):
    hplayer, iface = _serial_iface(node)
    events = []
    hplayer.on('nowde.unlinked')(lambda ev, *a: events.append(ev))
    iface.start()
    try:
        assert wait_for(lambda: iface.isLinked(), 3.0)
        node.unplug()
        assert wait_for(lambda: not iface.isLinked(), 3.0), "a lost tty left the link up"
        assert wait_for(lambda: events, 1.0)
    finally:
        iface.quit()


def test_link_kind_is_checked():
    with pytest.raises(RuntimeError):
        NowdeInterface(HPlayer2(mediaPath=[]), _Player(), link='usb')


# ---- discovery: VID:PID candidates, a QUERY_RUNNING_STATE probe, HELLO confirms ------------------

import core.interfaces.nowde as nowde_mod  # noqa: E402
from core.interfaces.serialbase import SerialBase  # noqa: E402


class _Port:
    def __init__(self, device, vid=0x10C4, pid=0xEA60):
        self.device, self.vid, self.pid = device, vid, pid
        self.hwid = 'USB VID:PID=%04X:%04X' % (vid, pid)


def _ports(monkeypatch, *ports):
    class FakeListPorts:
        @staticmethod
        def comports():
            return list(ports)
    monkeypatch.setattr(nowde_mod, '_list_ports', FakeListPorts)


def _answer_probes(node, uptime_ms, delay=0.0, role=1):
    """The node: every QUERY_RUNNING_STATE it reads is answered with a HELLO."""
    stop = threading.Event()

    def run():
        p = NowdeStreamParser()
        while not stop.is_set():
            try:
                chunk = node.read(64, timeout=0.05)
            except OSError:
                return
            for m in p.messages(chunk):
                if m.type == 'sysex' and list(m.data[:2]) == [0x7D, CMD_QUERY_RUNNING_STATE]:
                    time.sleep(delay)
                    node.write(hello_frame(uptime_ms=uptime_ms, role=role))
    t = threading.Thread(target=run, daemon=True)
    t.start()

    def halt():                     # joined: a pty's fd numbers are reused by the next test
        stop.set()
        t.join(1.0)
    return halt


def test_discovery_links_the_tty_that_answers_hello(node, monkeypatch):
    _ports(monkeypatch, _Port('/dev/ttyNOPE', 0x2341, 0x0043), _Port(node.path))
    stop = _answer_probes(node, 3_600_000)
    hplayer, iface = _serial_iface(node)
    iface.serial_device = None                      # nothing pinned: discovery decides
    iface.start()
    try:
        assert wait_for(lambda: iface.isLinked() and iface.role == 'master', 6.0)
        assert iface._resolved_port_name == node.path
        assert SerialBase._claims.get(os.path.realpath(node.path)) is iface    # held while linked
    finally:
        iface.quit()
        stop()
    assert os.path.realpath(node.path) not in SerialBase._claims


def test_a_silent_tty_is_probed_once_per_plug_in(node, monkeypatch):
    _ports(monkeypatch, _Port(node.path))
    hplayer, iface = _serial_iface(node)
    iface.SERIAL_PROBE_TIMEOUT = 0.3
    assert iface._discover_serial() is None
    assert node.read(4) == bytes([0xF0, 0x7D, CMD_QUERY_RUNNING_STATE, 0xF7])   # never QUERY_CONFIG
    assert iface._discover_serial() is None
    assert node.read(4, timeout=0.5) == b''                                      # not written again
    assert node.path in iface._notNowde


def test_discovery_skips_a_tty_another_interface_holds(node, monkeypatch):
    _ports(monkeypatch, _Port(node.path))
    hplayer, iface = _serial_iface(node)
    key = os.path.realpath(node.path)
    SerialBase._claims[key] = object()
    try:
        assert iface._discover_serial() is None
        assert node.read(4, timeout=0.3) == b''
    finally:
        del SerialBase._claims[key]


def test_a_node_that_resets_on_open_is_refused_on_the_second_strike(node, monkeypatch):
    _ports(monkeypatch, _Port(node.path))
    stop = _answer_probes(node, uptime_ms=40, delay=0.2)     # up 40 ms, 200 ms after our open
    hplayer, iface = _serial_iface(node)
    logs = []
    iface.log = lambda *a: logs.append(' '.join(map(str, a)))
    try:
        assert iface._discover_serial() is None
        assert node.path not in iface._notNowde                 # one strike: maybe a fresh plug-in
        assert iface._discover_serial() is None
        assert node.path in iface._notNowde                     # twice: refused, with a log line
        assert any('reset when its port opened' in line for line in logs)
    finally:
        stop()


def test_auto_takes_the_serial_node_when_no_midi_node_is_there(node, monkeypatch):
    monkeypatch.setattr(nowde_mod.mido, 'get_input_names', lambda: [])
    _ports(monkeypatch, _Port(node.path))
    stop = _answer_probes(node, 3_600_000, role=0)
    hplayer, iface = _serial_iface(node)
    iface.link, iface.serial_device = 'auto', None
    iface.start()
    try:
        assert wait_for(lambda: iface.isLinked() and iface.role == 'slave', 6.0)
        assert iface._resolved_port_name == node.path
    finally:
        iface.quit()
        stop()


def test_auto_prefers_the_midi_node(node, monkeypatch):
    monkeypatch.setattr(nowde_mod.mido, 'get_input_names', lambda: ['Nowde - ABC123:Nowde - ABC123 MIDI 1 28:0'])
    probed = []
    hplayer, iface = _serial_iface(node)
    iface.link, iface.serial_device = 'auto', None
    iface._discover_serial = lambda: probed.append(1)
    iface.stopped.clear()                           # as start() does, without the threads
    assert iface._wait_for_port().startswith('Nowde - ABC123')
    assert probed == []


def test_status_names_the_link_kind(node):
    hplayer, iface = _serial_iface(node)
    seen = []
    hplayer.on('nowde.status')(lambda ev, *a: seen.append(a[0]))
    iface.start()
    try:
        assert wait_for(lambda: any(st.get('linked') for st in seen), 3.0)
        assert [st['link'] for st in seen if st.get('linked')][-1] == 'serial'
    finally:
        iface.quit()
    iface._lastStatus = 0
    iface._push_status()
    assert seen[-1]['linked'] is False and seen[-1]['link'] is None
