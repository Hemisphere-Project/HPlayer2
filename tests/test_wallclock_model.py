"""Wallclock gap model: a packet is aged once on arrival, then the model runs on the
monotonic clock — a step of our own wall clock during a master's silence must not move it
(hplayer2#t-087). Pure function test: _modelClock reads no instance state."""

import time

from core.interfaces.wallclock import WallclockInterface


def _model(base):
    return WallclockInterface._modelClock(None, base)


def test_model_ignores_a_wall_step(monkeypatch):
    base = (10.0, 0.25, time.monotonic(), 120.0, 1, 0, 120.0)   # pos, age, recvMono, dur, seq, cs, wrap
    before = _model(base)
    real = time.time
    monkeypatch.setattr(time, 'time', lambda: real() + 5.0)    # +5 s step of OUR wall clock
    after = _model(base)
    assert abs(after - before) < 0.01


def test_model_advances_on_monotonic(monkeypatch):
    t0 = 1000.0
    monkeypatch.setattr(time, 'monotonic', lambda: t0)
    base = (10.0, 0.25, t0, 120.0, 1, 0, 120.0)
    assert abs(_model(base) - 10.25) < 1e-9
    monkeypatch.setattr(time, 'monotonic', lambda: t0 + 2.0)
    assert abs(_model(base) - 12.25) < 1e-9


def test_model_wraps_at_media_length(monkeypatch):
    t0 = 1000.0
    monkeypatch.setattr(time, 'monotonic', lambda: t0)
    base = (119.9, 0.25, t0, 120.0, 1, 0, 120.0)
    assert abs(_model(base) - 0.15) < 1e-6
