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
    # usbout2/usbout8 are the @args PCMs of asound.conf-rpi3-multi; cards with
    # 3..7 outs fall back to stereo for now (route tables are static per width)
    if channels >= 8:
        return 'usbout8:CARD=' + card_id
    return 'usbout2:CARD=' + card_id


def build_alsaloop_cmd(device, tlatency_us, chrt=None, alsaloop='alsaloop'):
    cmd = []
    if chrt:
        cmd += [chrt, '-f', '10']
    cmd += [alsaloop,
            '-C', 'hw:Loopback,1,0',
            '-P', device,
            '-r', '48000',
            '-f', 'S16_LE',
            '-c', '8',
            '-t', str(int(tlatency_us)),
            '-S', 'auto']
    return cmd


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------

class AudiohubInterface(BaseInterface):
    """
    Watchdog of the always-on audio graph (scripts/asound/asound.conf-rpi3-multi).

    Jack and HDMI are static slaves of the mpv-facing multi PCM and need no help.
    The USB output is a mirror: this interface scans /proc/asound for a USB card
    and supervises an alsaloop forwarder (loopback -> USB, adaptive resample) so
    a dongle can come and go without mpv ever noticing. No dongle, no forwarder:
    playback never blocks.

    Emits (edges only): audiohub.connected <card>, audiohub.disconnected,
    audiohub.error <detail>. Pushes an 'audio-status' dict to http2 every scan
    tick — the UI shows indicators, not selectors, and 'error' means exactly the
    silent-failure case: mpv plays, the USB output doesn't.
    """

    DEFAULTS = {
        'audiohub-usb':      True,    # live kill-switch for the USB mirror
        'audiohub-tlatency': 8000,    # alsaloop target latency, µs (bench-tuned)
    }

    SCAN_PERIOD = 1.0      # s
    ERROR_AFTER = 3        # forwarder deaths (same card, no unplug) before 'error'
    RETRY_BACKOFF = [1, 2, 5, 10]   # s between respawns; last value repeats
    HEAL_AFTER = 30        # s a respawned forwarder must hold to clear the error history

    def __init__(self, hplayer):
        super().__init__(hplayer, "AudioHub", "cyan")
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)

        self._graph = None          # asound.conf carries pcm.hplayer ?
        self._card = None           # {'id', 'index', 'channels'} of the mirrored card
        self._proc = None
        self._deaths = 0            # forwarder exits since this card appeared
        self._nextSpawn = 0         # monotonic gate for respawn backoff
        self._spawnTime = 0         # monotonic time of the last spawn
        self._xruns = 0
        self._lastSent = None       # last status pushed to http2

    # -- config -------------------------------------------------------------

    def _enabled(self):
        try:
            return bool(self.hplayer.settings.get('audiohub-usb'))
        except Exception:
            return True

    def _tlatency(self):
        try:
            return int(self.hplayer.settings.get('audiohub-tlatency'))
        except (TypeError, ValueError):
            return self.DEFAULTS['audiohub-tlatency']

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

    def _spawn(self, card):
        alsaloop = shutil.which('alsaloop')
        if not alsaloop:
            self.log('alsaloop not found: USB mirror unavailable')
            self._deaths = self.ERROR_AFTER    # report 'error', don't retry-spam
            return
        device = pick_usb_egress(card['id'], card['channels'])
        cmd = build_alsaloop_cmd(device, self._tlatency(),
                                 chrt=shutil.which('chrt'), alsaloop=alsaloop)
        self.log('mirroring to', device, '(%dch)' % card['channels'], ':', ' '.join(cmd))
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE, universal_newlines=True)
        threading.Thread(target=self._watchStderr, args=(self._proc,), daemon=True).start()

    def _watchStderr(self, proc):
        for line in proc.stderr:
            line = line.strip()
            if not line:
                continue
            if 'xrun' in line.lower() or 'underrun' in line.lower():
                self._xruns += 1
            else:
                self.log('alsaloop:', line)

    def _kill(self):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    # -- status --------------------------------------------------------------

    def _usbState(self):
        if not self._enabled():
            return 'off'
        if not self._card:
            return 'absent'
        if self._deaths >= self.ERROR_AFTER:
            return 'error'
        if self._proc and self._proc.poll() is None:
            return 'active'
        return 'error' if self._deaths else 'absent'

    def _pushStatus(self):
        status = {
            'graph':        bool(self._graph),
            'jack':         'on' if self._graph else 'legacy',
            'hdmi':         'on' if self._graph else 'legacy',
            'usb':          self._usbState() if self._graph else 'off',
            'usb-card':     self._card['id'] if self._card else None,
            'usb-channels': self._card['channels'] if self._card else 0,
            'usb-xruns':    self._xruns,
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
                self.log('snd-aloop unavailable: graph is degraded, USB mirror off')
                self._graph = False
        else:
            self.log('no pcm.hplayer graph in asound.conf: status-only (legacy audio)')

        while self.isRunning():
            if self._graph:
                self._tick()
            self._pushStatus()
            self.stopped.wait(self.SCAN_PERIOD)

        self._kill()

    def _tick(self):
        card = self._scanUsb() if self._enabled() else None

        # unplug / disable: stop mirroring, forget the error history
        if self._card and (not card or card['id'] != self._card['id']):
            self.log('USB card gone:', self._card['id'])
            self._kill()
            self._card = None
            self._deaths = 0
            self._xruns = 0
            self.emit('disconnected')

        # plug: adopt the card
        if card and not self._card:
            self.log('USB card found:', card['id'], '(%dch)' % card['channels'])
            self._card = card
            self._deaths = 0
            self._nextSpawn = 0
            self.emit('connected', card['id'], card['channels'])

        if not self._card:
            return

        # supervise: a forwarder that holds redeems its crash history,
        # a dead one is reaped and respawned with backoff
        if self._proc and self._proc.poll() is None:
            if self._deaths and time.monotonic() - self._spawnTime > self.HEAL_AFTER:
                self.log('forwarder stable again')
                self._deaths = 0

        if self._proc and self._proc.poll() is not None:
            code = self._proc.poll()
            self._proc = None
            self._deaths += 1
            backoff = self.RETRY_BACKOFF[min(self._deaths, len(self.RETRY_BACKOFF)) - 1]
            self._nextSpawn = time.monotonic() + backoff
            self.log('forwarder died (exit %s), retry in %ds' % (code, backoff))
            if self._deaths == self.ERROR_AFTER:
                self.emit('error', 'forwarder crash-looping (exit %s)' % code)

        if not self._proc and time.monotonic() >= self._nextSpawn:
            self._spawn(self._card)
            self._spawnTime = time.monotonic()
