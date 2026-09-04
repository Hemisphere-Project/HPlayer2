import re
"""Slave leg through ALSA virtual MIDI ports: a simulated v1.2 node streams CC#100 + MTC and
the interface must select the clip by numeric prefix and feed the Drifter with the timecode."""
import os
import sys
import time
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

mido = pytest.importorskip("mido")
pytest.importorskip("rtmidi")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                       # noqa: E402
from core.interfaces.nowde import NowdeInterface               # noqa: E402
from test_nowde_loopback import FakePlayer, wait_for           # noqa: E402


@pytest.fixture
def sim_node():
    try:
        to_host = mido.open_output('Nowde - SIM', virtual=True, client_name='Nowde - SIM')
        from_host = mido.open_input('Nowde - SIM', virtual=True, client_name='Nowde - SIM')
    except Exception as err:
        pytest.skip(f"virtual MIDI ports unavailable: {err}")
    yield to_host
    from_host.close()
    to_host.close()


def quarter_frames(to_host, pos_ms, fps=30):
    total = int(pos_ms * fps / 1000)
    fr, sec, mn, hr = total % fps, (total // fps) % 60, (total // (fps * 60)) % 60, (total // (fps * 3600)) % 24
    pieces = [fr & 0xF, (fr >> 4) & 1, sec & 0xF, (sec >> 4) & 3, mn & 0xF, (mn >> 4) & 3, hr & 0xF, ((hr >> 4) & 1) | (3 << 1)]
    for i, v in enumerate(pieces):
        to_host.send(mido.Message('quarter_frame', frame_type=i, frame_value=v))


def test_slave_leg_cc100_and_mtc(sim_node, monkeypatch):
    to_host = sim_node
    hplayer = HPlayer2(mediaPath=[])
    hplayer.appRunning = True
    player = FakePlayer()
    hplayer._players['player'] = player

    plays = []
    monkeypatch.setattr(hplayer.playlist, 'play', lambda pattern=None, *a, **k: plays.append(pattern))
    monkeypatch.setattr(hplayer.playlist, 'size', lambda: 1 if plays else 0)

    iface = NowdeInterface(hplayer, player, mode='auto', port_name=re.compile(r'^Nowde - SIM'))
    iface.PORT_LOOKUP_INTERVAL = 0.2
    iface.PROBE_TIMEOUT = 0.5
    ticks = []
    monkeypatch.setattr(iface.drifter, 'tick', lambda clock: ticks.append(clock))
    armed = []
    monkeypatch.setattr(iface.drifter, 'arm', lambda: armed.append(True))
    iface.start()
    try:
        assert wait_for(lambda: iface.isLinked()), "interface did not link"

        # CC#100 = 7 -> playlist pattern with zero-padding alternatives, drifter armed
        to_host.send(mido.Message('control_change', channel=0, control=100, value=7))
        assert wait_for(lambda: plays), "CC#100 did not trigger playlist.play"
        assert plays[-1] == "(007_*|07_*|7_*)"
        assert armed and not iface.isStopped

        # same value repeated (the node re-sends every second): no second play
        to_host.send(mido.Message('control_change', channel=0, control=100, value=7))
        time.sleep(0.2)
        assert len(plays) == 1

        # MTC quarter-frames at 00:01:05:15 (30 fps) -> drifter.tick(65.5)
        quarter_frames(to_host, 65500)
        assert wait_for(lambda: ticks), "MTC did not reach the drifter"
        assert abs(ticks[-1] - 65.5) < 0.02

        # full-frame SysEx 00:00:10:00 -> tick(10.0)
        to_host.send(mido.Message('sysex', data=[0x7F, 0x7F, 0x01, 0x01, (3 << 5) | 0, 0, 10, 0]))
        assert wait_for(lambda: any(abs(t - 10.0) < 0.02 for t in ticks)), "full-frame did not reach the drifter"

        # silent node: resolves to a legacy slave without ever sending QUERY_CONFIG
        assert wait_for(lambda: iface.role == 'slave', timeout=3.0)

        # CC#100 = 0 -> stop, and MTC is ignored afterwards
        to_host.send(mido.Message('control_change', channel=0, control=100, value=0))
        assert wait_for(lambda: iface.isStopped), "CC#100=0 did not stop"
        n = len(ticks)
        quarter_frames(to_host, 70000)
        time.sleep(0.3)
        assert len(ticks) == n
    finally:
        iface.quit()
