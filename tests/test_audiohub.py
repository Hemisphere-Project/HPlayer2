"""Audiohub monitor: platform contract parsing, /proc/asound parsing, and the
read-only supervision of the Pi-tools forwarder units.

The monitor tests drive _tick() directly (the loop body is sleep-free) on
dict-backed /proc fixtures and stubbed systemd states — zero audio hardware,
zero processes.
"""

import time

from core.engine.audiohw import read_audio_conf
from core.engine.drifter import Drifter
from core.interfaces.audiohub import (
    AudiohubInterface,
    parse_cards,
    parse_stream_playback_channels,
)


CARDS_NO_USB = """\
 0 [b1             ]: bcm2835_hdmi - bcm2835 HDMI 1
                      bcm2835 HDMI 1
 1 [Headphones     ]: bcm2835_headphones - bcm2835 Headphones
                      bcm2835 Headphones
 2 [Loopback       ]: Loopback - Loopback
                      Loopback 1
"""

CARDS_USB = CARDS_NO_USB + """\
 3 [Device         ]: USB-Audio - USB Audio Device
                      C-Media Electronics Inc. USB Audio Device at usb-3f980000.usb-1.1.3
"""

STREAM0_STEREO = """\
C-Media Electronics Inc. USB Audio Device, full speed : USB Audio

Playback:
  Status: Stop
  Interface 1
    Altset 1
    Format: S16_LE
    Channels: 2
    Rates: 44100, 48000

Capture:
  Interface 2
    Altset 1
    Format: S16_LE
    Channels: 1
    Rates: 44100, 48000
"""

STREAM0_MULTI = """\
8ch USB interface : USB Audio

Playback:
  Interface 1
    Altset 1
    Format: S16_LE
    Channels: 2
    Rates: 44100, 48000
  Interface 1
    Altset 2
    Format: S24_3LE
    Channels: 8
    Rates: 48000, 96000

Capture:
  Interface 2
    Altset 1
    Channels: 2
"""


# ---------------------------------------------------------------------------
# platform contract (core/engine/audiohw.py)
# ---------------------------------------------------------------------------

def test_read_audio_conf_missing(tmp_path):
    assert read_audio_conf(str(tmp_path / 'nope.conf')) is None


def test_read_audio_conf(tmp_path):
    p = tmp_path / 'audiohub.conf'
    p.write_text("# comment\ngraph=v2\nlatency_us=30000\n\njunk line\n")
    assert read_audio_conf(str(p)) == {'graph': 'v2', 'latency_us': 30000}


def test_read_audio_conf_defaults(tmp_path):
    p = tmp_path / 'audiohub.conf'
    p.write_text("graph=v3\nlatency_us=notanumber\n")
    conf = read_audio_conf(str(p))
    assert conf['graph'] == 'v3'
    assert conf['latency_us'] == 30000      # unparsable value -> default


# ---------------------------------------------------------------------------
# /proc/asound parsing
# ---------------------------------------------------------------------------

def test_parse_cards():
    cards = parse_cards(CARDS_USB)
    assert [c['id'] for c in cards] == ['b1', 'Headphones', 'Loopback', 'Device']
    assert [c['usb'] for c in cards] == [False, False, False, True]
    assert cards[3]['index'] == 3


def test_parse_cards_empty():
    assert parse_cards('') == []
    assert parse_cards('--- no soundcards ---') == []


def test_parse_stream_channels():
    assert parse_stream_playback_channels(STREAM0_STEREO) == 2
    assert parse_stream_playback_channels(STREAM0_MULTI) == 8


# ---------------------------------------------------------------------------
# monitor state machine
# ---------------------------------------------------------------------------

class StubSettings:
    _settings = {}

    def get(self, key):
        return self._settings.get(key)


class StubPlayer:
    def __init__(self):
        self.delays = []

    def status(self, entry=None):
        return True if entry == 'isReady' else None

    def _applyAudioDelay(self, seconds):
        self.delays.append(seconds)


class StubHttp2:
    def __init__(self):
        self.sent = []

    def send(self, event, message):
        self.sent.append((event, message))


