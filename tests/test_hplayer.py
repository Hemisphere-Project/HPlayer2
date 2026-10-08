import core.players as playerlib
from core.engine.hplayer import HPlayer2


def test_add_player_handles_runtime_error(monkeypatch):
    hplayer = HPlayer2(mediaPath=[])

    class FailingPlayer:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("backend missing")

    monkeypatch.setattr(playerlib, "getPlayer", lambda name: FailingPlayer)

    result = hplayer.addPlayer("mpv", "player")
    assert result is None
    assert "player" not in hplayer._players


import os
import signal
import threading
import time

import pytest

import core.engine.hplayer as hplayer_mod


def test_engine_owns_sigint_and_sigterm():
    # czmq installs its own handlers at its first socket unless told not to,
    # and then neither signal reaches Python (kmini-001, 2026-09-04)
    assert os.environ.get('ZSYS_SIGHANDLER') == 'false'
    assert signal.getsignal(signal.SIGINT) is hplayer_mod.signal_handler
    assert signal.getsignal(signal.SIGTERM) is hplayer_mod.signal_handler


def test_sigterm_ends_run_and_arms_the_exit_watchdog(monkeypatch):
    if signal.getsignal(signal.SIGTERM) is not hplayer_mod.signal_handler:
        pytest.fail('no engine SIGTERM handler: the signal would kill the test run')

    armed = []

    class FakeTimer:
        def __init__(self, interval, fn, args=()):
            armed.append(interval)
            self.daemon = False

        def start(self):
            pass

    monkeypatch.setattr(hplayer_mod, 'Timer', FakeTimer)
    hplayer = HPlayer2(mediaPath=[])
    monkeypatch.setattr(hplayer.settings, 'load', lambda *a, **k: None)   # no player to autoplay

    # net: if the signal does not end the loop, end it ourselves and say so
    net = threading.Timer(5.0, hplayer_mod._RUN_EVENT.clear)
    net.start()
    threading.Timer(0.3, os.kill, args=(os.getpid(), signal.SIGTERM)).start()
    t0 = time.monotonic()
    try:
        assert hplayer.run() == 0
    finally:
        net.cancel()
        hplayer_mod._RUN_EVENT.set()

    assert time.monotonic() - t0 < 2.0, 'SIGTERM did not end the main loop'
    assert armed == [10.0]          # the run() finally watchdog
