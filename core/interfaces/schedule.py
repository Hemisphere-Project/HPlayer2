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
        # 2026-09-29 (MBA garden, Thomas): a clean slate around the window — reboot the player
        # REBOOT_BEFORE_OPEN min before the window opens and REBOOT_AFTER_CLOSE min after it
        # closes, on open days only, and only when the schedule is enabled, an RTC is present, the
        # clock is sane and the player has been up > REBOOT_MIN_UPTIME s (so a slow boot into the
        # slot can never loop). Not gated on playback: a player playing outside its window is the
        # dirty state this clears. A power cut is a dirty stop; this is a clean one: /data
        # unmounts, mpv/HPlayer2/tmpfs start fresh every day.
        'schedule-reboot': False,
    }
    REBOOT_BEFORE_OPEN = 10     # minutes
    REBOOT_AFTER_CLOSE = 5      # minutes
    REBOOT_SLOT_MINUTES = 3     # the decision window (the tick is 30 s)
    REBOOT_MIN_UPTIME = 900     # seconds
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
        self._rebootSlotDone = None     # "<date>-<label>" of the last slot acted on (or skipped)

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
        try:
            self._rebootTick()
        except Exception as e:
            self.log("schedule-reboot error:", e)

    #
    # clean-slate reboot around the window (schedule-reboot)
    #

    def _rebootSlots(self):
        """[(label, minute-of-day)] for today, or [] when the option cannot act: disabled, no RTC,
        insane clock, closed day, malformed or midnight-crossing window (not handled: a window that
        belongs to the previous day has no clean 'before open' on this one)."""
        if not (self._cfgBool('schedule-reboot') and self._cfgBool('schedule-enable')):
            return []
        if not self.rtcPresent or not self._clockSane():
            return []
        o = self._parseHM(self.hplayer.settings.get('schedule-open'))
        c = self._parseHM(self.hplayer.settings.get('schedule-close'))
        if o is None or c is None or not (o < c):
            return []
        if not self._dayOpen(datetime.now().weekday()):
            return []
        slots = [('before open', o - self.REBOOT_BEFORE_OPEN), ('after close', c + self.REBOOT_AFTER_CLOSE)]
        return [(l, m) for l, m in slots if 0 <= m < 1440]

    @staticmethod
    def _uptime():
        try:
            with open('/proc/uptime') as f:
                return float(f.read().split()[0])
        except Exception:
            return 0.0

    def _rebootTick(self):
        now = datetime.now()
        mins = now.hour * 60 + now.minute
        for label, slot in self._rebootSlots():
            if not (slot <= mins < slot + self.REBOOT_SLOT_MINUTES):
                continue
            key = "%s-%s" % (now.date(), label)
            if self._rebootSlotDone == key:
                return
            self._rebootSlotDone = key          # one decision per slot, whatever it is
            up = self._uptime()
            if up < self.REBOOT_MIN_UPTIME:
                self.log("schedule-reboot (%s): skipped, up only %d s" % (label, up))
                return
            # Deliberately NOT gated on "not playing": both slots sit outside the window, so a
            # player found playing there is either a manual test or exactly the stuck state this
            # option exists to clear (Thomas, 2026-09-29). The clean slate wins.
            self.log("schedule-reboot (%s): RTC ok, up %d min -> rebooting now" % (label, up // 60))
            self.emit('reboot', label)
            subprocess.Popen(['systemctl', 'reboot'])
            return

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
                'reboot': self._cfgBool('schedule-reboot'),
                'rebootSlots': ' / '.join('%02d:%02d %s' % (m // 60, m % 60, l) for l, m in self._rebootSlots()),
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
