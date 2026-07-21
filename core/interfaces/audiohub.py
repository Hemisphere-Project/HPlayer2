from .base import BaseInterface
from ..engine.audiohw import read_audio_conf

import re
import shutil
import subprocess


# ---------------------------------------------------------------------------
# pure helpers (unit-tested in tests/test_audiohub.py)
# ---------------------------------------------------------------------------

def parse_cards(text):
    """Parse /proc/asound/cards into [{'index', 'id', 'desc', 'usb'}]."""
    cards = []
    for line in text.splitlines():
        m = re.match(r'^\s*(\d+)\s+\[(\S+)\s*\]:\s+(.*)$', line)
        if m:
            cards.append({'index': int(m.group(1)),
                          'id': m.group(2),
                          'desc': m.group(3).strip(),
                          'usb': 'USB-Audio' in m.group(3)})
    return cards


def parse_stream_playback_channels(text):
    """Max playback channel count from a /proc/asound/cardN/stream0 dump."""
    channels = 0
    in_playback = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('Playback:'):
            in_playback = True
        elif s.startswith('Capture:'):
            in_playback = False
        elif in_playback and s.startswith('Channels:'):
            try:
                channels = max(channels, int(s.split(':')[1].strip()))
            except ValueError:
                pass
    return channels


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------

class AudiohubInterface(BaseInterface):
    """
    Read-only monitor of the platform audio plumbing.

    The plumbing itself lives in Pi-tools (audiohub module): the ALSA hub
    graph, snd-aloop, and the audiohub@{jack,hdmi,usb} forwarder units.
    This interface only OBSERVES — /etc/audiohub.conf (+ /data override) for
    the contract, systemd for forwarder health, /proc/asound for the USB
    card — and:

      - pushes per-output status chips to http2 ('audio-status' event);
      - applies the player compensation (mpv audio-delay = -latency) so video
        waits for the audio pipeline. Profiles can veto it (start-sync fleets
        keep visual priority) by setting `audiohub.compensate = False`; the
        WALL-mode drifter lead is the profile's side of the deal.

    Without the contract file the platform is generic: no compensation, no
    monitoring, chips report 'default' — HPlayer2 never touches audio config.

    Emits (edges only): audiohub.connected <card> <ch>, audiohub.disconnected,
    audiohub.error <sink>. 'error' on a chip means the silent-failure case:
    mpv plays, that output doesn't.
    """

    SCAN_PERIOD = 2.0      # s
    RESEND_EVERY = 5       # ticks: re-push unchanged status for late web clients
    UNITS = {'jack': 'audiohub@jack.service',
             'hdmi': 'audiohub@hdmi.service',
             'usb':  'audiohub@usb.service'}

    def __init__(self, hplayer):
        super().__init__(hplayer, "AudioHub", "cyan")
        self.compensate = True      # profile veto: start-sync keeps visual priority
        self.conf = read_audio_conf()
        self._card = None           # USB card currently seen
        self._states = {}           # sink -> unit state, for error edges
        self._lastSent = None
        self._resend = 0
        self._appliedDelay = None

    def latency(self):
        """Pipeline latency in seconds (0.0 on a generic platform)."""
        return self.conf['latency_us'] / 1e6 if self.conf else 0.0

    # -- probes (overridable in tests) ---------------------------------------

    def _read(self, path):
        try:
            with open(path) as fd:
                return fd.read()
        except OSError:
            return ''

    def _unitStates(self):
        """sink -> systemd ActiveState ('active', 'failed', 'inactive', ...)."""
        systemctl = shutil.which('systemctl')
        if not systemctl:
            return {s: 'unknown' for s in self.UNITS}
        out = subprocess.run([systemctl, 'is-active'] + list(self.UNITS.values()),
                             capture_output=True, universal_newlines=True).stdout
        lines = out.split()
        return {sink: (lines[i] if i < len(lines) else 'unknown')
                for i, sink in enumerate(self.UNITS)}

    def _scanUsb(self):
        for c in parse_cards(self._read('/proc/asound/cards')):
            if c['usb']:
                c['channels'] = parse_stream_playback_channels(
                                    self._read('/proc/asound/card%d/stream0' % c['index']))
                return c
        return None

    # -- main loop -----------------------------------------------------------

    def listen(self):
        if not self.conf:
            self.log('no audiohub.conf contract: generic ALSA platform, monitoring off')
        else:
            self.log('platform audio hub:', self.conf['graph'],
                     '(%dms)' % (self.conf['latency_us'] / 1000),
                     '- compensation', 'on' if self.compensate else 'off (profile)')

        while self.isRunning():
            if self.conf:
                self._tick()
            self._pushStatus()
            self.stopped.wait(self.SCAN_PERIOD)

    def _tick(self):
        # USB card presence (plug/unplug edges)
        card = self._scanUsb()
        if self._card and (not card or card['id'] != self._card['id']):
            self.log('USB card gone:', self._card['id'])
            self._card = None
            self.emit('disconnected')
        if card and not self._card:
            self.log('USB card found:', card['id'], '(%dch)' % card['channels'])
            self._card = card
            self.emit('connected', card['id'], card['channels'])

        # forwarder unit health (error edges)
        states = self._unitStates()
        for sink, state in states.items():
            if state == 'failed' and self._states.get(sink) != 'failed':
                self.log(sink, 'forwarder unit FAILED')
                self.emit('error', sink)
        self._states = states

        # player compensation: constant by config, so video simply waits for
        # the audio to reach the speakers (profiles veto via .compensate)
        delay = -self.latency() if self.compensate else 0.0
        if delay != self._appliedDelay:
            applied = False
            for p in self.hplayer.players():
                if p.status('isReady'):
                    p._applyAudioDelay(delay)
                    applied = True
            if applied:
                self._appliedDelay = delay

    # -- status --------------------------------------------------------------

    def _sinkState(self, sink):
        unit = self._states.get(sink, 'unknown')
        if sink == 'usb':
            if not self._card:
                return 'absent'
            return 'active' if unit == 'active' else 'error'
        return 'active' if unit == 'active' else 'error'

    def _pushStatus(self):
        if self.conf:
            status = {
                'mode':         'hub',
                'graph':        self.conf['graph'],
                'latency-ms':   self.conf['latency_us'] / 1000.0,
                'jack':         self._sinkState('jack'),
                'hdmi':         self._sinkState('hdmi'),
                'usb':          self._sinkState('usb'),
                'usb-card':     self._card['id'] if self._card else None,
                'usb-channels': self._card['channels'] if self._card else 0,
            }
        else:
            status = {'mode': 'default',
                      'jack': 'default', 'hdmi': 'default', 'usb': 'default'}

        self._resend -= 1
        if status == self._lastSent and self._resend > 0:
            return
        self._lastSent = status
        self._resend = self.RESEND_EVERY
        h = self.hplayer.interface('http2')
        if h:
            h.send('audio-status', status)
