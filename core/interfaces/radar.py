from .serialbase import SerialBase

import time


class RadarInterface(SerialBase):
    """
    HLK-LD2450 24GHz radar presence, read over USB from an ESP32-C3 (extra/arduino/radar_ld2450).

    The firmware is dumb: it streams one line per radar frame,
        T <x>,<y>,<v> <x>,<y>,<v> ...       (mm, mm, cm/s; bare "T" = empty)
    All the decisions live here. We gate targets against a detection box, debounce with
    separate enter/leave hysteresis, and emit edge events only:
        radar.enter  — a human entered the zone
        radar.leave  — the zone went empty
    Range / width / hysteresis are read live from settings on every frame, so http2 edits
    take effect immediately. See profiles/biennale26-radar.py for the trigger policy.
    """

    DEFAULTS = {
        'radar-filter':    '',      # USB device filter override (test rigs); empty = production default
        'radar-range':     3000,    # max distance y, mm
        'radar-width':     1500,    # max lateral |x|, mm
        'radar-enter-ms':  300,     # presence must hold this long to fire enter
        'radar-leave-ms':  1500,    # emptiness must hold this long to fire leave
    }

    def __init__(self, hplayer, filter="USB JTAG|303a:1001|CP210|USB Single Serial"):
        super().__init__(hplayer, "Radar", filter)
        # seed persistent, http2-editable tunables (must exist before settings.load())
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)
        self._present = False       # committed, debounced presence
        self._edgeSince = None      # when raw first disagreed with committed
        self._lastStatus = 0        # throttle the live http2 feedback

    # The scan loop reads .filter on every pass, so a 'radar-filter' setting in the
    # /data cfg lets one player match a non-production device (e.g. the M5 Atom desk
    # rig, FTDI-branded) without touching code — the production default stays intact.
    @property
    def filter(self):
        try:
            custom = self.hplayer.settings.get('radar-filter')
        except Exception:
            custom = None
        return custom if custom else self._filter

    @filter.setter
    def filter(self, value):
        self._filter = value

    def _cfg(self, key):
        try:
            return int(self.hplayer.settings.get(key))
        except (TypeError, ValueError):
            return self.DEFAULTS[key]

    def onLine(self, line):
        parts = line.split()
        if not parts or parts[0] != 'T':
            return                  # hello / boot spew — ignore
        rng = self._cfg('radar-range')
        wid = self._cfg('radar-width')
        raw = False
        count = 0
        nearest = None              # nearest target overall (mm), even out of zone, for tuning
        for tok in parts[1:]:
            try:
                x, y, v = (int(n) for n in tok.split(','))
            except ValueError:
                continue
            if y <= 0:
                continue
            count += 1
            if nearest is None or y < nearest:
                nearest = y
            if y <= rng and abs(x) <= wid:
                raw = True
        self._debounce(raw)
        self._pushStatus(raw, count, nearest)

    def _pushStatus(self, raw, count, nearest):
        now = time.time()
        if now - self._lastStatus < 0.2:        # ~5Hz to the UI
            return
        self._lastStatus = now
        h = self.hplayer.interface('http2')
        if h:
            h.send('radar-status', {'connected': self.serial is not None,
                                    'present': self._present, 'raw': raw,
                                    'count': count, 'near': nearest})

    def _debounce(self, raw):
        now = time.time()
        if raw == self._present:
            self._edgeSince = None
            return
        if self._edgeSince is None:
            self._edgeSince = now
        hold = self._cfg('radar-enter-ms' if raw else 'radar-leave-ms') / 1000.0
        if now - self._edgeSince >= hold:
            self._present = raw
            self._edgeSince = None
            self.emit('enter' if raw else 'leave')

    def onDisconnect(self):
        # box unplugged: forget presence so a reconnect re-arms cleanly
        self._present = False
        self._edgeSince = None
        h = self.hplayer.interface('http2')
        if h:
            h.send('radar-status', {'connected': False, 'present': False,
                                    'raw': False, 'count': 0, 'near': None})
