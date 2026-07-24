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


def parse_pcm_status(text):
    """(state, hw_ptr) from a /proc/asound/.../subN/status dump.

    The file reads 'closed' (single word, no colon) when the PCM is not
    open — that and an unreadable file both come back ('closed', None).
    """
    state, ptr = 'closed', None
    for line in text.splitlines():
        if line.startswith('state:'):
            state = line.split(':', 1)[1].strip()
        elif line.startswith('hw_ptr'):
            digits = re.sub(r'\D', '', line)
            if digits:
                ptr = int(digits)
    return state, ptr


def resolve_sink_pcms(cards):
    """jack/hdmi -> (card index, egress pcm) for the platform in `cards`.

    Mirrors audiohub-fwd's sink resolution: the Pi has one firmware card
    per output (each on its pcm0p), x86 HDA has ONE card (PCH) carrying
    analog as device 0 and HDMI as device 3.
    """
    idx = {c['id']: c['index'] for c in cards}
    if 'PCH' in idx:
        return {'jack': (idx['PCH'], 'pcm0p'), 'hdmi': (idx['PCH'], 'pcm3p')}
    sinks = {}
    if 'Headphones' in idx:
        sinks['jack'] = (idx['Headphones'], 'pcm0p')
    if 'b1' in idx:
        sinks['hdmi'] = (idx['b1'], 'pcm0p')
    return sinks


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

    Health is judged on TWO axes. Unit axis: forwarder ActiveState ('error'
    chip when not active). Flow axis: unit liveness lies — a sink can wedge
    with its unit 'active', alsaloop spinning and hw_ptr frozen (bench
    2026-07-21, twice). So while the loopback cable has a writer (mpv is
    playing), each sink's egress hw_ptr must advance between scans;
    STALL_TICKS consecutive misses turn the chip 'stalled'. The horizon
    (~10s) sits just past the forwarder's own ~9s flow-watchdog recycle, so
    a successful platform self-heal never blips the chip.

    Without the contract file the platform is generic: no compensation, no
    monitoring, chips report 'default' — HPlayer2 never touches audio config.

    Emits (edges only): audiohub.connected <card> <ch>, audiohub.disconnected,
    audiohub.error <sink> (unit failed, or stall onset). 'error'/'stalled' on
    a chip means the silent-failure case: mpv plays, that output doesn't.
    """

    SCAN_PERIOD = 2.0      # s
    RESEND_EVERY = 5       # ticks: re-push unchanged status for late web clients
    STALL_TICKS = 5        # scans without hw_ptr progress before 'stalled'
    UNITS = {'jack': 'audiohub@jack.service',
             'hdmi': 'audiohub@hdmi.service',
             'usb':  'audiohub@usb.service'}

    def __init__(self, hplayer):
        super().__init__(hplayer, "AudioHub", "cyan")
        self.compensate = True      # profile veto: start-sync keeps visual priority
        self.conf = read_audio_conf()
        self._card = None           # USB card currently seen
        self._states = {}           # sink -> unit state, for error edges
        self._flow = {}             # sink -> {'ptr', 'miss'}, for stall detection
        self._lastSent = None
        self._resend = 0
        self._appliedDelay = None

    def latency(self):
        """Pipeline latency in seconds (0.0 on a generic platform)."""
        return self.conf['latency_us'] / 1e6 if self.conf else 0.0

    # -- probes (overridable in tests) ---------------------------------------

    def _readConf(self):
        return read_audio_conf()

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

    def _scanUsb(self, cards):
        for c in cards:
            if c['usb']:
                c['channels'] = parse_stream_playback_channels(
                                    self._read('/proc/asound/card%d/stream0' % c['index']))
                return c
        return None

    def _pcmStatus(self, card, pcm):
        return parse_pcm_status(
            self._read('/proc/asound/card%d/%s/sub0/status' % (card, pcm)))

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
        # live config: `audiohub set` (or any app writing /data/audiohub.conf)
        # must not need an HPlayer2 restart — latency re-compensates below
        conf = self._readConf()
        if conf != self.conf and conf is not None:
            self.log('platform audio config changed:', conf)
            self.conf = conf

        # USB card presence (plug/unplug edges)
        cards = parse_cards(self._read('/proc/asound/cards'))
        card = self._scanUsb(cards)
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

        # sink flow (stall edges): only meaningful with a writer on the cable
        self._flowTick(cards)

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

    def _flowTick(self, cards):
        lb = next((c['index'] for c in cards if c['id'] == 'Loopback'), None)
        cable = self._pcmStatus(lb, 'pcm0p')[0] if lb is not None else 'closed'
        if cable != 'RUNNING':
            self._flow = {}     # no writer on the cable: idle sinks are legit
            return

        sinks = resolve_sink_pcms(cards)
        if self._card:
            sinks['usb'] = (self._card['index'], 'pcm0p')
        for sink, (card, pcm) in sinks.items():
            if self._states.get(sink) != 'active':
                self._flow.pop(sink, None)   # unit down: that's the unit axis
                continue
            state, ptr = self._pcmStatus(card, pcm)
            f = self._flow.setdefault(sink, {'ptr': None, 'miss': 0})
            if state == 'RUNNING' and ptr is not None and ptr != f['ptr']:
                f['ptr'], f['miss'] = ptr, 0
                continue
            f['miss'] += 1
            f['ptr'] = ptr if ptr is not None else f['ptr']
            if f['miss'] == self.STALL_TICKS:
                self.log(sink, 'sink STALLED with a live cable (%s)' % state)
                self.emit('error', sink)

    # -- status --------------------------------------------------------------

    def _stalled(self, sink):
        f = self._flow.get(sink)
        return f is not None and f['miss'] >= self.STALL_TICKS

    def _sinkState(self, sink):
        if sink == 'usb' and not self._card:
            return 'absent'
        if self._states.get(sink, 'unknown') != 'active':
            return 'error'
        if self._stalled(sink):
            return 'stalled'
        return 'active'

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
