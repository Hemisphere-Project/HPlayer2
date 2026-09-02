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


def test_media_index_of():
    assert media_index_of('/data/media/7_intro.mp4') == 7
    assert media_index_of('07_intro.mp4') == 7
    assert media_index_of('007_intro.mp4') == 7
    assert media_index_of('127_x.mov') == 127
    assert media_index_of('128_x.mov') == 0
    assert media_index_of('0_mire.mp4') == 0
    assert media_index_of('intro.mp4') == 0
    assert media_index_of(None) == 0
