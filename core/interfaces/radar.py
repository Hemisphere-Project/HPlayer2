from .serialbase import SerialBase

import time


class RadarInterface(SerialBase):
    """
    HLK-LD2450 24GHz radar presence, read over USB from an ESP32-C3 (extra/arduino/radar_c3).

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
        for tok in parts[1:]:
            try:
                x, y, v = (int(n) for n in tok.split(','))
            except ValueError:
                continue
            if 0 < y <= rng and abs(x) <= wid:
                raw = True
                break
        self._debounce(raw)

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
