"""hplayer2#t-113 — the keyboard probe with no keyboard attached.

On bench-04 (RastaOS-7.5) every start logged `[Keyboard] Keyboard not found ...
<class 'TypeError'>`: detect() found nothing, bind(None) still opened
InputDevice(None), and the catch-all logged the TypeError — the same line a real
keyboard failing to open printed. These pin the two paths apart, without evdev or
a device: bind() is driven on a bare instance with InputDevice stubbed.
"""
import core.interfaces.keyboard as kbmod
from core.interfaces.keyboard import KeyboardInterface


def _bare(detected):
    kb = KeyboardInterface.__new__(KeyboardInterface)
    kb.remote = None
    kb.logs = []
    kb.log = lambda *a: kb.logs.append(" ".join(str(x) for x in a))
    kb.detect = lambda: detected
    return kb


class _Device:
    instances = []

    def __init__(self, path, fail_grab=None):
        self.path = path
        self.fail_grab = fail_grab
        self.grabbed = False
        self.closed = False
        _Device.instances.append(self)

    def grab(self):
        if self.fail_grab:
            raise self.fail_grab
        self.grabbed = True

    def close(self):
        self.closed = True


def test_no_keyboard_is_a_plain_line_and_opens_nothing(monkeypatch):
    opened = []
    monkeypatch.setattr(kbmod, "InputDevice", lambda path: opened.append(path))
    kb = _bare(None)

    kb.bind(kb.detect())

    assert opened == []                    # InputDevice(None) is never attempted
    assert kb.remote is None
    assert kb.logs == ["No keyboard attached ..."]
    assert "TypeError" not in " ".join(kb.logs)


def test_keyboard_present_binds(monkeypatch):
    monkeypatch.setattr(kbmod, "InputDevice", _Device)
    kb = _bare("/dev/input/event3")

    kb.bind(kb.detect())

    assert isinstance(kb.remote, _Device) and kb.remote.grabbed
    assert kb.logs == ["Keyboard connected ... /dev/input/event3"]


def test_real_keyboard_that_fails_to_open_names_device_and_error(monkeypatch):
    _Device.instances.clear()
    busy = OSError(16, "Device or resource busy")
    monkeypatch.setattr(kbmod, "InputDevice", lambda path: _Device(path, fail_grab=busy))
    kb = _bare("/dev/input/event3")

    kb.bind(kb.detect())

    assert kb.remote is None
    assert _Device.instances[-1].closed     # the half-opened fd is released
    line = kb.logs[-1]
    assert line.startswith("Keyboard found but not opened ...")
    assert "/dev/input/event3" in line and "OSError" in line and "busy" in line
    assert "No keyboard attached" not in line


def test_hotplug_event_for_another_device_is_ignored(monkeypatch):
    opened = []
    monkeypatch.setattr(kbmod, "InputDevice", lambda path: opened.append(path))
    kb = _bare(None)                          # a mouse appears; still no keyboard

    class Event:
        src_path = "/dev/input/event5"

    kb.bind(Event())

    assert opened == [] and kb.logs == []   # no « no keyboard » line on every hotplug


def test_hotplug_keyboard_event_binds(monkeypatch):
    monkeypatch.setattr(kbmod, "InputDevice", _Device)
    kb = _bare("/dev/input/event4")

    class Event:
        src_path = "/dev/input/event4"

    kb.bind(Event())

    assert isinstance(kb.remote, _Device) and kb.remote.path == "/dev/input/event4"
