from datetime import datetime

import pytest

import core.interfaces.schedule as schedmod
from core.engine.hplayer import HPlayer2
from core.interfaces.schedule import ScheduleInterface

# 2026-10-12 is a Monday: day d of that week is 12 + d (Mon=0 .. Sun=6)
def at(day, hm):
    h, m = hm.split(':')
    return datetime(2026, 10, 12 + day, int(h), int(m))

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

# the MBA garden's window: 10:00-18:00, closed on Tuesdays, louder on the weekend
GARDEN = dict(schedule_open='10:00', schedule_close='18:00', schedule_days='1011111')
WEEKEND = [35, None, 35, 35, 35, 50, 50]


@pytest.fixture(autouse=True)
def fresh_settings():
    """Settings._settings is a CLASS dict, shared by every HPlayer2 of the process: put it back
    after each test, or one test's schedule-volumes leaks into the next."""
    from core.engine.settings import Settings
    saved = dict(Settings._settings)
    yield
    Settings._settings.clear()
    Settings._settings.update(saved)


@pytest.fixture
def clock(monkeypatch):
    """clock.now = <datetime> sets what the interface reads as the system clock."""
    class Clock:
        now = at(MON, '12:00')
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return Clock.now
    monkeypatch.setattr(schedmod, 'datetime', FakeDatetime)
    monkeypatch.setattr(schedmod.glob, 'glob', lambda pat: ['/dev/rtc0'])
    return Clock


def make(**settings):
    hplayer = HPlayer2(mediaPath=[])
    hplayer.settings._ready = True              # no file: just arm set()
    sched = ScheduleInterface(hplayer, 30, True)
    sched.rtcPresent = True
    hplayer.settings.set('schedule-enable', True)
    for k, v in settings.items():
        hplayer.settings.set(k.replace('_', '-'), v)
    events = []
    hplayer.on('schedule.*')(lambda ev, *a: events.append((ev, a[0] if a else None)))
    return sched, events


def test_the_window_gates_as_before(clock):
    sched, _ = make(**GARDEN)
    for when, expect in [(at(MON, '09:59'), False), (at(MON, '10:00'), True),
                         (at(MON, '17:59'), True), (at(MON, '18:00'), False),
                         (at(TUE, '12:00'), False), (at(WED, '12:00'), True)]:
        clock.now = when
        assert sched.isOpen() is expect, when


def test_a_clock_nobody_set_fails_open_and_carries_no_day_volume(clock):
    sched, events = make(schedule_volumes=WEEKEND, **GARDEN)
    clock.now = datetime(2000, 1, 1, 3, 0)      # a Saturday, at night: would be closed
    assert sched.isOpen() is True
    assert sched.currentSlot() is None
    sched._evaluate()
    assert [e for e in events if e[0] == 'schedule.slot'] == []


def test_no_rtc_or_disabled_never_gates_nor_sets_a_volume(clock):
    sched, _ = make(schedule_volumes=WEEKEND, **GARDEN)
    clock.now = at(SAT, '12:00')
    sched.rtcPresent = False
    assert sched.isOpen() is True and sched.currentSlot() is None
    sched.rtcPresent = True
    sched.hplayer.settings.set('schedule-enable', False)
    assert sched.isOpen() is True and sched.currentSlot() is None


def test_the_slot_carries_the_day_volume(clock):
    sched, _ = make(schedule_volumes=WEEKEND, **GARDEN)
    clock.now = at(SAT, '12:00')
    assert sched.currentSlot() == {'day': SAT, 'open': '10:00', 'close': '18:00', 'volume': 50}
    clock.now = at(MON, '12:00')
    assert sched.currentSlot()['volume'] == 35
    clock.now = at(TUE, '12:00')
    assert sched.currentSlot() is None          # closed day


def test_no_day_volumes_means_volume_none(clock):
    sched, _ = make(**GARDEN)
    clock.now = at(SAT, '12:00')
    assert sched.currentSlot()['volume'] is None


@pytest.mark.parametrize('raw, sat', [
    ('[35, null, 35, 35, 35, 50, 50]', 50),     # JSON string (http / osc)
    ([35, '', 35, 35, 35, '60', 50], 60),        # numeric string
    ([0, 0, 0, 0, 0, 150, 0], 100),              # clamped
    ([0, 0, 0, 0, 0, -3, 0], 0),
    ([0, 0, 0, 0, 0, 'loud', 0], None),          # unreadable = keep
    ([0, 0, 0, 0, 0, ''], None),                 # not 7 values = none at all
    ('not json', None),
    (None, None),
])
def test_day_volumes_are_coerced(clock, raw, sat):
    sched, _ = make(schedule_volumes=raw, **GARDEN)
    assert sched.dayVolume(SAT) == sat


