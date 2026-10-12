from datetime import datetime

import pytest

import core.interfaces.schedule as schedmod
from core.engine.hplayer import HPlayer2
from core.interfaces.schedule import ScheduleInterface, clean_grid

# 2026-10-12 is a Monday: day d of that week is 12 + d (Mon=0 .. Sun=6)
def at(day, hm):
    h, m = hm.split(':')
    return datetime(2026, 10, 12 + day, int(h), int(m))

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


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


def slot(o, c, v=None):
    return {'open': o, 'close': c, 'volume': v}


def week(**days):
    g = [[] for _ in range(7)]
    for name, slots in days.items():
        g[('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun').index(name)] = slots
    return g


def test_legacy_single_window_still_applies_without_a_grid(clock):
    sched, _ = make(schedule_open='10:00', schedule_close='18:00', schedule_days='1011111')
    for when, expect in [(at(MON, '09:59'), False), (at(MON, '10:00'), True),
                         (at(MON, '17:59'), True), (at(MON, '18:00'), False),
                         (at(TUE, '12:00'), False), (at(WED, '12:00'), True)]:
        clock.now = when
        assert sched.isOpen() is expect, when


def test_legacy_window_past_midnight_closes_at_its_end(clock):
    # Sunday 22:00-02:00 only: plays into Monday morning, and NOT through Monday noon
    sched, _ = make(schedule_open='22:00', schedule_close='02:00', schedule_days='0000001')
    for when, expect in [(at(SAT, '23:00'), False), (at(SUN, '21:59'), False),
                         (at(SUN, '23:00'), True), (at(SUN + 1, '01:59'), True),
                         (at(SUN + 1, '02:00'), False), (at(SUN + 1, '12:00'), False)]:
        clock.now = when
        assert sched.isOpen() is expect, when


def test_legacy_degenerate_window_fails_open(clock):
    sched, _ = make(schedule_open='10:00', schedule_close='10:00')
    clock.now = at(MON, '03:00')
    assert sched.isOpen() is True
    assert sched.currentSlot() is None


def test_several_slots_a_day_each_with_its_volume(clock):
    sched, _ = make(schedule_grid=week(mon=[slot('10:00', '12:00', 30), slot('14:00', '18:00', 50)]))
    clock.now = at(MON, '11:00')
    assert sched.isOpen() and sched.currentSlot()['volume'] == 30
    clock.now = at(MON, '13:00')
    assert not sched.isOpen() and sched.currentSlot() is None
    clock.now = at(MON, '15:00')
    assert sched.currentSlot() == {'day': MON, 'open': '14:00', 'close': '18:00', 'volume': 50}
    clock.now = at(TUE, '11:00')
    assert not sched.isOpen()                    # an empty day is a closed day


def test_past_midnight_slot_belongs_to_the_day_it_started(clock):
    sched, _ = make(schedule_grid=week(fri=[slot('20:00', '01:00', 40)]))
    clock.now = at(SAT, '00:30')                 # Saturday has no slot of its own
    assert sched.isOpen() and sched.currentSlot()['day'] == FRI
    clock.now = at(SAT, '01:00')
    assert not sched.isOpen()
    clock.now = at(FRI, '00:30')                 # Thursday has nothing spilling into Friday
    assert not sched.isOpen()


def test_grid_wins_over_the_legacy_keys(clock):
    sched, _ = make(schedule_open='10:00', schedule_close='18:00',
                    schedule_grid=week(mon=[slot('20:00', '22:00')]))
    clock.now = at(MON, '12:00')
    assert not sched.isOpen()
    clock.now = at(MON, '21:00')
    assert sched.isOpen()


def test_disabled_or_no_rtc_never_gates(clock):
    sched, _ = make(schedule_grid=week(mon=[slot('10:00', '12:00', 30)]))
    clock.now = at(MON, '20:00')
    sched.rtcPresent = False                     # requireRtc: no trustworthy clock
    assert sched.isOpen() and sched.currentSlot() is None
    sched.rtcPresent = True
    sched.hplayer.settings.set('schedule-enable', False)
    assert sched.isOpen() and sched.currentSlot() is None


def test_clean_grid_coerces_and_drops_what_it_cannot_read():
    raw = ('[[{"open":"10:00","close":"12:00","volume":"35"},{"open":"bad","close":"12:00"},'
           '{"open":"13:00","close":"13:00"},{"open":"14:00","close":"25:00"},'
           '{"open":"14:00","close":"16:00","volume":""},{"open":"16:00","close":"17:00","volume":250}],'
           '[],[],[],[],[],[]]')
    g = clean_grid(raw)
    assert g[0] == [slot('10:00', '12:00', 35), slot('14:00', '16:00'), slot('16:00', '17:00', 100)]
    assert g[1:] == [[]] * 6
    assert clean_grid(None) is None
    assert clean_grid([[]] * 6) is None          # not a week -> the legacy window applies
    assert clean_grid('not json') is None


def test_evaluate_emits_edges_and_slots(clock):
    sched, events = make(schedule_grid=week(mon=[slot('10:00', '12:00', 30), slot('12:00', '14:00'),
                                                 slot('16:00', '18:00', 50)]))
    clock.now = at(MON, '11:00')
    sched._evaluate()                            # booted inside a slot: no edge, its volume applies
    assert events == [('schedule.slot', {'day': MON, 'open': '10:00', 'close': '12:00', 'volume': 30})]
    events.clear()
    clock.now = at(MON, '11:30')
    sched._evaluate()
    assert events == []                          # same slot: nothing
    clock.now = at(MON, '12:00')
    sched._evaluate()                            # back-to-back: a new slot, no close/open
    assert events == [('schedule.slot', {'day': MON, 'open': '12:00', 'close': '14:00', 'volume': None})]
    events.clear()
    clock.now = at(MON, '14:00')
    sched._evaluate()
    assert events == [('schedule.close', None)]
    events.clear()
    clock.now = at(MON, '16:00')
    sched._evaluate()
    assert events == [('schedule.open', None),
                      ('schedule.slot', {'day': MON, 'open': '16:00', 'close': '18:00', 'volume': 50})]


def test_day_span_for_the_clean_slate_reboot(clock):
    # once a day: before the first slot, after the last; a past-midnight end counts for its day
    sched, _ = make(schedule_grid=week(mon=[slot('14:00', '18:00'), slot('10:00', '12:00')],
                                       fri=[slot('10:00', '12:00'), slot('20:00', '01:00')]))
    assert sched.daySpan(MON) == (600, 1080)
    assert sched.daySpan(FRI) == (600, 1500)
    assert sched.daySpan(TUE) is None


def test_next_opening_is_reported(clock):
    sched, _ = make(schedule_grid=week(mon=[slot('10:00', '12:00'), slot('14:00', '18:00')],
                                       wed=[slot('09:00', '10:00')]))
    grid = sched.grid()
    assert sched._nextOpen(grid, at(MON, '13:00')) == '14:00'
    assert sched._nextOpen(grid, at(MON, '19:00')) == 'Wed 09:00'
    assert sched._nextOpen(grid, at(WED, '11:00')) == 'Mon 10:00'
