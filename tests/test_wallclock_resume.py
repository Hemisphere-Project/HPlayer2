"""A fixed master restarted by health resumes on its timeline, not at 0 (hplayer2#t-079).

KOUAGOU 30/09: the master's loop-point restart played again from 0 ~25 s later while the slaves
chased their model of it, and they jumped back ~28 s when its clock returned. health now keeps
the wall time of the timeline's position 0 in /run; the next process seeks its first play there
and sends no clock (not even a stopped beat) until it has landed.
"""

import json
import time

from core.interfaces import wallclock
from core.interfaces.wallclock import WallclockInterface, PRECISION, LONG_AGO
from core.interfaces.health import HealthInterface

FILM = '/data/media/film.mp4'


class FakePlayer:
    name = 'player'

    def __init__(self, media=FILM, dur=120.0, playing=True):
        self.media, self.dur, self.playing = media, dur, playing
        self.seeks = []
        self.paused = False

    def isPlaying(self):
        return self.playing

    def isPaused(self):
        return self.paused

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seekTo(self, ms, exact=False):
        self.seeks.append((ms, exact))

    def status(self, k=None):
        return {'media': self.media, 'duration': self.dur}.get(k)


class Clock:
    def __init__(self, wall=1_800_000_000.0, mono=5000.0):
        self.wall, self.mono = wall, mono

    def step(self, s):
        self.wall += s
        self.mono += s


def _master(player, logs=None):
    w = WallclockInterface.__new__(WallclockInterface)
    w.master, w.elected, w.seamless = True, False, True
    w.player = player
    w.durTolerance = 1.0
    w._latch, w._posHold = None, 0
    w._resume, w._resumeUntil, w._resumeSeek = None, LONG_AGO, None
    w.log = (lambda *a: logs.append(' '.join(str(x) for x in a))) if logs is not None else (lambda *a: None)
    return w


def _clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(time, 'time', lambda: c.wall)
    monkeypatch.setattr(time, 'monotonic', lambda: c.mono)
    return c


def _latch(w, c, pos):
    w._latch = (pos, int(c.wall * PRECISION), c.mono)


def test_round_trip_keeps_the_timeline(monkeypatch, tmp_path):
    monkeypatch.setattr(wallclock, 'RESUME', str(tmp_path / 'resume.json'))
    c = _clock(monkeypatch)
    old = _master(FakePlayer())
    _latch(old, c, 119.6)                       # health restarts at the loop point
    rec = old.saveResume()
    assert rec['m'] == 'film.mp4' and rec['dur'] == 120.0
    assert abs(rec['t0'] - (c.wall - 119.6)) < 1e-6

    c.step(25.0)                                # the new process starts
    new = _master(FakePlayer(playing=False))
    new._loadResume()
    assert new._resume == rec and new.resuming()
    assert not (tmp_path / 'resume.json').exists(), "one restart, one resume"


def test_frozen_player_view_falls_back_to_mpvs_own_reading(monkeypatch, tmp_path):
    monkeypatch.setattr(wallclock, 'RESUME', str(tmp_path / 'resume.json'))
    c = _clock(monkeypatch)
    w = _master(FakePlayer(media=None, dur=None))
    rec = w.saveResume({'time-pos': 40.0, 'duration': 120.0, 'path': FILM, 'wall': c.wall})
    assert rec['m'] == 'film.mp4' and abs(rec['t0'] - (c.wall - 40.0)) < 1e-6


def test_nothing_kept_off_a_seamless_fixed_master(monkeypatch, tmp_path):
    monkeypatch.setattr(wallclock, 'RESUME', str(tmp_path / 'resume.json'))
    c = _clock(monkeypatch)
    w = _master(FakePlayer())
    _latch(w, c, 10.0)
    w.seamless = False                          # a cue list moves on to another file
    assert w.saveResume() is None
    w.seamless, w.elected = True, True          # an elected leader is no leader after a restart
    assert w.saveResume() is None
    assert not (tmp_path / 'resume.json').exists()


def test_stale_record_is_ignored_and_removed(monkeypatch, tmp_path):
    path = tmp_path / 'resume.json'
    monkeypatch.setattr(wallclock, 'RESUME', str(path))
    c = _clock(monkeypatch)
    path.write_text(json.dumps({'t0': c.wall - 50, 'm': 'film.mp4', 'dur': 120.0,
                                'at': c.wall - wallclock.RESUME_MAX_AGE - 1}))
    w = _master(FakePlayer())
    w._loadResume()
    assert w._resume is None and not w.resuming() and not path.exists()


def _resumed(monkeypatch, player, t0_ago=50.0):
    c = _clock(monkeypatch)
    w = _master(player, logs=[])
    w._resume = {'t0': c.wall - t0_ago, 'm': 'film.mp4', 'dur': 120.0, 'at': c.wall - 25}
    w._resumeUntil = c.mono + wallclock.RESUME_WINDOW
    return w, c


def test_prerolls_to_the_timeline_and_holds_the_clock_until_it_runs_there(monkeypatch):
    p = FakePlayer(playing=False)
    w, c = _resumed(monkeypatch, p)
    assert w._resumeGate() is False, "booting: not even a stopped beat (it releases the slaves)"
    p.playing = True
    _latch(w, c, 0.3)                           # the boot play starts the file at 0
    assert w._resumeGate() is False
    assert p.paused, "paused: the film decodes its keyframe off the timeline"
    (ms, exact), = p.seeks
    pre = wallclock.RESUME_PREROLL
    assert exact and abs(ms - (50 + pre) * 1000) < 1, "where the timeline will be at the start"
    c.step(1.0)
    _latch(w, c, 50 + pre)                      # decoded, sitting on the target frame
    assert w._resumeGate() is False and p.paused
    c.step(pre - 1.0)                           # the timeline reaches the target: start
    assert w._resumeGate() is False and not p.paused
    c.step(0.05)
    _latch(w, c, 50 + pre + 0.05)               # reading the target is not running on it...
    assert w._resumeGate() is False
    c.step(0.35)
    _latch(w, c, 50 + pre + 0.40)               # ...moving with the wall clock, on the timeline: landed
    assert w._resumeGate() is True
    assert w.resuming(), "the profile's other boot plays stay local a while"
    assert len(p.seeks) == 1


