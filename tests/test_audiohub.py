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
    parse_pcm_status,
    parse_stream_playback_channels,
    resolve_sink_pcms,
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

CARDS_X86 = """\
 0 [PCH            ]: HDA-Intel - HDA Intel PCH
                      HDA Intel PCH at 0x6001120000 irq 172
 1 [Loopback       ]: Loopback - Loopback
                      Loopback 1
"""

# /proc/asound/cardN paths for the CARDS_NO_USB / CARDS_USB layout
CABLE = '/proc/asound/card2/pcm0p/sub0/status'      # Loopback
HDMI_SINK = '/proc/asound/card0/pcm0p/sub0/status'  # b1
JACK_SINK = '/proc/asound/card1/pcm0p/sub0/status'  # Headphones
USB_SINK = '/proc/asound/card3/pcm0p/sub0/status'   # Device

PCM_CLOSED = 'closed\n'


def pcm_running(ptr):
    return ("state: RUNNING\n"
            "owner_pid   : 617\n"
            "trigger_time: 173.501\n"
            "tstamp      : 0.0\n"
            "delay       : 1200\n"
            "avail       : 288\n"
            "avail_max   : 4321\n"
            "-----\n"
            "hw_ptr      : %d\n"
            "appl_ptr    : %d\n" % (ptr, ptr + 1200))


def pcm_prepared(ptr):
    # the bench wedge signature: sink stuck PREPARED, hw_ptr frozen
    return ("state: PREPARED\n"
            "hw_ptr      : %d\n"
            "appl_ptr    : %d\n" % (ptr, ptr))


# ---------------------------------------------------------------------------
# platform contract (core/engine/audiohw.py)
# ---------------------------------------------------------------------------

def test_read_audio_conf_missing(tmp_path):
    assert read_audio_conf(str(tmp_path / 'nope.conf')) is None


def test_read_audio_conf(tmp_path):
    p = tmp_path / 'audiohub.conf'
    p.write_text("# comment\ngraph=v2\nlatency_us=30000\n\njunk line\n")
    assert read_audio_conf(str(p)) == {'graph': 'v2', 'latency_us': 30000,
                                       'mute': []}


def test_read_audio_conf_defaults(tmp_path):
    p = tmp_path / 'audiohub.conf'
    p.write_text("graph=v3\nlatency_us=notanumber\n")
    conf = read_audio_conf(str(p))
    assert conf['graph'] == 'v3'
    assert conf['latency_us'] == 30000      # unparsable value -> default


def test_read_audio_conf_mute_key(tmp_path):
    etc = tmp_path / 'etc.conf'
    data = tmp_path / 'data.conf'
    etc.write_text("graph=v2\nlatency_us=30000\n")
    data.write_text("mute=hdmi\n")
    conf = read_audio_conf((str(etc), str(data)))
    assert conf['mute'] == ['hdmi']
    data.write_text("mute=\n")              # `audiohub unmute` variant: empty
    assert read_audio_conf((str(etc), str(data)))['mute'] == []


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


def test_parse_pcm_status():
    assert parse_pcm_status(pcm_running(4800)) == ('RUNNING', 4800)
    assert parse_pcm_status(pcm_prepared(960)) == ('PREPARED', 960)
    assert parse_pcm_status(PCM_CLOSED) == ('closed', None)
    assert parse_pcm_status('') == ('closed', None)


def test_resolve_sink_pcms_pi():
    sinks = resolve_sink_pcms(parse_cards(CARDS_NO_USB))
    assert sinks == {'jack': (1, 'pcm0p'), 'hdmi': (0, 'pcm0p')}


def test_resolve_sink_pcms_x86():
    # one HDA card: analog is device 0, HDMI device 3
    sinks = resolve_sink_pcms(parse_cards(CARDS_X86))
    assert sinks == {'jack': (0, 'pcm0p'), 'hdmi': (0, 'pcm3p')}


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

    def _readConf(self):
        return self.conf

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


def test_live_config_change_recompensates():
    hub = FixturedHub()
    hub._tick()
    assert hub.hplayer.player.delays == [-0.03]
    hub.conf = {'graph': 'v2', 'latency_us': 25000}   # as if `audiohub set` ran
    hub._tick()
    assert hub.hplayer.player.delays[-1] == -0.025


# ---------------------------------------------------------------------------
# flow supervision (t-030): hw_ptr stall detection behind the chips
# ---------------------------------------------------------------------------

def test_stalled_sink_flagged_and_edges_once():
    hub = FixturedHub()
    ptr = 0
    for _ in range(AudiohubInterface.STALL_TICKS + 2):
        ptr += 960
        hub.files[CABLE] = pcm_running(ptr)           # mpv writes the cable
        hub.files[JACK_SINK] = pcm_running(ptr)       # jack flows
        hub.files[HDMI_SINK] = pcm_prepared(4800)     # hdmi wedged, unit 'active'
        hub._tick()
    assert hub.events.count('error') == 1             # stall onset is an edge
    hub._pushStatus()
    _, msg = hub.hplayer.http2.sent[-1]
    assert msg['hdmi'] == 'stalled'
    assert msg['jack'] == 'active'


