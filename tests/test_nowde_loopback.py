import re
"""End-to-end loopback of the Nowde master leg through ALSA virtual MIDI ports.

A simulated node ("Nowde - SIM") answers the interface's role probe with a v2 HELLO
(role=master) and checks that the interface then handshakes and streams MEDIA_SYNC
frames reflecting the player's state. Skipped when no ALSA sequencer is reachable.
"""
import os
import sys
import time
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mido = pytest.importorskip("mido")
pytest.importorskip("rtmidi")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                       # noqa: E402
from core.interfaces.nowde import (                            # noqa: E402
    NowdeInterface, encode7, CMD_QUERY_CONFIG, CMD_QUERY_RUNNING_STATE, CMD_MEDIA_SYNC, CMD_HELLO,
)


class FakePlayer:
    """Just enough of core.players.base.BasePlayer for the master leg."""
    def __init__(self):
        self.name = 'player'
        self._status = {'isPlaying': False, 'isPaused': False, 'media': None, 'time': 0.0, 'speed': 1.0,
                        'duration': 0, 'isReady': True}

    def status(self, entry=None):
        return self._status[entry] if entry else dict(self._status)

    def isPlaying(self):
        return self._status['isPlaying'] or self._status['isPaused']

    def isPaused(self):
        return self._status['isPaused']

    def position(self):
        return self._status['time']

    def stop(self):
        self._status.update(isPlaying=False, isPaused=False, media=None, time=0.0)

    def speed(self, s):
        self._status['speed'] = s

    def seekTo(self, ms, exact=False):
        self._status['time'] = ms / 1000.0


def hello_payload(role=1, board=2):
    version = list(b'2.0'.ljust(8, b'\x00'))
    return [0x7D, CMD_HELLO] + encode7(version) + encode7([0, 0, 0x03, 0xE8]) + [1, role, board]


@pytest.fixture
def sim_node():
    """Virtual ALSA ports named like a real node. `to_host` is what the node sends,
    `from_host` collects what the interface sends to the node."""
    received = []
    lock = threading.Lock()

    def on_msg(msg):
        with lock:
            received.append(msg)

    try:
        to_host = mido.open_output('Nowde - SIM', virtual=True, client_name='Nowde - SIM')
        from_host = mido.open_input('Nowde - SIM', virtual=True, client_name='Nowde - SIM', callback=on_msg)
    except Exception as err:                     # no ALSA seq, or rtmidi without virtual ports
        pytest.skip(f"virtual MIDI ports unavailable: {err}")
    yield to_host, received, lock
    from_host.close()
    to_host.close()


def wait_for(pred, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


def sysex_cmds(received, lock, cmd):
    with lock:
        return [list(m.data) for m in received if m.type == 'sysex' and len(m.data) >= 2 and m.data[0] == 0x7D and m.data[1] == cmd]


def test_master_leg_loopback(sim_node):
    to_host, received, lock = sim_node

    hplayer = HPlayer2(mediaPath=[])
    hplayer.appRunning = True
    player = FakePlayer()
    hplayer._players['player'] = player
    hplayer.settings._settings['nowde-layer'] = 'loop'

    iface = NowdeInterface(hplayer, player, mode='auto', port_name=re.compile(r'^Nowde - SIM'))
    iface.PORT_LOOKUP_INTERVAL = 0.2
    roles = []
    hplayer.on('nowde.role')(lambda ev, *a: roles.append(a[0]))
    iface.start()
    try:
        # 1. link + role probe (QUERY_RUNNING_STATE, never QUERY_CONFIG before the role is known)
        assert wait_for(lambda: iface.isLinked() and iface.out is not None), "interface did not link to the sim node"
        assert wait_for(lambda: sysex_cmds(received, lock, CMD_QUERY_RUNNING_STATE)), "no role probe sent"
        assert not sysex_cmds(received, lock, CMD_QUERY_CONFIG)
        assert iface.role is None

        # 2. node says master -> interface handshakes and starts streaming
        to_host.send(mido.Message('sysex', data=hello_payload(role=1, board=2)))
        assert wait_for(lambda: iface.role == 'master'), "HELLO role not applied"
        assert roles == ['master']
        assert iface.node['version'] == '2.0' and iface.node['board'] == 'atoms3'
        assert wait_for(lambda: sysex_cmds(received, lock, CMD_QUERY_CONFIG)), "no QUERY_CONFIG handshake"
        assert wait_for(lambda: sysex_cmds(received, lock, CMD_MEDIA_SYNC)), "no MEDIA_SYNC while stopped"
        stopped = sysex_cmds(received, lock, CMD_MEDIA_SYNC)[-1]
        assert stopped[18] == 0 and stopped[24] == 0          # index 0, state stopped (payload offsets: no F0)

        # 3. player plays 3_piece.mp4 at 1.5 s -> index 3, playing, position 1500
        with lock:
            received.clear()
        player._status.update(isPlaying=True, media='/data/media/3_piece.mp4', time=1.5)
        assert wait_for(lambda: any(f[18] == 3 and f[24] == 1 for f in sysex_cmds(received, lock, CMD_MEDIA_SYNC))), "no playing MEDIA_SYNC"
        frame = [f for f in sysex_cmds(received, lock, CMD_MEDIA_SYNC) if f[18] == 3][-1]
        assert bytes(frame[2:18]).rstrip(b'\x00') == b'loop'
        msb = frame[19]
        pb = [frame[20 + i] | (0x80 if msb & (1 << i) else 0) for i in range(4)]
        assert (pb[0] << 24) | (pb[1] << 16) | (pb[2] << 8) | pb[3] == 1500

        # 4. ~10 Hz while playing
        with lock:
            received.clear()
        time.sleep(1.0)
        n = len(sysex_cmds(received, lock, CMD_MEDIA_SYNC))
        assert 6 <= n <= 14, f"expected ~10 MEDIA_SYNC/s, got {n}"

        # 5. pause reads as stopped on the wire (v2.0 contract)
        player._status.update(isPaused=True)
        assert wait_for(lambda: any(f[24] == 0 for f in sysex_cmds(received, lock, CMD_MEDIA_SYNC)))
    finally:
        iface.quit()


def test_slave_leg_assumes_legacy_node_when_silent(sim_node):
    to_host, received, lock = sim_node
    hplayer = HPlayer2(mediaPath=[])
    hplayer.appRunning = True
    player = FakePlayer()
    hplayer._players['player'] = player
    iface = NowdeInterface(hplayer, player, mode='auto', port_name=re.compile(r'^Nowde - SIM'))
    iface.PORT_LOOKUP_INTERVAL = 0.2
    iface.PROBE_TIMEOUT = 0.5
    iface.start()
    try:
        assert wait_for(lambda: iface.role == 'slave', timeout=6.0), "silent node should resolve to a legacy slave"
        assert not sysex_cmds(received, lock, CMD_QUERY_CONFIG)      # never flip a v1.2 receiver into a sender
        assert not sysex_cmds(received, lock, CMD_MEDIA_SYNC)
    finally:
        iface.quit()