def test_slot_is_emitted_before_open_on_the_edge_and_once(clock):
    sched, events = make(schedule_volumes=WEEKEND, **GARDEN)
    clock.now = at(SAT, '09:59')
    sched._evaluate()                            # baseline: closed, nothing emitted
    assert events == []
    clock.now = at(SAT, '10:00')
    sched._evaluate()
    assert [e[0] for e in events] == ['schedule.slot', 'schedule.open']
    assert events[0][1]['volume'] == 50
    clock.now = at(SAT, '10:00')
    sched._evaluate()                            # same window: nothing new
    clock.now = at(SAT, '18:00')
    sched._evaluate()
    assert [e[0] for e in events] == ['schedule.slot', 'schedule.open', 'schedule.close']


def test_a_boot_inside_the_window_takes_the_day_volume(clock):
    sched, events = make(schedule_volumes=WEEKEND, **GARDEN)
    clock.now = at(SUN, '14:00')
    sched._evaluate()                            # first tick: baseline open, no open edge...
    assert events == [('schedule.slot', {'day': SUN, 'open': '10:00', 'close': '18:00', 'volume': 50})]


def test_editing_today_volume_reapplies_it_live(clock):
    sched, events = make(schedule_volumes=WEEKEND, **GARDEN)
    clock.now = at(SAT, '14:00')
    sched._evaluate()
    sched.hplayer.settings.set('schedule-volumes', [35, None, 35, 35, 35, 70, 50])
    sched._evaluate()
    sched.hplayer.settings.set('schedule-volumes', [35, None, 35, 35, 40, 70, 50])   # Friday: not today
    sched._evaluate()
    assert [e[1]['volume'] for e in events if e[0] == 'schedule.slot'] == [50, 70]


def test_crossing_midnight_window_belongs_to_its_start_day_and_closes(clock):
    sched, _ = make(schedule_open='22:00', schedule_close='02:00', schedule_days='0000001',
                    schedule_volumes=[10, 20, 30, 40, 50, 60, 70])
    clock.now = at(SUN, '23:00')
    assert sched.currentSlot()['volume'] == 70
    clock.now = at(SUN, '23:00').replace(day=19, hour=1)    # Monday 01:00: still Sunday's
    assert sched.currentSlot() == {'day': SUN, 'open': '22:00', 'close': '02:00', 'volume': 70}
    clock.now = at(MON, '12:00')                # between a close and the next open: closed
    assert sched.isOpen() is False              # (read open before: master's #t-082 fix)


def test_the_clean_slate_times_are_unchanged(clock):
    sched, _ = make(schedule_reboot=True, schedule_volumes=WEEKEND, **GARDEN)
    clock.now = at(SAT, '08:00')
    assert sched._rebootSlots() == [('before open', 590), ('after close', 1085)]
    clock.now = at(TUE, '08:00')
    assert sched._rebootSlots() == []


# ── the window as a STATE: a play outside it ends (hplayer2#t-073) ──────────────────────────
# W3, Tuesday 22/09 16:05: a play sent by hand on the garden's closed day ran on, because the
# window only acted on its edges and a closed day has none.

class FakePlayer:
    def __init__(self):
        self.playing = False
    def isPlaying(self):
        return self.playing


def playing_make(**settings):
    sched, events = make(**settings)
    p = FakePlayer()
    sched.hplayer._players['fake'] = p
    return sched, events, p


def closes(events):
    return [e for e in events if e[0] == 'schedule.close']


def tick(sched, clock, when):
    clock.now = when
    sched._evaluate()


def test_a_play_on_a_closed_day_stops_after_the_grace(clock):
    sched, events, p = playing_make(**GARDEN)        # default grace: 60 min
    tick(sched, clock, at(TUE, '16:00'))             # baseline: closed, idle
    p.playing = True                                 # someone presses play on the day off
    tick(sched, clock, at(TUE, '16:05'))
    assert sched.outOfHoursStop() == '17:05'
    tick(sched, clock, at(TUE, '17:04'))
    assert closes(events) == []
    tick(sched, clock, at(TUE, '17:05'))
    assert closes(events) == [('schedule.close', 'out-of-hours')]
    tick(sched, clock, at(TUE, '17:35'))             # still reported playing: one close, not a storm
    tick(sched, clock, at(TUE, '23:59'))
    assert len(closes(events)) == 1
    assert sched.outOfHoursStop() is None


