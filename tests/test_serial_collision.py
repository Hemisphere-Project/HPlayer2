"""teleco2 vs radar on the shared Espressif 303a:1001 ROM-CDC id (hplayer2#t-033).

The pump tests run the real SerialBase.listen() threads against fake ports: a radar box
(one bare `hello 1` on boot, then a radar frame per read) and a CoreS3 remote (beacons
`hello 1 <fw>` until a host line reaches it).
"""
import re
import time
from types import SimpleNamespace

import pytest

import core.interfaces.serialbase as serialbase
import core.interfaces.teleco2 as teleco2_module
from core.interfaces.radar import RadarInterface
from core.interfaces.serialbase import SerialBase
from core.interfaces.teleco2 import Teleco2Interface


class FakeSettings:
    def __init__(self):
        self._settings = {'volume': 80, 'mute': False, 'loop': 0}

    def get(self, key):
        return self._settings.get(key)


class FakePlayer:
    def status(self):
        return {'isPaused': False, 'isPlaying': False, 'media': None, 'time': 0, 'duration': 0}

    def isPaused(self):
        return False

    def isPlaying(self):
        return False


class FakePlaylist:
    def index(self):
        return -1

    def size(self):
        return 0

    def export(self):
        return []


class FakeHPlayer:
    def __init__(self):
        self.settings = FakeSettings()
        self.playlist = FakePlaylist()
        self.events = []

    def autoBind(self, module):  # noqa: N802
        return None

    def on(self, event):
        return lambda fn: fn

    def emit(self, event, *args):
        self.events.append(event)

    def activePlayer(self):  # noqa: N802
        return FakePlayer()

    def interface(self, name):
        return None


#
# fake hardware
#

class FakeDevice:
    def __init__(self, port, hwid, desc="USB JTAG/serial debug unit"):
        self.port, self.hwid, self.description = port, hwid, desc
        self.rx = []                # host -> device lines
        self.readers = 0            # how many fds currently hold it open

    def line(self):
        return None


class RadarBox(FakeDevice):
    def __init__(self, port):
        super().__init__(port, "USB VID:PID=303A:1001 SER=RADAR LOCATION=1-1.2:1.0")
        self.booted = False

    def line(self):
        if not self.booted:
            self.booted = True
            return "hello 1"        # what extra/arduino/radar_ld2450 prints on boot
        return "T 120,1500,0"


class Remote(FakeDevice):
    def __init__(self, port):
        super().__init__(port, "USB VID:PID=303A:1001 SER=REMOTE LOCATION=1-1.3:1.0")

    def line(self):
        return None if self.rx else "hello 1 5"     # beacon until the host speaks


class Silent(FakeDevice):
    pass


class FakeBus:
    def __init__(self, *devices):
        self.devices = {d.port: d for d in devices}

    def grep(self, regexp):
        for d in list(self.devices.values()):
            if any(re.search(regexp, s, re.I) for s in (d.port, d.description, d.hwid)):
                yield SimpleNamespace(device=d.port, hwid=d.hwid, description=d.description)


class FakeSerialException(Exception):
    pass


def fake_serial_module(bus):
    class FakeSerial:
        def __init__(self, port, baud=115200, timeout=None):
            if port not in bus.devices:
                raise FakeSerialException("no such port " + port)
            self.dev = bus.devices[port]
            self.dev.readers += 1
            self.open = True

        def readline(self):
            if not self.open or self.dev.port not in bus.devices:
                raise FakeSerialException("gone")
            time.sleep(0.01)
            line = self.dev.line()
            return (line + "\n").encode() if line else b""

        def write(self, data):
            self.dev.rx.append(data.decode().strip())

        def close(self):
            if self.open:
                self.open = False
                self.dev.readers -= 1

    return SimpleNamespace(Serial=FakeSerial, SerialException=FakeSerialException)


@pytest.fixture
def bus(monkeypatch):
    def install(*devices):
        b = FakeBus(*devices)
        monkeypatch.setattr(serialbase, "list_ports", SimpleNamespace(grep=b.grep))
        monkeypatch.setattr(serialbase, "serial", fake_serial_module(b))
        return b
    SerialBase._claims.clear()
    yield install
    SerialBase._claims.clear()


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch):
    monkeypatch.setattr(teleco2_module, "network", SimpleNamespace(
        get_hostname=lambda: "player", get_ip=lambda i: "10.0.0.2",
        get_rssi=lambda i: 70, get_essid=lambda i: "Pi-sync"))


def make_teleco2(hplayer=None, **kw):
    t = Teleco2Interface(hplayer or FakeHPlayer(), **kw)
    t.scanInterval = 0.05
    t.flashed = []
    t._fwCheck = lambda fw: t.flashed.append((t.port, fw)) or False
    return t


def make_radar(hplayer=None):
    r = RadarInterface(hplayer or FakeHPlayer())
    r.scanInterval = 0.05
    return r


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def running(*ifaces):
    class Ctx:
        def __enter__(self):
            for i in ifaces:
                i.start()
            return ifaces

        def __exit__(self, *exc):
            for i in ifaces:
                i.quit()
    return Ctx()


def host_lines(dev):
    return [line for line in dev.rx if line.startswith('{')]


#
# teleco2: what makes a port the remote's
#

