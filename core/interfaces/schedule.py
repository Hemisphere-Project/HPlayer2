from .base import BaseInterface

from datetime import datetime
import subprocess
import glob


class ScheduleInterface(BaseInterface):
    """
    Generic playback window: enable/disable autonomous playback on a daily schedule.

    Settable from a profile and from http2 (settings keys below). Emits edge events
        schedule.open   — the window just opened
        schedule.close  — the window just closed
    and exposes isOpen() for trigger sources (e.g. the radar) to consult. Disabled =
    always open (fail-open), so adding this interface changes nothing until configured.

    Clock source is the system clock. The RTC's job is to keep that correct while a
    player is offline (no NTP), so we don't read the RTC directly — we detect it and
    WARN if it is missing while the schedule is enabled (offline players would drift).

    Generalises the one-off hwclock logic in profiles/biennale24-rtc.py into a reusable
    interface. biennale-2026-module-radar #t-005.
    """

    DEFAULTS = {
        'schedule-enable': False,       # off = always open (no behaviour change)
        'schedule-open':   '10:00',     # daily window start "HH:MM"
        'schedule-close':  '19:00',     # daily window end   "HH:MM"
    }

    def __init__(self, hplayer, tick=30, requireRtc=False):
        super().__init__(hplayer, "Schedule")
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)
        self.tick = tick
        self.requireRtc = requireRtc    # if True, never gate without a real RTC (fail open + warn)
        self.rtcPresent = False
        self._lastOpen = None

    #
    # public
    #

    def isOpen(self):
        if not self._cfgBool('schedule-enable'):
            return True
        if self.requireRtc and not self.rtcPresent:
            return True                 # no trustworthy clock -> don't gate (see _checkRtc warning)
        o = self._parseHM(self.hplayer.settings.get('schedule-open'))
        c = self._parseHM(self.hplayer.settings.get('schedule-close'))
        if o is None or c is None or o == c:
            return True                 # misconfigured / degenerate -> fail open
        mins = datetime.now().hour * 60 + datetime.now().minute
        if o < c:
            return o <= mins < c
        return mins >= o or mins < c    # window crosses midnight

    #
    # thread
    #

    def listen(self):
        self._checkRtc()
        while self.isRunning():
            try:
                self._evaluate()
            except Exception as e:
                self.log("schedule error:", e)
            self.stopped.wait(self.tick)    # interruptible; returns at once on quit()

    def _evaluate(self):
        openNow = self.isOpen()
        if self._lastOpen is None:
            self._lastOpen = openNow        # baseline, no edge at startup
        elif openNow != self._lastOpen:
            self._lastOpen = openNow
            self.emit('open' if openNow else 'close')
        self._pushStatus(openNow)

    #
    # internals
    #

    def _checkRtc(self):
        self.rtcPresent = bool(glob.glob('/dev/rtc*'))
        if self.rtcPresent:
            when = ""
            try:
                r = subprocess.run(['hwclock', '--show'], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=5)
                when = r.stdout.decode('utf-8', 'replace').strip()
            except Exception:
                pass
            self.log("RTC present", when)
        elif self._cfgBool('schedule-enable'):
            self.log("WARNING: schedule enabled but no RTC found — timekeeping relies on "
                     "NTP/system clock; offline players will drift")

    def _pushStatus(self, openNow):
        h = self.hplayer.interface('http2')
        if h:
            h.send('schedule-status', {
                'enabled': self._cfgBool('schedule-enable'),
                'rtc': self.rtcPresent,
                'open': openNow,
            })

    def _cfgBool(self, key):
        return self.hplayer.settings.get(key) in (True, 1, '1', 'true', 'True', 'on')

    @staticmethod
    def _parseHM(val):
        try:
            h, m = str(val).split(':')
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None
