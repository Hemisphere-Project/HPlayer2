from .base import BaseInterface
from ..engine.conduite import Conduite

import os
import time
import serial
from serial.tools import list_ports


class DmxInterface(BaseInterface):
    """
    USB->DMX output driven by a per-media sidecar conduite (see core/engine/conduite.py).

    A generic cheap FTDI adapter is found the same way the radar box is (list_ports.grep),
    then driven at a fixed refresh rate. Two adapter families are supported, toggled live
    from http2 via the 'dmx-protocol' setting:
        open : bare FT232 "Open DMX" -- the host bit-bangs the frame (BREAK + 250k 8N2)
        pro  : Enttec "DMX USB Pro" & clones -- a 0x7E..0xE7 packet, widget keeps timing

    Every frame we read the active player's (wall-synced) position and evaluate the sidecar
    conduite of the media currently playing: output = f(conduite, playerTime). That makes DMX
    follow seeks, loops, pause and multi-device sync for free. No media / no conduite / stopped
    -> blackout. The conduite hot-reloads when its file's mtime changes (http2 Save).
    """

    DEFAULTS = {
        'dmx-filter':   '',        # USB device filter override (test rigs); empty = production default
        'dmx-protocol': 'open',    # 'open' (raw FTDI bit-bang) | 'pro' (Enttec packet)
        'dmx-fps':      30,        # frame refresh rate (Hz)
    }
    # cheap DMX dongles are almost all FT232 (VID 0403); Enttec Pro clones enumerate alike
    PROD_FILTER = "0403:6001|FT232|USB DMX|DMX USB|Enttec|DMX512"

    BAUD = {'open': 250000, 'pro': 115200}

    def __init__(self, hplayer, filter=None):
        super().__init__(hplayer, "DMX")
        self._filter = filter or self.PROD_FILTER
        # seed persistent, http2-editable tunables (must exist before settings.load())
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)

        self.serial = None
        self.port = None
        self._openProto = None          # protocol the current link was opened with
        self._openFilter = None         # filter the current port was matched with

        self._conduite = Conduite()
        self._conduiteFile = None
        self._conduiteMtime = 0
        self._mediaLoaded = -1          # sentinel != any media (incl. None)
        self._lastLevelsEmit = 0
        self._lastStatus = None

        self._bindHttp2()

    # settings override for the USB filter, read live on every scan (radar pattern)
    @property
    def filter(self):
        try:
            custom = self.hplayer.settings.get('dmx-filter')
        except Exception:
            custom = None
        return custom if custom else self._filter

    def _cfg(self, key):
        try:
            return self.hplayer.settings.get(key) or self.DEFAULTS[key]
        except Exception:
            return self.DEFAULTS[key]

    #
    # MAIN THREAD
    #

    def listen(self):
        while self.isRunning():
            if not self.serial:
                self._connect()
                continue
            self._pump()
        self._drop()

    def _connect(self):
        proto = self._cfg('dmx-protocol')
        port = None
        flt = self.filter
        if flt.startswith('/'):
            port = flt
        else:
            for dev in list_ports.grep(flt):
                port = dev.device
                break
        if not port:
            self._emitStatus(connected=False)
            self._sleep(3.0)
            return
        try:
            self.serial = serial.Serial(
                port, self.BAUD.get(proto, 250000),
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_TWO if proto == 'open' else serial.STOPBITS_ONE,
                timeout=0)
            self.port = port
            self._openProto = proto
            self._openFilter = flt
            self.log("connected to", port, "as", proto)
            self._emitStatus(connected=True)
        except Exception as e:
            self.log("connection failed on", port, ":", e)
            self.serial = None
            self.port = None
            self._sleep(3.0)

    def _pump(self):
        start = time.time()

        # protocol switched live in http2 -> reopen with the new line settings
        if self._cfg('dmx-protocol') != self._openProto:
            self.log("protocol changed -> reconnect")
            self._drop()
            return

        # filter changed -> re-scan: the first scan can beat settings.load() and
        # connect with the production fallback (seen grabbing the radar's Atom on
        # a desk rig); this also applies dmx-filter edits from http2 live.
        if self.filter != self._openFilter:
            self.log("filter changed -> reconnect")
            self._drop()
            return

        media, t, active = self._playerState()
        self._syncMedia(media)

        if active and media and self._conduite:
            frame = self._conduite.frame(t)
        else:
            frame = bytearray(512)      # blackout

        try:
            self._write(frame)
        except (serial.SerialException, OSError):
            self.log("broken link..")
            self._drop()
            return

        self._emitLevels(frame, active and bool(media))

        # pace to fps
        period = 1.0 / max(1, int(self._cfg('dmx-fps')))
        rest = period - (time.time() - start)
        if rest > 0:
            time.sleep(rest)

    #
    # PLAYER + CONDUITE
    #

    def _playerState(self):
        players = self.hplayer.players()
        if not players:
            return None, 0.0, False
        p = players[0]
        return p.status('media'), p.position(), p.isPlaying()

    def _sidecar(self, media):
        return os.path.splitext(media)[0] + '.dmx' if media else None

    def _syncMedia(self, media):
        if media != self._mediaLoaded:
            self._mediaLoaded = media
            self._conduiteFile = self._sidecar(media)
            self._loadConduite()
        elif self._conduiteFile and os.path.isfile(self._conduiteFile):
            m = os.path.getmtime(self._conduiteFile)
            if m != self._conduiteMtime:
                self.log("conduite changed on disk -> reload")
                self._loadConduite()

    def _loadConduite(self):
        text = ''
        f = self._conduiteFile
        if f and os.path.isfile(f):
            try:
                with open(f) as fd:
                    text = fd.read()
                self._conduiteMtime = os.path.getmtime(f)
            except OSError as e:
                self.log("conduite read error:", e)
        else:
            self._conduiteMtime = 0
        self._conduite = Conduite(text)
        if self._conduite.errors:
            self.log("conduite parse errors:", self._conduite.errors)
        self._emitStatus()

    #
    # TRANSPORT
    #

    def _write(self, frame):
        if self._openProto == 'pro':
            data = bytes([0x00]) + bytes(frame)        # DMX start code + 512 channels
            n = len(data)
            self.serial.write(bytes([0x7E, 0x06, n & 0xFF, (n >> 8) & 0xFF]) + data + bytes([0xE7]))
        else:
            # Open DMX: host-generated BREAK + Mark-After-Break, then start code + data.
            # Sleep granularity on a non-realtime Pi makes these longer than the spec
            # minimums (88us / 8us), which DMX receivers tolerate fine.
            self.serial.break_condition = True
            time.sleep(0.0001)
            self.serial.break_condition = False
            time.sleep(0.00002)
            self.serial.write(bytes([0x00]) + bytes(frame))
            self.serial.flush()     # drain OS buffer before the next BREAK, else the frame tail is truncated

    def _drop(self):
        try:
            if self.serial:
                self.serial.close()
        except Exception:
            pass
        self.serial = None
        self.port = None
        self._openProto = None
        self._emitStatus(connected=False)

    def _sleep(self, duration):     # interruptible by quit()
        end = time.time() + duration
        while time.time() < end and self.isRunning():
            time.sleep(0.1)

    #
    # HTTP2 bridge (status/meter out, conduite editor in)
    #

    def _http2(self):
        return self.hplayer.interface('http2')

    def _emitStatus(self, connected=None):
        h = self._http2()
        if not h:
            return
        st = {
            'connected': self.serial is not None if connected is None else connected,
            'port':      self.port,
            'protocol':  self._cfg('dmx-protocol'),
            'media':     None if self._mediaLoaded == -1 else self._mediaLoaded,
            'conduite':  self._conduiteFile,
            'channels':  self._conduite.activeChannels(),
            'errors':    self._conduite.errors,
        }
        if st != self._lastStatus:
            self._lastStatus = st
            h.send('dmx-status', st)

    def _emitLevels(self, frame, active):
        h = self._http2()
        if not h:
            return
        now = time.time()
        if now - self._lastLevelsEmit < 0.2:       # throttle the meter to ~5Hz
            return
        self._lastLevelsEmit = now
        chans = self._conduite.activeChannels() or list(range(1, 17))
        h.send('dmx-levels', {'active': active, 'levels': {c: frame[c - 1] for c in chans}})

    def _bindHttp2(self):
        # editor LOAD: http2 asks for a media's sidecar text (falls back to current media)
        @self.hplayer.on('http2.dmx-edit')
        def _edit(ev, *a):
            media = a[0] if a and a[0] else (None if self._mediaLoaded == -1 else self._mediaLoaded)
            f = self._sidecar(media)
            text = ''
            if f and os.path.isfile(f):
                try:
                    text = open(f).read()
                except OSError:
                    pass
            h = self._http2()
            if h:
                h.send('dmx-conduite', {'media': media, 'file': f, 'text': text})

        # editor SAVE: write the sidecar, hot-reload if it's the live one, report parse errors
        @self.hplayer.on('http2.dmx-save')
        def _save(ev, *a):
            if not a or not isinstance(a[0], dict):
                return
            media = a[0].get('media')
            text = a[0].get('text', '')
            f = self._sidecar(media)
            if not f:
                return
            try:
                with open(f, 'w') as fd:
                    fd.write(text)
            except OSError as e:
                self.log("conduite write error:", e)
                return
            self.log("conduite saved:", f)
            if media == self._mediaLoaded:
                self._loadConduite()
            errs = Conduite(text).errors
            h = self._http2()
            if h:
                h.send('dmx-saved', {'media': media, 'file': f, 'errors': errs})
