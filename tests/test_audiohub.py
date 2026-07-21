"""Audiohub: /proc/asound parsing, egress choice, and forwarder supervision.

The supervision tests drive _tick() directly (the loop body is sleep-free) with
dict-backed /proc fixtures and stub forwarder processes, so the whole
jack/hdmi/USB supervision state machine runs in milliseconds with zero audio
hardware.
"""

import subprocess
import sys
import time

import core.interfaces.audiohub as audiohub_module
from core.interfaces.audiohub import (
    AudiohubInterface,
    build_alsaloop_cmd,
    parse_cards,
    parse_stream_playback_channels,
    pick_usb_egress,
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
                      C-Media Electronics Inc. USB Audio Device at usb-3f980000.usb-1.2
"""

STREAM0_STEREO = """\
C-Media Electronics Inc. USB Audio Device at usb-3f980000.usb-1.2, full speed : USB Audio

Playback:
  Status: Stop
  Interface 1
    Altset 1
    Format: S16_LE
    Channels: 2
    Endpoint: 0x01 (1 OUT) (ADAPTIVE)
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
  Status: Stop
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
    Format: S16_LE
    Channels: 2
    Rates: 48000
"""


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------

def test_parse_cards():
    cards = parse_cards(CARDS_USB)
    assert [c['id'] for c in cards] == ['b1', 'Headphones', 'Loopback', 'Device']
    assert [c['usb'] for c in cards] == [False, False, False, True]
    assert cards[3]['index'] == 3


def test_parse_cards_empty():
    assert parse_cards('') == []
    assert parse_cards('--- no soundcards ---') == []


def test_parse_stream_channels_stereo():
    # the Capture 1ch line must not leak into the playback count
    assert parse_stream_playback_channels(STREAM0_STEREO) == 2


def test_parse_stream_channels_multi():
    # highest playback altset wins
    assert parse_stream_playback_channels(STREAM0_MULTI) == 8


def test_pick_usb_egress():
    assert pick_usb_egress('Device', 2) == 'usbout2:CARD=Device'
    assert pick_usb_egress('Device', 6) == 'usbout2:CARD=Device'   # static routes: 2 or 8 only
    assert pick_usb_egress('UMC1820', 10) == 'usbout8:CARD=UMC1820'


def test_build_alsaloop_cmd():
    cmd = build_alsaloop_cmd('usbout2:CARD=Device', 8000,
                             chrt='/usr/bin/chrt', alsaloop='/usr/bin/alsaloop')
    assert cmd[:3] == ['/usr/bin/chrt', '-f', '10']
    assert '/usr/bin/alsaloop' in cmd
    assert cmd[cmd.index('-C') + 1] == 'aloopcap'
    assert cmd[cmd.index('-P') + 1] == 'usbout2:CARD=Device'
    assert cmd[cmd.index('-t') + 1] == '8000'
    # no chrt available: plain spawn; capture side overridable (desk harness)
    plain = build_alsaloop_cmd('null', 30000, capture='hw:Loopback,1,0')
    assert plain[0] == 'alsaloop'
    assert plain[plain.index('-C') + 1] == 'hw:Loopback,1,0'


# ---------------------------------------------------------------------------
# supervision state machine
# ---------------------------------------------------------------------------

class StubSettings:
    def __init__(self):
        self._settings = {}

    def get(self, key):
        return self._settings.get(key)


class StubHPlayer:
    def __init__(self):
        self.settings = StubSettings()

    def autoBind(self, module):
        return None

    def interface(self, name):
        return None


class FixturedHub(AudiohubInterface):
    """Probe /proc through a dict, spawn long-sleep stub processes."""

    def __init__(self):
        super().__init__(StubHPlayer())
        self.files = {'/etc/asound.conf': 'pcm.hplayer {}',
                      '/proc/asound/cards': CARDS_NO_USB}
        self.events = []

    def _read(self, path):
        return self.files.get(path, '')

    def emit(self, event, *args):
        self.events.append(event)

    def _spawn(self, fwd):
        fwd.proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])


def make_hub():
    hub = FixturedHub()
    hub._graph = hub._checkGraph()
    assert hub._graph
    return hub


def teardown(hub):
    for fwd in hub._fwd.values():
        hub._kill(fwd)


def plug(hub, stream0=STREAM0_STEREO, index=3):
    hub.files['/proc/asound/cards'] = CARDS_USB
    hub.files['/proc/asound/card%d/stream0' % index] = stream0


def test_static_sinks_mirror_from_first_tick():
    hub = make_hub()
    hub._tick()
    assert hub._fwd['jack'].state() == 'active'
    assert hub._fwd['hdmi'].state() == 'active'
    assert hub._usbState() == 'absent'
    assert 'usb' not in hub._fwd
    teardown(hub)


def test_plug_spawns_and_unplug_kills():
    hub = make_hub()
    hub._tick()
    plug(hub)
    hub._tick()
    assert hub._usbState() == 'active'
    assert hub.events == ['connected']
    proc = hub._fwd['usb'].proc
    hub.files['/proc/asound/cards'] = CARDS_NO_USB
    hub._tick()
    assert hub._usbState() == 'absent'
    assert hub.events == ['connected', 'disconnected']
    assert proc.poll() is not None
    assert 'usb' not in hub._fwd
    teardown(hub)


def test_multichannel_card_picks_usbout8():
    hub = make_hub()
    plug(hub, stream0=STREAM0_MULTI)
    hub._tick()
    assert hub._fwd['usb'].device == 'usbout8:CARD=Device'
    teardown(hub)


def test_forwarder_death_backs_off_then_errors():
    hub = make_hub()
    plug(hub)
    hub._tick()
    fwd = hub._fwd['usb']
    for _ in range(hub.ERROR_AFTER):
        fwd.proc.kill()
        fwd.proc.wait()
        hub._tick()                      # reap + schedule respawn
        fwd.nextSpawn = 0                # collapse the backoff for the test
        hub._tick()                      # respawn
    assert fwd.deaths == hub.ERROR_AFTER
    assert 'error' in hub.events
    # jack/hdmi are untouched by the usb crash-loop
    assert hub._fwd['jack'].state() == 'active'
    assert hub._fwd['hdmi'].state() == 'active'
    # a replug resets the error history (fresh forwarder object)
    hub.files['/proc/asound/cards'] = CARDS_NO_USB
    hub._tick()
    plug(hub)
    hub._tick()
    assert hub._usbState() == 'active'
    assert hub._fwd['usb'].deaths == 0
    teardown(hub)


def test_static_sink_crash_is_independent():
    hub = make_hub()
    hub._tick()
    jack = hub._fwd['jack']
    for _ in range(hub.ERROR_AFTER):
        jack.proc.kill()
        jack.proc.wait()
        hub._tick()
        jack.nextSpawn = 0
        hub._tick()
    assert jack.deaths == hub.ERROR_AFTER
    assert 'error' in hub.events
    assert hub._fwd['hdmi'].state() == 'active'
    teardown(hub)


def test_stable_forwarder_heals_error_history():
    hub = make_hub()
    hub._tick()
    jack = hub._fwd['jack']
    jack.proc.kill()
    jack.proc.wait()
    hub._tick()
    jack.nextSpawn = 0
    hub._tick()
    assert jack.deaths == 1
    jack.spawnTime = time.monotonic() - hub.HEAL_AFTER - 1
    hub._tick()
    assert jack.deaths == 0
    assert jack.state() == 'active'
    teardown(hub)


def test_disable_setting_stops_usb_mirror_only():
    hub = make_hub()
    plug(hub)
    hub._tick()
    assert hub._usbState() == 'active'
    hub.hplayer.settings._settings['audiohub-usb'] = False
    hub._tick()
    assert hub._usbState() == 'off'
    assert 'usb' not in hub._fwd
    assert hub._fwd['jack'].state() == 'active'
    teardown(hub)
