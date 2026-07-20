"""Audiohub: /proc/asound parsing, egress choice, and forwarder supervision.

The supervision tests drive _tick() directly (the loop body is sleep-free) with
dict-backed /proc fixtures and a stub forwarder process, so the whole USB
plug/unplug/crash state machine runs in milliseconds with zero audio hardware.
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
 0 [Headphones     ]: bcm2835_headphones - bcm2835 Headphones
                      bcm2835 Headphones
 1 [b1             ]: bcm2835_hdmi - bcm2835 HDMI 1
                      bcm2835 HDMI 1
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
    assert [c['id'] for c in cards] == ['Headphones', 'b1', 'Loopback', 'Device']
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
    assert cmd[cmd.index('-P') + 1] == 'usbout2:CARD=Device'
    assert cmd[cmd.index('-t') + 1] == '8000'
    # no chrt available: plain spawn
    assert build_alsaloop_cmd('null', 8000)[0] == 'alsaloop'


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
    """Probe /proc through a dict, mirror into a long-sleep stub process."""

    def __init__(self):
        super().__init__(StubHPlayer())
        self.files = {'/etc/asound.conf': 'pcm.hplayer {}',
                      '/proc/asound/cards': CARDS_NO_USB}
        self.events = []

    def _read(self, path):
        return self.files.get(path, '')

    def emit(self, event, *args):
        self.events.append(event)

    def _spawn(self, card):
        self._proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])


def make_hub():
    hub = FixturedHub()
    hub._graph = hub._checkGraph()
    assert hub._graph
    return hub


def plug(hub, stream0=STREAM0_STEREO, index=3):
    hub.files['/proc/asound/cards'] = CARDS_USB
    hub.files['/proc/asound/card%d/stream0' % index] = stream0


def test_no_card_stays_absent():
    hub = make_hub()
    hub._tick()
    assert hub._usbState() == 'absent'
    assert hub._proc is None


def test_plug_spawns_and_unplug_kills():
    hub = make_hub()
    hub._tick()
    plug(hub)
    hub._tick()
    assert hub._usbState() == 'active'
    assert hub.events == ['connected']
    proc = hub._proc
    hub.files['/proc/asound/cards'] = CARDS_NO_USB
    hub._tick()
    assert hub._usbState() == 'absent'
    assert hub.events == ['connected', 'disconnected']
    assert proc.poll() is not None
    assert hub._proc is None


def test_forwarder_death_backs_off_then_errors():
    hub = make_hub()
    plug(hub)
    hub._tick()
    for _ in range(hub.ERROR_AFTER):
        hub._proc.kill()
        hub._proc.wait()
        hub._tick()                      # reap + schedule respawn
        hub._nextSpawn = 0               # collapse the backoff for the test
        hub._tick()                      # respawn
    assert hub._deaths == hub.ERROR_AFTER
    assert hub._usbState() == 'error'
    assert 'error' in hub.events
    # a replug resets the error history
    hub.files['/proc/asound/cards'] = CARDS_NO_USB
    hub._tick()
    plug(hub)
    hub._tick()
    assert hub._usbState() == 'active'
    hub._kill()


def test_stable_forwarder_heals_error_history():
    hub = make_hub()
    plug(hub)
    hub._tick()
    hub._proc.kill()
    hub._proc.wait()
    hub._tick()
    hub._nextSpawn = 0
    hub._tick()
    assert hub._deaths == 1
    hub._spawnTime = time.monotonic() - hub.HEAL_AFTER - 1
    hub._tick()
    assert hub._deaths == 0
    assert hub._usbState() == 'active'
    hub._kill()


def test_disable_setting_stops_mirror():
    hub = make_hub()
    plug(hub)
    hub._tick()
    assert hub._usbState() == 'active'
    hub.hplayer.settings._settings['audiohub-usb'] = False
    hub._tick()
    assert hub._usbState() == 'off'
    assert hub._proc is None