def test_bare_hello_needs_the_beacon_to_repeat_before_any_flash():
    t = make_teleco2()
    t.port = "/dev/ttyACM0"
    t.onConnect()
    t.onLine("hello 1")
    assert t.flashed == [] and t._helloWait        # the radar box says exactly this, once
    t.onLine("hello 1")
    assert t.flashed == [("/dev/ttyACM0", 0)]       # a fw<=1 remote repeats it: flash allowed
    assert t._helloWait is None                     # and dumped


def test_hello_with_fw_is_the_remote_at_once():
    t = make_teleco2()
    t.port = "/dev/ttyACM0"
    t.onConnect()
    t.onLine("hello 1 5")
    assert t.flashed == [("/dev/ttyACM0", 5)]
    assert t._helloWait is None


def test_radar_frame_rejects_the_port():
    t = make_teleco2()
    t.port = "/dev/ttyACM0"
    t.onConnect()
    t.onLine("hello 1")
    t.onLine("T 120,1500,0")
    assert t._rejectReason == "radar frames"
    assert t.flashed == []


def test_silence_rejects_on_the_default_filter(monkeypatch):
    monkeypatch.setattr(teleco2_module, "HELLO_WAIT", 0)
    t = make_teleco2()
    t.port = "/dev/ttyACM0"
    t.onConnect()
    time.sleep(0.01)
    t.tick()
    assert t._rejectReason and t._helloWait         # rejected, nothing sent
    assert t._txQueue.empty()


def test_teleco2_filter_setting_overrides_and_is_trusted(monkeypatch):
    monkeypatch.setattr(teleco2_module, "HELLO_WAIT", 0)
    hp = FakeHPlayer()
    t = make_teleco2(hp)
    assert hp.settings._settings['teleco2-filter'] == ''   # seeded before settings.load()
    assert t.filter == teleco2_module.DEFAULT_FILTER
    hp.settings._settings['teleco2-filter'] = 'SER=F4:12:FA:00:00:01'
    assert t.filter == 'SER=F4:12:FA:00:00:01'
    t.port = "/dev/ttyACM0"
    t.onConnect()
    t.onLine("hello 1")
    assert t.flashed == [("/dev/ttyACM0", 0)]       # trusted: first hello acts, as before
    t.onConnect()
    time.sleep(0.01)
    t.tick()
    assert t._rejectReason is None                  # trusted: silence gets the dump anyway
    assert not t._txQueue.empty()


def test_radar_rejects_a_remote_beacon_not_its_own_hello():
    r = make_radar()
    r.port = "/dev/ttyACM0"
    r.onLine("hello 1")
    assert r._rejectReason is None
    r.onLine("hello 1 5")
    assert r._rejectReason == "teleco2 remote beacon"


def test_literal_port_is_never_rejected():
    t = make_teleco2(filter="/tmp/hp2r-host")
    t.port = "/tmp/hp2r-host"
    t.rejectPort("anything")
    assert t._rejectReason is None


#
# the pump, end to end
#

def test_teleco2_skips_the_radar_box_and_finds_the_remote(bus):
    radar, remote = RadarBox("/dev/ttyACM0"), Remote("/dev/ttyACM1")
    bus(radar, remote)
    t = make_teleco2()
    with running(t):
        assert wait_for(lambda: t.port == "/dev/ttyACM1" and host_lines(remote))
    assert host_lines(radar) == []                  # never wrote to the radar box
    assert ("/dev/ttyACM0", 0) not in t.flashed     # never flashed it on its boot hello
    assert t.flashed == [("/dev/ttyACM1", 5)]


@pytest.mark.parametrize("order", ["radar-first", "remote-first"])
def test_radar_and_teleco2_sort_themselves_out(bus, order):
    radar, remote = RadarBox("/dev/ttyACM0"), Remote("/dev/ttyACM1")
    if order == "remote-first":
        radar.port, remote.port = remote.port, radar.port
        bus(remote, radar)
    else:
        bus(radar, remote)
    hp = FakeHPlayer()
    r, t = make_radar(hp), make_teleco2(hp)
    with running(r, t):
        assert wait_for(lambda: r.port == radar.port and r.serial is not None
                        and t.port == remote.port and host_lines(remote))
        assert radar.readers == 1 and remote.readers == 1   # one reader per tty
    assert host_lines(radar) == []


def test_two_interfaces_never_share_a_tty(bus):
    radar = RadarBox("/dev/ttyACM0")
    bus(radar)
    hp = FakeHPlayer()
    r1, r2 = make_radar(hp), make_radar(hp)
    with running(r1, r2):
        assert wait_for(lambda: (r1.serial is not None) != (r2.serial is not None))
        time.sleep(0.2)
        assert radar.readers == 1


def test_silent_device_is_excluded_until_it_leaves_the_bus(bus, monkeypatch):
    monkeypatch.setattr(teleco2_module, "HELLO_WAIT", 0.2)
    silent = Silent("/dev/ttyACM0", "USB VID:PID=303A:1001 SER=JTAGBOARD")
    b = bus(silent)
    t = make_teleco2()
    with running(t):
        assert wait_for(lambda: "/dev/ttyACM0" in t._rejected and t.port is None)
        time.sleep(0.3)
        assert t.port is None and silent.readers == 0       # stays excluded while plugged
        del b.devices["/dev/ttyACM0"]                        # unplug ...
        assert wait_for(lambda: not t._rejected)
        remote = Remote("/dev/ttyACM0")                      # ... and the remote takes the slot
        b.devices[remote.port] = remote
        assert wait_for(lambda: host_lines(remote))
    assert host_lines(silent) == []