class StubHPlayer:
    def __init__(self):
        self.settings = StubSettings()
        self.player = StubPlayer()
        self.http2 = StubHttp2()

    def autoBind(self, module):
        return None

    def interface(self, name):
        return self.http2 if name == 'http2' else None

    def players(self):
        return [self.player]


class FixturedHub(AudiohubInterface):
    def __init__(self, conf={'graph': 'v2', 'latency_us': 30000}):
        super().__init__(StubHPlayer())
        self.conf = conf
        self.files = {'/proc/asound/cards': CARDS_NO_USB}
        self.units = {'jack': 'active', 'hdmi': 'active', 'usb': 'active'}
        self.events = []

    def _read(self, path):
        return self.files.get(path, '')

    def _unitStates(self):
        return dict(self.units)

    def emit(self, event, *args):
        self.events.append(event)


def plug(hub, stream0=STREAM0_STEREO, index=3):
    hub.files['/proc/asound/cards'] = CARDS_USB
    hub.files['/proc/asound/card%d/stream0' % index] = stream0


def test_generic_platform_status():
    hub = FixturedHub(conf=None)
    assert hub.latency() == 0.0
    hub._pushStatus()
    ev, msg = hub.hplayer.http2.sent[-1]
    assert ev == 'audio-status'
    assert msg['mode'] == 'default'
    assert msg['jack'] == 'default'


def test_hub_platform_healthy():
    hub = FixturedHub()
    assert hub.latency() == 0.03
    hub._tick()
    hub._pushStatus()
    _, msg = hub.hplayer.http2.sent[-1]
    assert msg['mode'] == 'hub'
    assert msg['graph'] == 'v2'
    assert msg['latency-ms'] == 30.0
    assert msg['jack'] == 'active'
    assert msg['usb'] == 'absent'       # unit waits, no card plugged
    # compensation pushed to the player
    assert hub.hplayer.player.delays == [-0.03]


def test_usb_plug_unplug_edges():
    hub = FixturedHub()
    hub._tick()
    plug(hub)
    hub._tick()
    assert hub.events == ['connected']
    hub._pushStatus()
    _, msg = hub.hplayer.http2.sent[-1]
    assert msg['usb'] == 'active'
    assert msg['usb-card'] == 'Device'
    assert msg['usb-channels'] == 2
    hub.files['/proc/asound/cards'] = CARDS_NO_USB
    hub._tick()
    assert hub.events == ['connected', 'disconnected']


def test_failed_unit_reports_error_once():
    hub = FixturedHub()
    hub._tick()
    hub.units['hdmi'] = 'failed'
    hub._tick()
    hub._tick()                          # edge only: no repeat event
    assert hub.events.count('error') == 1
    hub._pushStatus()
    _, msg = hub.hplayer.http2.sent[-1]
    assert msg['hdmi'] == 'error'
    assert msg['jack'] == 'active'


def test_compensate_veto():
    hub = FixturedHub()
    hub.compensate = False               # profile: start-sync keeps visual priority
    hub._tick()
    assert hub.hplayer.player.delays == [0.0]


def test_status_resent_for_late_clients():
    hub = FixturedHub()
    hub._tick()
    for _ in range(hub.RESEND_EVERY + 1):
        hub._pushStatus()
    assert len(hub.hplayer.http2.sent) >= 2   # unchanged status still re-pushed


# ---------------------------------------------------------------------------
# drifter chase lead
# ---------------------------------------------------------------------------

class DrifterStubPlayer:
    def __init__(self, pos):
        self._pos = pos
        self.speeds = []

    def position(self):
        self._pos += 0.001               # must move or the tick is dropped
        return self._pos

    def isPaused(self):
        return False

    def isPlaying(self):
        return True

    def resume(self):
        pass

    def speed(self, s):
        self.speeds.append(s)

    def seekTo(self, ms):
        pass


def test_drifter_offset_leads_the_clock():
    d = Drifter(DrifterStubPlayer(10.0), log=lambda *a: None)
    d.arm()
    d.kickStart = 0
    base = d.tick(10.0)['diff']
    d2 = Drifter(DrifterStubPlayer(10.0), log=lambda *a: None)
    d2.offset = 0.03
    d2.arm()
    d2.kickStart = 0
    lead = d2.tick(10.0)['diff']
    assert abs((lead - base) - 0.03) < 1e-9
