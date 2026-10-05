"""Byte-exact checks of the Nowde SysEx helpers against the MillluBridge Bridge encoder
(Bridge/src/midi/output_manager.py) and the firmware parsers (Nowde src/sysex.cpp)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.interfaces.nowde import (  # noqa: E402
    encode7, decode7, build_media_sync, build_change_receiver_layer, build_simple,
    parse_hello, parse_config_state, parse_running_state, media_index_of,
)


def bridge_encode_7bit(data_bytes):
    """Verbatim port of Bridge/src/midi/output_manager.py::encode_7bit (reference)."""
    result = []
    i = 0
    while i < len(data_bytes):
        chunk_size = min(7, len(data_bytes) - i)
        msb_byte = 0
        for j in range(chunk_size):
            if data_bytes[i + j] & 0x80:
                msb_byte |= (1 << j)
        result.append(msb_byte)
        for j in range(chunk_size):
            result.append(data_bytes[i + j] & 0x7F)
        i += chunk_size
    return result


def bridge_media_sync(layer_name, media_index, position_ms, state):
    """Verbatim port of Bridge::send_media_sync message assembly (F0..F7 included)."""
    layer_bytes = (layer_name[:16] + '\x00' * 16)[:16].encode('ascii')
    media_index = max(0, min(127, media_index))
    state_byte = 1 if state == 'playing' else 0
    position_bytes_raw = [(position_ms >> 24) & 0xFF, (position_ms >> 16) & 0xFF,
                          (position_ms >> 8) & 0xFF, position_ms & 0xFF]
    return ([0xF0, 0x7D, 0x10] + list(layer_bytes) + [media_index]
            + bridge_encode_7bit(position_bytes_raw) + [state_byte] + [0xF7])


def test_encode7_matches_bridge_and_roundtrips():
    for raw in ([], [0x80], [1, 2, 3], list(range(256)), [0xFF] * 36, [0x12, 0x80, 0x7F, 0x00, 0xAA, 0x55, 0x81, 0x01]):
        enc = encode7(raw)
        assert enc == bridge_encode_7bit(raw)
        assert all(b < 0x80 for b in enc)
        assert decode7(enc) == raw


def test_media_sync_is_byte_exact_with_bridge():
    for layer, idx, pos, playing in [('hplayer2', 7, 0, True), ('L', 127, 0xDEADBEEF, False),
                                     ('a-very-long-layer-name', 1, 123456, True), ('x', 0, 0, False)]:
        ours = [0xF0] + build_media_sync(layer, idx, pos, playing) + [0xF7]
        ref = bridge_media_sync(layer, idx, pos, 'playing' if playing else 'stopped')
        assert ours == ref
        assert len(ours) == 27                       # firmware: length >= 27
        assert ours[19] == max(0, min(127, idx))     # firmware reads index at data[19]
        assert ours[25] == (1 if playing else 0)     # and state at data[25]
        # firmware decodes position from data[20..24]
        msb = ours[20]
        pb = [ours[21 + i] | (0x80 if msb & (1 << i) else 0) for i in range(4)]
        assert (pb[0] << 24) | (pb[1] << 16) | (pb[2] << 8) | pb[3] == (pos & 0xFFFFFFFF)


def test_change_receiver_layer_layout():
    mac = [0xA0, 0xB1, 0xC2, 0xD3, 0xE4, 0xF5]
    msg = [0xF0] + build_change_receiver_layer(mac, 'stage') + [0xF7]
    assert len(msg) == 30                            # F0 7D 11 mac(7) layer(19) F7; firmware checks length >= 29
    assert decode7(msg[3:10]) == mac
    layer = decode7(msg[10:29])
    assert bytes(layer).rstrip(b'\x00') == b'stage'


def test_simple_commands():
    assert build_simple(0x01) == [0x7D, 0x01]
    assert build_simple(0x08, 1) == [0x7D, 0x08, 1]


def test_parse_hello_v1_and_v2():
    version = list(b'1.2'.ljust(8, b'\x00'))
    uptime = [0x00, 0x01, 0x86, 0xA0]                 # 100000 ms
    body = encode7(version) + encode7(uptime) + [1]
    v1 = parse_hello(body)
    assert v1 == {'version': '1.2', 'uptime': 100000, 'boot_reason': 'POWERON'}
    v2 = parse_hello(body + [1, 2])
    assert v2['role'] == 'master' and v2['board'] == 'atoms3'
    assert parse_hello(body[:5]) is None


def test_parse_config_state_v1_and_v2():
    assert parse_config_state([0, 3, 0x10]) == {'rf_sim': False, 'rf_sim_delay': 400}
    v2 = parse_config_state([1, 0, 5, 0, 3, 3] + list(b'abc'))
    assert v2['rf_sim'] and v2['rf_sim_delay'] == 5
    assert v2['role'] == 'slave' and v2['board'] == 'atoms3-lite' and v2['layer'] == 'abc'


def test_parse_running_state_chunk():
    uptime = [0, 0, 0x27, 0x10]
    rec = ([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF] + list(b'main'.ljust(16, b'\x00'))
           + list(b'2.0'.ljust(8, b'\x00')) + [0, 0, 0x03, 0xE8] + [1, 9])
    assert len(rec) == 36
    d = encode7(uptime) + [1, 1, 0, 1, 1] + encode7(rec)
    meta, receivers = parse_running_state(d)
    assert meta == {'uptime': 10000, 'synced': True, 'total': 1, 'chunk': 0, 'chunks': 1}
    assert len(receivers) == 1
    r = receivers[0]
    assert r['mac'] == 'AA:BB:CC:DD:EE:FF' and r['layer'] == 'main' and r['version'] == '2.0'
    assert r['last_seen'] == 1000 and r['index'] == 9
    assert r['sync_quality'] == 0xFF                 # pre-2.0.1: no trailer -> unknown


def test_parse_running_state_pre_201_wire_frame():
    """A whole RUNNING_STATE payload (after F0 7D 22) as a pre-2.0.1 master node puts it on the
    wire: chunk 1 of 2, one 42-byte record, laid out by Nowde v2.0.0 sendRunningState. Literal
    bytes, so encode7 cannot agree with itself here."""
    d = [0x0C, 0x00, 0x36, 0x6E, 0x00,                       # uptime 3600000 ms
         0x01, 0x02, 0x01, 0x02, 0x01,                       # synced, total, chunk, chunks, n
         0x38, 0x24, 0x6F, 0x28, 0x1A, 0x31, 0x44, 0x68,
         0x00, 0x70, 0x6C, 0x61, 0x79, 0x65, 0x72, 0x32,
         0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
         0x00, 0x00, 0x32, 0x2E, 0x30, 0x00, 0x00, 0x00,
         0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7A, 0x01,
         0x00, 0x03]
    meta, receivers = parse_running_state(d)
    assert meta == {'uptime': 3600000, 'synced': True, 'total': 2, 'chunk': 1, 'chunks': 2}
    assert len(receivers) == 1
    r = receivers[0]
    assert r['mac'] == '24:6F:28:9A:B1:C4' and r['layer'] == 'hplayer2' and r['version'] == '2.0'
    assert r['last_seen'] == 250 and r['index'] == 3 and r['sync_quality'] == 0xFF


def _running_state_record(mac_last, index, trailer):
    return ([0xA0, 0xB1, 0xC2, 0xD3, 0xE4, mac_last] + list(b'main'.ljust(16, b'\x00'))
            + list(b'2.0.1'.ljust(8, b'\x00')) + [0, 0, 0x01, 0xF4] + [1, index] + trailer)


def test_parse_running_state_reads_every_record_size():
    """42 (pre-2.0.1), 43 (2.0.1 syncQuality) and 45 (v2.2 syncGaps) encoded bytes per record,
    one and two records per chunk: the stride follows the record, the fields never move."""
    for trailer, quality in (([], 0xFF), ([2], 2), ([1, 0x01, 0x2C], 1)):
        recs = [_running_state_record(0x01, 4, trailer), _running_state_record(0x02, 5, trailer)]
        for n in (1, 2):
            d = encode7([0, 0, 0x27, 0x10]) + [1, n, 0, 1, n]
            for rec in recs[:n]:
                d += encode7(rec)
            meta, receivers = parse_running_state(d)
            assert meta['total'] == n
            assert [r['mac'][-2:] for r in receivers] == ['01', '02'][:n]
            assert [r['index'] for r in receivers] == [4, 5][:n]
            assert all(r['last_seen'] == 500 and r['sync_quality'] == quality for r in receivers)


def test_parse_running_state_empty_and_short():
    meta, receivers = parse_running_state(encode7([0, 0, 0, 1]) + [0, 0, 0, 1, 0])
    assert meta['total'] == 0 and receivers == []
    short = encode7(_running_state_record(0x01, 4, []))[:41]          # one byte shy of mac..index
    assert parse_running_state(encode7([0, 0, 0, 1]) + [1, 1, 0, 1, 1] + short)[1] == []
    assert parse_running_state([0] * 9) == (None, [])


def test_media_index_of():
    assert media_index_of('/data/media/7_intro.mp4') == 7
    assert media_index_of('07_intro.mp4') == 7
    assert media_index_of('007_intro.mp4') == 7
    assert media_index_of('127_x.mov') == 127
    assert media_index_of('128_x.mov') == 0
    assert media_index_of('0_mire.mp4') == 0
    assert media_index_of('intro.mp4') == 0
    assert media_index_of(None) == 0


SEQ_LIVE = """Client info
  cur  clients : 5