def test_after_the_close_hour_too_not_only_on_a_day_off(clock):
    sched, events, p = playing_make(schedule_grace=15, **GARDEN)
    tick(sched, clock, at(MON, '18:00'))             # baseline just after the window: closed
    p.playing = True
    tick(sched, clock, at(MON, '18:30'))
    tick(sched, clock, at(MON, '18:45'))
    assert closes(events) == [('schedule.close', 'out-of-hours')]


def test_grace_zero_stops_at_the_first_tick(clock):
    sched, events, p = playing_make(schedule_grace=0, **GARDEN)
    p.playing = True
    tick(sched, clock, at(TUE, '09:00'))
    assert closes(events) == [('schedule.close', 'out-of-hours')]


def test_a_new_play_after_a_stop_gets_a_fresh_grace(clock):
    sched, events, p = playing_make(schedule_grace=30, **GARDEN)
    p.playing = True
    tick(sched, clock, at(TUE, '10:00'))
    tick(sched, clock, at(TUE, '10:30'))
    assert len(closes(events)) == 1
    p.playing = False                                # the handler stopped it
    tick(sched, clock, at(TUE, '10:31'))
    p.playing = True                                 # played by hand again
    tick(sched, clock, at(TUE, '11:00'))
    assert len(closes(events)) == 1 and sched.outOfHoursStop() == '11:30'
    tick(sched, clock, at(TUE, '11:30'))
    assert len(closes(events)) == 2


def test_a_play_that_ends_by_itself_is_never_closed(clock):
    sched, events, p = playing_make(schedule_grace=30, **GARDEN)
    p.playing = True
    tick(sched, clock, at(TUE, '10:00'))
    p.playing = False
    tick(sched, clock, at(TUE, '10:20'))
    p.playing = True                                 # a later play is timed from ITS start
    tick(sched, clock, at(TUE, '10:40'))
    tick(sched, clock, at(TUE, '11:09'))
    assert closes(events) == []


def test_playing_inside_the_window_is_untouched(clock):
    sched, events, p = playing_make(schedule_grace=0, **GARDEN)
    p.playing = True
    for hm in ('10:00', '12:00', '17:59'):
        tick(sched, clock, at(WED, hm))
    assert closes(events) == [] and sched.outOfHoursStop() is None


def test_the_window_opening_ends_the_count(clock):
    sched, events, p = playing_make(schedule_grace=60, **GARDEN)
    p.playing = True
    tick(sched, clock, at(WED, '09:30'))             # a test play before opening
    tick(sched, clock, at(WED, '10:00'))             # the window opens on it: legitimate now
    tick(sched, clock, at(WED, '10:30'))
    assert closes(events) == []


def test_never_gates_when_the_schedule_does_not(clock):
    sched, events, p = playing_make(schedule_grace=0, **GARDEN)
    p.playing = True
    sched.hplayer.settings.set('schedule-enable', False)
    tick(sched, clock, at(TUE, '12:00'))
    sched.hplayer.settings.set('schedule-enable', True)
    tick(sched, clock, datetime(2000, 1, 1, 3, 0))   # a clock nobody set: fails open
    assert closes(events) == []


def test_the_edge_close_still_fires_once_then_a_stuck_play_gets_the_grace(clock):
    sched, events, p = playing_make(schedule_grace=60, **GARDEN)
    p.playing = True
    tick(sched, clock, at(MON, '17:59'))
    tick(sched, clock, at(MON, '18:00'))             # the edge
    assert closes(events) == [('schedule.close', None)]
    tick(sched, clock, at(MON, '18:59'))             # a slave, or a stop that did not take
    tick(sched, clock, at(MON, '19:00'))
    assert closes(events) == [('schedule.close', None), ('schedule.close', 'out-of-hours')]


@pytest.mark.parametrize('raw, minutes', [
    (60, 60), ('15', 15), (0, 0), (-5, 0), (5000, 24 * 60), ('2.5', 2),
    ('', 60), (None, 60), ('never', 60),             # unreadable = the default, never "off"
])
def test_grace_is_coerced(clock, raw, minutes):
    sched, _ = make(**GARDEN)
    sched.hplayer.settings.set('schedule-grace', raw)
    assert sched.grace() == minutes


def test_the_status_says_when_it_stops(clock):
    sched, _, p = playing_make(schedule_grace=45, **GARDEN)
    sent = []
    class FakeHttp:
        def send(self, ev, data):
            sent.append((ev, data))
    sched.hplayer.interface = lambda name: FakeHttp() if name == 'http2' else None
    p.playing = True
    tick(sched, clock, at(TUE, '20:00'))
    st = sent[-1][1]
    assert st['open'] is False and st['grace'] == 45 and st['stopsAt'] == '20:45'