def test_a_decode_that_outruns_the_preroll_prerolls_again_with_twice_the_margin(monkeypatch):
    # rig 20/11 (bench-01, RastaOS-7.5, 1080p 0_mire.mp4): an exact seek decoded 1.8 s, the next
    # 4.1 s - a seek-and-go (the first fix) sent the clock off mpv's first reading and the master
    # ran 2 s behind its slave (-1906 ms). A pre-roll whose decode outran it starts late: again,
    # with twice the margin.
    p = FakePlayer()
    w, c = _resumed(monkeypatch, p)
    logs = []
    w.log = lambda *a: logs.append(' '.join(str(x) for x in a))
    pre = wallclock.RESUME_PREROLL
    _latch(w, c, 0.3)
    assert w._resumeGate() is False             # pre-roll 1: paused at 50 + pre
    c.step(pre)
    assert w._resumeGate() is False and not p.paused     # started - but still decoding
    c.step(0.05)
    _latch(w, c, 50 + pre)
    assert w._resumeGate() is False
    c.step(1.0)
    _latch(w, c, 50 + pre + 0.02)               # frozen a second, moving now
    assert w._resumeGate() is False
    c.step(0.4)
    _latch(w, c, 50 + pre + 0.42)               # running 1.03 s behind (timeline 50 + pre + 1.45)
    assert w._resumeGate() is False, "1 s behind is no landing"
    assert p.paused and len(p.seeks) == 2
    ms, exact = p.seeks[1]
    assert exact and abs(ms - (50 + pre + 1.45 + 2 * pre) * 1000) < 1, "twice the margin"
    c.step(2 * pre)
    assert w._resumeGate() is False and not p.paused
    c.step(0.05)
    _latch(w, c, 50 + 3 * pre + 1.50)
    assert w._resumeGate() is False
    c.step(0.35)
    _latch(w, c, 50 + 3 * pre + 1.85)           # on the timeline
    assert w._resumeGate() is True
    assert len(p.seeks) == 2
    assert any('pre-roll again' in l for l in logs) and any('running' in l and 'clock out' in l for l in logs)


def test_still_off_after_the_last_preroll_lets_the_clock_out(monkeypatch):
    p = FakePlayer()
    w, c = _resumed(monkeypatch, p)
    w._resumeSeek = {'phase': 'running', 'target': 50.0, 'start': c.wall, 'margin': 24.0,
                     'n': wallclock.RESUME_PREROLLS, 'anchor': None, 'runAt': c.mono}
    c.step(0.05)
    _latch(w, c, 49.6)
    assert w._resumeGate() is False
    c.step(0.4)
    _latch(w, c, 50.0)                          # running, 0.45 s behind, no pre-roll left
    assert w._resumeGate() is True
    assert not p.seeks and not p.paused, "the slaves' drifter trims the rest"


def test_landing_unconfirmed_still_lets_the_clock_out(monkeypatch):
    p = FakePlayer()
    w, c = _resumed(monkeypatch, p)
    _latch(w, c, 0.3)
    assert w._resumeGate() is False
    c.step(wallclock.RESUME_PREROLL)
    assert w._resumeGate() is False and not p.paused    # started; no position ever comes back
    c.step(wallclock.RESUME_HOLD + 0.1)
    assert w._resumeGate() is True


def test_another_file_forgets_the_record(monkeypatch):
    w, c = _resumed(monkeypatch, FakePlayer(media='/data/media/other.mp4'))
    _latch(w, c, 0.3)
    assert w._resumeGate() is True and w._resume is None and not w.resuming()


def test_timeline_at_its_loop_point_needs_no_seek(monkeypatch):
    p = FakePlayer()
    w, c = _resumed(monkeypatch, p, t0_ago=120.4)   # the timeline wrapped 0.4 s ago
    _latch(w, c, 0.3)
    assert w._resumeGate() is True and not p.seeks


def test_window_passes_without_a_play(monkeypatch):
    w, c = _resumed(monkeypatch, FakePlayer(playing=False))
    c.step(wallclock.RESUME_WINDOW + 1)
    assert w._resumeGate() is True and w._resume is None


def test_send_loop_reads_the_gate():
    import inspect
    src = inspect.getsource(WallclockInterface._runMaster)
    assert 'elif self._resume is not None and not self._resumeGate():' in src


def test_health_restart_writes_the_record(monkeypatch, tmp_path):
    monkeypatch.setattr(wallclock, 'RESUME', str(tmp_path / 'resume.json'))
    c = _clock(monkeypatch)
    p = FakePlayer()
    w = _master(p)
    _latch(w, c, 119.5)

    class Hp:
        def interface(self, name):
            return w if name == 'wallclock' else None

        def players(self):
            return [p]

    h = HealthInterface.__new__(HealthInterface)
    h.hplayer = Hp()
    h.log = lambda *a: None
    h._saveResume()
    rec = json.loads((tmp_path / 'resume.json').read_text())
    assert rec['m'] == 'film.mp4' and abs(rec['t0'] - (c.wall - 119.5)) < 1e-3
