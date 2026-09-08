from .base import BaseInterface

from datetime import datetime
import subprocess
import glob


class ScheduleInterface(BaseInterface):
    """
    Generic playback window: enable/disable autonomous playback on a daily schedule,
    optionally restricted to certain weekdays (a museum closed on Mondays).

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
        # Which weekdays the window applies to: 7 chars, Monday first (Mon..Sun), '1' = open
        # that day, '0' = closed all day. Default = every day, so adding this changes nothing
        # for an existing config. A museum closed on Mondays is "0111111".
        'schedule-days':   '1111111',
    }
    DAYS_ALL = '1111111'

    def __init__(self, hplayer, tick=30, requireRtc=False):
        super().__init__(hplayer, "Schedule")
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)
        self.tick = tick
        self.requireRtc = requireRtc    # if True, never gate without a real RTC (fail open + warn)
        self.rtcPresent = False
        self._warnedClock = False
        self._lastOpen = None

    #
    # public
    #

    def isOpen(self):
        if not self._cfgBool('schedule-enable'):
            return True
        if self.requireRtc and not self.rtcPresent:
            return True                 # no trustworthy clock -> don't gate (see _checkRtc warning)
        if not self._clockSane():
            return True                 # RTC present but never set (dead cell, 2000-01-01) -> same thing
        o = self._parseHM(self.hplayer.settings.get('schedule-open'))
        c = self._parseHM(self.hplayer.settings.get('schedule-close'))
        if o is None or c is None or o == c:
            return True                 # misconfigured / degenerate -> fail open
        now = datetime.now()
        mins = now.hour * 60 + now.minute
        if o < c:
            # The window sits inside one day: that day must be an open day.
            return self._dayOpen(now.weekday()) and (o <= mins < c)
        # Window crosses midnight: it BELONGS to the day it started on, so the small hours
        # after midnight are still the previous day's window (a Sunday 22:00-02:00 window
        # plays into Monday morning even when Monday itself is a closed day).
        if mins >= o:
            return self._dayOpen(now.weekday())
        return self._dayOpen((now.weekday() - 1) % 7)

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
        # re-detect the RTC each tick: keeps the fail-open guarantee honest if a
        # module is missing/removed at runtime, and the http2 badge accurate
        self.rtcPresent = bool(glob.glob('/dev/rtc*'))
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

    def _clockSane(self):
        """A system clock before 2021 is a clock nobody set: a virgin or dead-cell DS1307 wakes on
        2000-01-01 and the schedule would then gate on a date that means nothing -- the whole
        installation silent, no error anywhere (Biennale 2026, master 069, 2026-09-08). Treat it
        like a missing RTC: play unrestricted, say so once. Same year<2021 rule as pi-tools' datesync."""
        sane = datetime.now().year >= 2021
        if not sane and not self._warnedClock:
            self._warnedClock = True
            self.log("WARNING: system clock reads %s — RTC never set or its cell is dead; "
                     "schedule NOT enforced until the clock is set" % datetime.now().strftime('%Y-%m-%d'))
        return sane

    def _pushStatus(self, openNow):
        h = self.hplayer.interface('http2')
        if h:
            h.send('schedule-status', {
                'enabled': self._cfgBool('schedule-enable'),
                'rtc': self.rtcPresent,
                'clockOk': self._clockSane(),
                'open': openNow,
                'days': self._cfgDays(),
                'dayOpen': self._dayOpen(datetime.now().weekday()),
            })

    def _cfgDays(self):
        """The weekday mask, normalised to exactly 7 chars of '0'/'1' (Monday first).
        Anything malformed falls back to every day — the interface fails OPEN, never silent."""
        raw = str(self.hplayer.settings.get('schedule-days') or '')
        mask = ''.join('1' if c not in ('0', 'false', 'False') else '0' for c in raw)
        if len(mask) != 7:
            return self.DAYS_ALL
        return mask

    def _dayOpen(self, weekday):
        """weekday: Monday=0 .. Sunday=6 (datetime.weekday())."""
        return self._cfgDays()[weekday] == '1'

    def _cfgBool(self, key):
        return self.hplayer.settings.get(key) in (True, 1, '1', 'true', 'True', 'on')

    @staticmethod
    def _parseHM(val):
        try:
            h, m = str(val).split(':')
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None
