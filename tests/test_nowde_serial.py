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
