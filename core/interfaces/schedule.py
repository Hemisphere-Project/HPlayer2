from .base import BaseInterface

from datetime import datetime, timedelta
import subprocess
import glob
import json


DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def _parseHM(val):
    """'HH:MM' -> minute of the day (0..1439), None when malformed or out of range."""
    try:
        h, m = str(val).split(':')
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def _fmtHM(mins):
    mins %= 1440
    return '%02d:%02d' % (mins // 60, mins % 60)


def clean_grid(grid):
    """Coerce a `schedule-grid` value onto its canonical shape, or None when it is not a grid.

    Shape: 7 lists, Monday first (Mon..Sun); each list holds that day's slots, in the order given,
    as {'open': 'HH:MM', 'close': 'HH:MM', 'volume': 0..100 | None}. A JSON string is accepted
    (http / osc). A slot whose close is EARLIER than its open crosses midnight and belongs to the
    day it started on. A slot that cannot be read (bad time, open == close) is dropped, so a typo
    never opens a hole elsewhere; an empty list is a closed day. Volume unset/blank/bad = None =
    "leave the volume where it is" (the last known one). Anything that is not 7 lists -> None, and
    the interface then falls back to the legacy single window (schedule-open/-close/-days)."""
    if isinstance(grid, str):
        try:
            grid = json.loads(grid)
        except ValueError:
            return None
    if not isinstance(grid, (list, tuple)) or len(grid) != 7:
        return None
    out = []
    for day in grid:
        if not isinstance(day, (list, tuple)):
            return None
        slots = []
        for s in day:
            if not isinstance(s, dict):
                continue
            o, c = _parseHM(s.get('open')), _parseHM(s.get('close'))
            if o is None or c is None or o == c:
                continue
            vol = s.get('volume')
            try:
                vol = None if vol in (None, '') else max(0, min(100, int(float(vol))))
            except (TypeError, ValueError):
                vol = None
            slots.append({'open': _fmtHM(o), 'close': _fmtHM(c), 'volume': vol})
        out.append(slots)
    return out


class ScheduleInterface(BaseInterface):
    """
    Generic playback grid: enable/disable autonomous playback on a weekly schedule of time
    slots — several per day, a slot may end past midnight, each may carry its own volume.

    Settable from a profile and from http2 (settings keys below). Emits
        schedule.open   — playback just became allowed (a slot started after a gap)
        schedule.close  — playback just stopped being allowed (the last slot in a row ended)
        schedule.slot   — the slot in force changed (also once at startup when inside one), with
                          {'day', 'open', 'close', 'volume'}; volume None = leave it as it is.
                          Back-to-back slots (10:00-12:00 then 12:00-18:00) change the slot, and
                          its volume, without a close/open in between.
    and exposes isOpen() for trigger sources (e.g. the radar) to consult. Disabled =
    always open (fail-open), so adding this interface changes nothing until configured.

    The grid (`schedule-grid`, see clean_grid) replaces the single daily window. While it is
    unset the legacy keys still apply, read as one slot per open day — an existing config
    behaves exactly as before.

    Clock source is the system clock. The RTC's job is to keep that correct while a
    player is offline (no NTP), so we don't read the RTC directly — we detect it and
    WARN if it is missing while the schedule is enabled (offline players would drift).

    Generalises the one-off hwclock logic in profiles/biennale24-rtc.py into a reusable
    interface. biennale-2026-module-radar #t-005; the grid hplayer2 #t-082.
    """

    DEFAULTS = {
        'schedule-enable': False,       # off = always open (no behaviour change)
        # The weekly grid (clean_grid). None = not set: the legacy single window below applies.
        'schedule-grid':   None,
        # Legacy single window, read only while schedule-grid is unset.
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
        self._lastOpen = None
        self._lastSlot = False          # False = no baseline yet; None = outside every slot

    #
    # public
    #

    def isOpen(self):
        grid = self._gate()
        return grid is None or self._slotAt(grid, datetime.now()) is not None

    def grid(self):
        """The grid in force: schedule-grid when it is one, else the legacy single window as one
        slot per open day; None = nothing readable -> the interface fails open."""
        g = clean_grid(self.hplayer.settings.get('schedule-grid'))
        if g is not None:
            return g
        o = _parseHM(self.hplayer.settings.get('schedule-open'))
        c = _parseHM(self.hplayer.settings.get('schedule-close'))
        if o is None or c is None or o == c:
            return None
        slot = {'open': _fmtHM(o), 'close': _fmtHM(c), 'volume': None}
        return [[dict(slot)] if d == '1' else [] for d in self._cfgDays()]

    def currentSlot(self):
        """The slot in force now as {'day', 'open', 'close', 'volume'} (day = the weekday it
        STARTED on, Monday=0), or None: outside every slot, or the schedule is not gating."""
        grid = self._gate()
        return None if grid is None else self._slotAt(grid, datetime.now())

    def daySpan(self, weekday):
        """(first open, last close) in minutes from that day's midnight, over the slots that
        START on `weekday` (Monday=0); a past-midnight end counts for the day it started, so the
        close may exceed 1440. None = a closed day (or no readable grid).
        The clean-slate reboot fires once a day around this span (Thomas, 2026-10-12)."""
        grid = self.grid()
        if grid is None or not grid[weekday]:
            return None
        first, last = None, None
        for s in grid[weekday]:
            o, c = _parseHM(s['open']), _parseHM(s['close'])
            if c <= o:
                c += 1440
            first = o if first is None else min(first, o)
            last = c if last is None else max(last, c)
        return (first, last)

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
        grid = self._gate()
        slot = None if grid is None else self._slotAt(grid, datetime.now())
        openNow = grid is None or slot is not None     # isOpen(), from the same instant as slot
        if self._lastOpen is None:
            self._lastOpen = openNow        # baseline, no edge at startup
        elif openNow != self._lastOpen:
            self._lastOpen = openNow
            self.emit('open' if openNow else 'close')
        # The slot: announced at startup too, so a player that boots (or is power-cycled) into a
        # slot takes that slot's volume, not the one persisted from the slot before.
        if slot != self._lastSlot:
            self._lastSlot = slot
            if slot is not None:
                self.emit('slot', dict(slot))
        self._pushStatus(openNow, slot)

    #
    # internals
    #

    def _gate(self):
        """The grid to gate on, or None when the schedule does not gate (always open)."""
        if not self._cfgBool('schedule-enable'):
            return None
        if self.requireRtc and not self.rtcPresent:
            return None                 # no trustworthy clock -> don't gate (see _checkRtc warning)
        return self.grid()              # None: misconfigured / degenerate -> fail open

    @staticmethod
    def _slotAt(grid, now):
        """The first slot (in grid order) holding `now`: one started today, or one started
        yesterday that runs past midnight (it belongs to the day it started, so a Sunday
        22:00-02:00 slot plays into Monday morning even when Monday itself is a closed day)."""
        mins = now.hour * 60 + now.minute
        today = now.weekday()
        yesterday = (today - 1) % 7
        for s in grid[today]:
            o, c = _parseHM(s['open']), _parseHM(s['close'])
            if (o < c and o <= mins < c) or (o > c and mins >= o):
                return dict(s, day=today)
        for s in grid[yesterday]:
            o, c = _parseHM(s['open']), _parseHM(s['close'])
            if o > c and mins < c:
                return dict(s, day=yesterday)
        return None

    def _nextOpen(self, grid, now):
        """'Tue 10:00' — the next slot start after `now` within a week, or '' when none."""
        base = now.replace(second=0, microsecond=0)
        mins = base.hour * 60 + base.minute
        for ahead in range(8):
            wd = (now.weekday() + ahead) % 7
            starts = sorted(_parseHM(s['open']) for s in grid[wd])
            for o in starts:
                if ahead == 0 and o <= mins:
                    continue
                when = base + timedelta(days=ahead)
                return ('' if ahead == 0 else DAY_NAMES[when.weekday()] + ' ') + _fmtHM(o)
        return ''

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

    def _pushStatus(self, openNow, slot=None):
        h = self.hplayer.interface('http2')
        if h:
            now = datetime.now()
            grid = self.grid()
            h.send('schedule-status', {
                'enabled': self._cfgBool('schedule-enable'),
                'rtc': self.rtcPresent,
                'open': openNow,
                'days': self._cfgDays(),
                'dayOpen': bool(grid and grid[now.weekday()]) if grid is not None else True,
                'slot': ('%s–%s' % (slot['open'], slot['close'])) if slot else '',
                'volume': slot['volume'] if slot else None,
                'next': self._nextOpen(grid, now) if grid is not None else '',
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
        """weekday: Monday=0 .. Sunday=6 (datetime.weekday()). A day with at least one slot
        starting on it."""
        grid = self.grid()
        return True if grid is None else bool(grid[weekday])

    def _cfgBool(self, key):
        return self.hplayer.settings.get(key) in (True, 1, '1', 'true', 'True', 'on')

    @staticmethod
    def _parseHM(val):
        return _parseHM(val)
