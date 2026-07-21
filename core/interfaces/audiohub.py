from .base import BaseInterface

import os
import re
import shutil
import subprocess
import threading
import time


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


def pick_usb_egress(card_id, channels):
    # usbout2/usbout8 are the @args PCMs of asound.conf-rpi3-hub; cards with
    # 3..7 outs fall back to stereo for now (route tables are static per width)
    if channels >= 8:
        return 'usbout8:CARD=' + card_id
    return 'usbout2:CARD=' + card_id


def build_alsaloop_cmd(device, tlatency_us, chrt=None, alsaloop='alsaloop',
                       capture='aloopcap'):
    cmd = []
    if chrt:
        cmd += [chrt, '-f', '10']
    cmd += [alsaloop,
            '-C', capture,
            '-P', device,
            '-r', '48000',
            '-f', 'S16_LE',
            '-c', '8',
            '-t', str(int(tlatency_us)),
            '-S', 'auto']
    return cmd


class Forwarder(object):
    """Supervision state of one alsaloop (aloopcap -> a sink PCM)."""

    def __init__(self, name, device, tlatency):
        self.name = name
        self.device = device        # egress PCM, or a callable -> egress PCM
        self.tlatency = tlatency    # µs, or a callable -> µs
        self.proc = None
        self.deaths = 0             # exits since this sink appeared
        self.nextSpawn = 0          # monotonic gate for respawn backoff
        self.spawnTime = 0          # monotonic time of the last spawn
        self.xruns = 0

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def state(self):
        if self.alive():
            return 'active'
        return 'error' if self.deaths else 'off'


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------

