import core.interfaces as ifacelib
from core.engine.hplayer import HPlayer2


class DummyInterface:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("hardware missing")


def test_add_interface_handles_runtime_error(monkeypatch):
    hplayer = HPlayer2(basepath=[], settingspath=None)

    monkeypatch.setattr(ifacelib, "getInterface", lambda name: DummyInterface)

    result = hplayer.addInterface("gpio")
    assert result is None