Client  20 : "Nowde - D19268" [Kernel Legacy]
  Port   0 : "Nowde - D19268 MIDI 1" (RWeX) [In/Out]
    Connecting To: 130:0
    Connected From: 131:0[r:0]
Client 128 : "RtMidiIn Client" [User Legacy]
  Port   0 : "RtMidi input" (-We-) [Out]
Client 130 : "RtMidiIn Client" [User Legacy]
  Port   0 : "RtMidi input" (-We-) [Out]
    Connected From: 20:0
Client 131 : "RtMidiOut Client" [User Legacy]
  Port   0 : "RtMidi output" (R-e-) [In]
    Connecting To: 20:0[r:0]
"""

SEQ_DEAD = """Client  20 : "Nowde - D19268" [Kernel Legacy]
  Port   0 : "Nowde - D19268 MIDI 1" (RWeX) [In/Out]
Client 130 : "RtMidiIn Client" [User Legacy]
  Port   0 : "RtMidi input" (-We-) [Out]
Client 131 : "RtMidiOut Client" [User Legacy]
  Port   0 : "RtMidi output" (R-e-) [In]
"""


def test_alsa_client_of():
    from core.interfaces.nowde import alsa_client_of
    assert alsa_client_of('Nowde - D19268:Nowde - D19268 MIDI 1 20:0') == 20
    assert alsa_client_of('Nowde - SIM') is None


def test_seq_subscriber_is_the_newest_client_fed_by_the_node():
    from core.interfaces.nowde import seq_subscriber_of
    assert seq_subscriber_of(SEQ_LIVE, 20) == 130       # 128 is an older, unsubscribed client
    assert seq_subscriber_of(SEQ_DEAD, 20) is None
    assert seq_subscriber_of('', 20) is None


def test_seq_subscribed_live_then_node_reenumerated():
    from core.interfaces.nowde import seq_subscribed
    assert seq_subscribed(SEQ_LIVE, 130, 20) is True
    # node rebooted: same client 20, same name, our subscription is gone
    assert seq_subscribed(SEQ_DEAD, 130, 20) is False


def test_seq_subscribed_unknown_reads_alive():
    from core.interfaces.nowde import seq_subscribed
    assert seq_subscribed('', 130, 20) is True          # no /proc dump on this platform
    assert seq_subscribed(SEQ_LIVE, None, 20) is True   # we never identified our client
    assert seq_subscribed(SEQ_LIVE, 130, None) is True  # virtual port, no node client
    assert seq_subscribed(SEQ_DEAD, 999, 20) is True    # our client not listed at all