class AudiohubInterface(BaseInterface):
    """
    Watchdog of the always-on audio hub (scripts/asound/asound.conf-rpi3-hub).

    mpv only ever plays the snd-aloop loopback; every physical output is an
    alsaloop forwarder reading the shared dsnoop capture: jack and HDMI always
    (spawned here at start), a USB card when /proc/asound shows one. Each
    forwarder is supervised independently — crash backoff, error state after
    repeated deaths, self-healing once it holds — so one bad output never
    touches the others, and playback itself never blocks on audio hardware.

    Per-sink latency targets (bench player-000, 2026-07-21): the bcm2835
    firmware sinks underrun below ~20ms (VCHIQ consumes in ~10ms quanta) so
    jack/hdmi default to 30ms; USB DACs run ~8ms. Both are live settings.

    Emits (edges only): audiohub.connected <card> <ch>, audiohub.disconnected,
    audiohub.error <sink> <detail>. Pushes an 'audio-status' dict to http2 on
    every change — the UI shows indicators, not selectors, and 'error' means
    exactly the silent-failure case: mpv plays, that output doesn't.
    """

    DEFAULTS = {
        'audiohub-usb':          True,    # live kill-switch for the USB mirror
        'audiohub-tlatency-usb':  8000,   # alsaloop target latency, µs
        'audiohub-tlatency-bcm': 30000,   # jack/hdmi: bcm2835 floor is ~20ms
    }

    SCAN_PERIOD = 1.0      # s
    ERROR_AFTER = 3        # forwarder deaths (same sink) before 'error' is emitted
    RETRY_BACKOFF = [1, 2, 5, 10]   # s between respawns; last value repeats
    HEAL_AFTER = 30        # s a respawned forwarder must hold to clear its history

    def __init__(self, hplayer):
        super().__init__(hplayer, "AudioHub", "cyan")
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)

        self._graph = None          # asound.conf carries the hub graph ?
        self._card = None           # {'id', 'index', 'channels'} of the USB card
        self._fwd = {
            'jack': Forwarder('jack', 'jackout', lambda: self._tlat('bcm')),
            'hdmi': Forwarder('hdmi', 'hdmiout', lambda: self._tlat('bcm')),
        }
        self._lastSent = None       # last status pushed to http2

    # -- config -------------------------------------------------------------

    def _enabled(self):
        try:
            return bool(self.hplayer.settings.get('audiohub-usb'))
        except Exception:
            return True

    def _tlat(self, kind):
        try:
            return int(self.hplayer.settings.get('audiohub-tlatency-' + kind))
        except (TypeError, ValueError):
            return self.DEFAULTS['audiohub-tlatency-' + kind]

    # -- probes (overridable in tests) ---------------------------------------

    def _read(self, path):
        try:
            with open(path) as fd:
                return fd.read()
        except OSError:
            return ''

    def _checkGraph(self):
        return 'pcm.hplayer' in self._read('/etc/asound.conf')

    def _ensureAloop(self):
        if any(c['id'] == 'Loopback' for c in parse_cards(self._read('/proc/asound/cards'))):
            return True
        modprobe = shutil.which('modprobe')
        if modprobe:
            subprocess.run([modprobe, 'snd-aloop'], check=False)
            return any(c['id'] == 'Loopback' for c in parse_cards(self._read('/proc/asound/cards')))
        return False

    def _scanUsb(self):
        for c in parse_cards(self._read('/proc/asound/cards')):
            if c['usb']:
                c['channels'] = parse_stream_playback_channels(
                                    self._read('/proc/asound/card%d/stream0' % c['index']))
                return c
        return None

    # -- forwarder lifecycle -------------------------------------------------

    def _spawn(self, fwd):
        alsaloop = shutil.which('alsaloop')
        if not alsaloop:
            self.log('alsaloop not found: audio outputs unavailable')
            fwd.deaths = self.ERROR_AFTER      # report 'error', don't retry-spam
            return
        device = fwd.device() if callable(fwd.device) else fwd.device
        tlat = fwd.tlatency() if callable(fwd.tlatency) else fwd.tlatency
        cmd = build_alsaloop_cmd(device, tlat, chrt=shutil.which('chrt'), alsaloop=alsaloop)
        self.log(fwd.name, '->', device, '(%dms)' % (tlat / 1000), ':', ' '.join(cmd))
        fwd.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, universal_newlines=True)
        threading.Thread(target=self._watchStderr, args=(fwd, fwd.proc), daemon=True).start()

    def _watchStderr(self, fwd, proc):
        for line in proc.stderr:
            line = line.strip()
            if not line:
                continue
            if 'xrun' in line.lower() or 'underrun' in line.lower():
                fwd.xruns += 1
            else:
                self.log('alsaloop[%s]:' % fwd.name, line)

    def _kill(self, fwd):
        if fwd.proc:
            fwd.proc.terminate()
            try:
                fwd.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                fwd.proc.kill()
            fwd.proc = None

    def _tickForwarder(self, fwd):
        # a forwarder that holds redeems its crash history,
        # a dead one is reaped and respawned with backoff
        if fwd.alive():
            if fwd.deaths and time.monotonic() - fwd.spawnTime > self.HEAL_AFTER:
                self.log(fwd.name, 'forwarder stable again')
                fwd.deaths = 0
            return

        if fwd.proc is not None:            # reap
            code = fwd.proc.poll()
            fwd.proc = None
            fwd.deaths += 1
            backoff = self.RETRY_BACKOFF[min(fwd.deaths, len(self.RETRY_BACKOFF)) - 1]
            fwd.nextSpawn = time.monotonic() + backoff
            self.log(fwd.name, 'forwarder died (exit %s), retry in %ds' % (code, backoff))
            if fwd.deaths == self.ERROR_AFTER:
                self.emit('error', fwd.name, 'forwarder crash-looping (exit %s)' % code)

        if time.monotonic() >= fwd.nextSpawn:
            self._spawn(fwd)
            fwd.spawnTime = time.monotonic()

    # -- status --------------------------------------------------------------

    def _usbState(self):
        if not self._enabled():
            return 'off'
        if not self._card:
            return 'absent'
        fwd = self._fwd.get('usb')
        return fwd.state() if fwd else 'absent'

    def _pushStatus(self):
        status = {
            'graph':        bool(self._graph),
            'jack':         self._fwd['jack'].state() if self._graph else 'legacy',
            'hdmi':         self._fwd['hdmi'].state() if self._graph else 'legacy',
            'usb':          self._usbState() if self._graph else 'off',
            'usb-card':     self._card['id'] if self._card else None,
            'usb-channels': self._card['channels'] if self._card else 0,
            'usb-xruns':    self._fwd['usb'].xruns if 'usb' in self._fwd else 0,
        }
        if status == self._lastSent:
            return
        self._lastSent = status
        h = self.hplayer.interface('http2')
        if h:
            h.send('audio-status', status)

    # -- main loop -----------------------------------------------------------

    def listen(self):
        self._graph = self._checkGraph()
        if self._graph:
            if not self._ensureAloop():
                self.log('snd-aloop unavailable: hub graph is dead, audio degraded')
                self._graph = False
        else:
            self.log('no pcm.hplayer graph in asound.conf: status-only (legacy audio)')

        while self.isRunning():
            if self._graph:
                self._tick()
            self._pushStatus()
            self.stopped.wait(self.SCAN_PERIOD)

        for fwd in self._fwd.values():
            self._kill(fwd)

    def _tick(self):
        # static sinks: always mirrored
        self._tickForwarder(self._fwd['jack'])
        self._tickForwarder(self._fwd['hdmi'])

        # USB sink: hotplug
        card = self._scanUsb() if self._enabled() else None

        if self._card and (not card or card['id'] != self._card['id']):
            self.log('USB card gone:', self._card['id'])
            if 'usb' in self._fwd:
                self._kill(self._fwd.pop('usb'))
            self._card = None
            self.emit('disconnected')

        if card and not self._card:
            self.log('USB card found:', card['id'], '(%dch)' % card['channels'])
            self._card = card
            self._fwd['usb'] = Forwarder('usb',
                                         pick_usb_egress(card['id'], card['channels']),
                                         lambda: self._tlat('usb'))
            self.emit('connected', card['id'], card['channels'])

        if 'usb' in self._fwd:
            self._tickForwarder(self._fwd['usb'])
