import pytest

import core.interfaces.midictrl as midictrl_module


class DummyHPlayer:
    def autoBind(self, module):  # noqa: N802
        return None


class DummyMidiDevice:
    def __init__(self):
        self._open = False

    def is_port_open(self):
        return self._open

    def get_port_count(self):
        return 0

    def get_port_name(self, index):
        return "LPD8"

    def open_port(self, index):
        self._open = True

    def cancel_callback(self):
        pass

    def close_port(self):
        self._open = False

    def set_callback(self, callback):
        pass


def test_midictrl_requires_rtmidi(monkeypatch):
    monkeypatch.setattr(midictrl_module, "rtmidi", None, raising=False)

    with pytest.raises(RuntimeError):
        midictrl_module.MidictrlInterface(DummyHPlayer())


def test_midictrl_selects_platform_api(monkeypatch):
    class DummyRTMidi:
        API_MACOSX_CORE = 1
        API_UNSPECIFIED = 2

        def __init__(self):
            self.last_rtapi = None

        def get_compiled_api(self):
            return [self.API_MACOSX_CORE, self.API_UNSPECIFIED]

        def MidiIn(self, rtapi=None):
            self.last_rtapi = rtapi
            return DummyMidiDevice()

    dummy_rtmidi = DummyRTMidi()
    monkeypatch.setattr(midictrl_module, "rtmidi", dummy_rtmidi, raising=False)
    monkeypatch.setattr(midictrl_module.platform, "system", lambda: "Darwin")

    interface = midictrl_module.MidictrlInterface(DummyHPlayer())

    assert dummy_rtmidi.last_rtapi == dummy_rtmidi.API_MACOSX_CORE
    assert interface._rtapi == dummy_rtmidi.API_MACOSX_CORE


def test_midictrl_fallback_to_first_available(monkeypatch):
    class DummyRTMidi:
        API_UNSPECIFIED = 3

        def __init__(self):
            self.last_rtapi = None

        def get_compiled_api(self):
            return [self.API_UNSPECIFIED]

        def MidiIn(self, rtapi=None):
            self.last_rtapi = rtapi
            return DummyMidiDevice()

    dummy_rtmidi = DummyRTMidi()
    monkeypatch.setattr(midictrl_module, "rtmidi", dummy_rtmidi, raising=False)
    monkeypatch.setattr(midictrl_module.platform, "system", lambda: "Unknown")

    interface = midictrl_module.MidictrlInterface(DummyHPlayer())

    assert dummy_rtmidi.last_rtapi == dummy_rtmidi.API_UNSPECIFIED
    assert interface._rtapi == dummy_rtmidi.API_UNSPECIFIED