def test_idle_cable_never_stalls():
    hub = FixturedHub()
    for _ in range(AudiohubInterface.STALL_TICKS + 2):
        hub.files[CABLE] = PCM_CLOSED                 # mpv not playing
        hub.files[HDMI_SINK] = pcm_prepared(0)
        hub._tick()
    assert 'error' not in hub.events
    hub._pushStatus()
    _, msg = hub.hplayer.http2.sent[-1]
    assert msg['hdmi'] == 'active'


def test_stall_recovers_when_flow_resumes():
    hub = FixturedHub()
    ptr = 0
    for _ in range(AudiohubInterface.STALL_TICKS):
        ptr += 960
        hub.files[CABLE] = pcm_running(ptr)
        hub.files[JACK_SINK] = pcm_running(ptr)
        hub.files[HDMI_SINK] = pcm_prepared(4800)
        hub._tick()
    assert hub._sinkState('hdmi') == 'stalled'
    hub.files[HDMI_SINK] = pcm_running(5760)          # forwarder recycled, flowing
    hub._tick()
    assert hub._sinkState('hdmi') == 'active'


def test_unit_down_is_error_not_stall():
    hub = FixturedHub()
    hub.units['hdmi'] = 'inactive'                    # e.g. `audiohub test` pause
    ptr = 0
    for _ in range(AudiohubInterface.STALL_TICKS + 1):
        ptr += 960
        hub.files[CABLE] = pcm_running(ptr)
        hub.files[JACK_SINK] = pcm_running(ptr)
        hub.files[HDMI_SINK] = PCM_CLOSED
        hub._tick()
    assert 'error' not in hub.events                  # no spurious stall edge
    assert hub._sinkState('hdmi') == 'error'


def test_usb_sink_flow_watched_when_present():
    hub = FixturedHub()
    plug(hub)
    ptr = 0
    for _ in range(AudiohubInterface.STALL_TICKS):
        ptr += 960
        hub.files[CABLE] = pcm_running(ptr)
        hub.files[JACK_SINK] = pcm_running(ptr)
        hub.files[HDMI_SINK] = pcm_running(ptr)
        hub.files[USB_SINK] = pcm_prepared(0)         # card there, nothing flows
        hub._tick()
    assert hub._sinkState('usb') == 'stalled'
    assert hub._sinkState('jack') == 'active'


# ---------------------------------------------------------------------------
# hdmi softvol mute (platform-side control, chips reflect the conf)
# ---------------------------------------------------------------------------

MUTED_CONF = {'graph': 'v2', 'latency_us': 30000, 'mute': ['hdmi']}


def test_muted_state_from_conf():
    hub = FixturedHub(conf=dict(MUTED_CONF))
    hub._tick()
    hub._pushStatus()
    _, msg = hub.hplayer.http2.sent[-1]
    assert msg['hdmi'] == 'muted'
    assert msg['jack'] == 'active'


def test_stall_and_error_outrank_muted():
    # softvol mute keeps silence flowing, so health stays watchable while
    # muted — the chip must tell the harder truth first
    hub = FixturedHub(conf=dict(MUTED_CONF))
    ptr = 0
    for _ in range(AudiohubInterface.STALL_TICKS):
        ptr += 960
        hub.files[CABLE] = pcm_running(ptr)
        hub.files[JACK_SINK] = pcm_running(ptr)
        hub.files[HDMI_SINK] = pcm_prepared(4800)
        hub._tick()
    assert hub._sinkState('hdmi') == 'stalled'
    hub.units['hdmi'] = 'failed'
    hub._tick()
    assert hub._sinkState('hdmi') == 'error'


def test_setmute_shells_the_platform_cli(monkeypatch):
    import core.interfaces.audiohub as mod
    calls = []
    monkeypatch.setattr(mod.shutil, 'which', lambda n: '/usr/local/bin/audiohub')
    monkeypatch.setattr(mod.subprocess, 'run', lambda cmd, **kw: calls.append(cmd))
    hub = FixturedHub()
    hub.setMute('hdmi', True)
    hub.setMute('hdmi', False)
    assert calls == [['/usr/local/bin/audiohub', 'mute', 'hdmi'],
                     ['/usr/local/bin/audiohub', 'unmute', 'hdmi']]


def test_setmute_ignored_without_hub_or_cli(monkeypatch):
    import core.interfaces.audiohub as mod
    monkeypatch.setattr(mod.subprocess, 'run',
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('ran')))
    hub = FixturedHub(conf=None)                      # generic platform
    hub.setMute('hdmi', True)
    hub2 = FixturedHub()                              # hub, but no CLI on PATH
    monkeypatch.setattr(mod.shutil, 'which', lambda n: None)
    hub2.setMute('hdmi', True)


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
