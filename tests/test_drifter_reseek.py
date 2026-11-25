"""A seek on the Nowde master is a STEP of the slaves' clock, not drift: one exact seek, never a chase.

Biennale 15/09 (module-radar log): one click on W3's http2 timeline and every slave's servo saw
deltas up to 92 s and hunted -- a JUMP every ~16 s, the speed swinging -- until the players were
power-cycled; Stop/Play re-locked in seconds. The servo had one rule for every gap: a late one up to
`seekLateThreshold` (10 s on Nowde) chased at up to 2x, a bigger one met a KEYFRAME seek that lands
on the GOP grid, up to a GOP early, which is a late gap again (hplayer2#t-062).

The desk: an mpv-like player in simulated time -- a keyframe seek snaps to the GOP grid, an exact
seek freezes the picture for its decode cost then lands on its target, speed saturates at 2x (mmal,
bench 2026-07-23) -- fed by a master clock at the MTC cadence. What the bench check counts on
player-000 (drag the timeline, count jumps) is counted here: seeks per master seek."""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.engine.drifter as drifter_mod           # noqa: E402
from core.engine.drifter import Drifter             # noqa: E402

TICK = 0.08          # s: one MTC position every 2 frames at 25 fps (the 8th quarter-frame)


class Sim:
    """Simulated time, shared by the clock source, the player and the servo's time.monotonic()."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


class SimPlayer:
    """mpv as the servo meets it. Exact seek: time-pos frozen for `exactCost` s, then the target.
    Keyframe seek: the GOP grid at or before the target, at once. Speed: capped at 2x."""

    def __init__(self, pos=0.0, duration=600.0, gop=16.0, exactCost=0.3):
        self.name = 'player'
        self.pos, self.duration, self.gop, self.exactCost = pos, duration, gop, exactCost
        self.rate, self.frozen, self.landAt = 1.0, 0.0, None
        self.seeks = []                  # (sim time, target, 'exact'|'keyframes')
        self.rates = []

    def position(self):
        return round(self.pos, 3)

    def isPlaying(self):
        return True

    def isPaused(self):
        return False

    def resume(self):
        pass

    def status(self, entry=None):
        st = {'isPlaying': True, 'isPaused': False, 'media': '03_garden.mp4',
              'time': self.pos, 'duration': self.duration}
        return st[entry] if entry else st

    def speed(self, s):
        self.rate = s
        self.rates.append(s)

    def seekTo(self, ms, exact=False):
        target = (ms / 1000.0) % self.duration
        self.seeks.append((self.sim.t, target, 'exact' if exact else 'keyframes'))
        if exact:
            self.frozen, self.landAt = self.exactCost, target
        else:
            self.pos = (target // self.gop) * self.gop

    def advance(self, dt):
        if self.frozen > 0:
            self.frozen -= dt
            if self.frozen <= 0:
                self.pos, self.landAt = self.landAt, None
            return
        self.pos = (self.pos + dt * min(self.rate, 2.0)) % self.duration


class Desk:
    """Master clock + slave player + servo, stepped together in simulated time."""

    def __init__(self, monkeypatch, reseek=2.0, start=100.0, **player):
        self.sim = Sim()
        monkeypatch.setattr(drifter_mod, 'time', types.SimpleNamespace(monotonic=self.sim.monotonic))
        self.player = SimPlayer(pos=start, **player)
        self.player.sim = self.sim
        self.lines = []
        self.drifter = Drifter(self.player, log=lambda *a: self.lines.append(' '.join(str(x) for x in a)),
                               jumpFix=200, seekLateThreshold=10, reseekThreshold=reseek)   # Nowde's
        self.drifter.arm()
        self.drifter.kickStart = 0
        self.clock = start

    def run(self, seconds, feed=None):
        for _ in range(int(round(seconds / TICK))):
            self.sim.t += TICK
            self.clock = (self.clock + TICK) % self.player.duration
            self.player.advance(TICK)
            self.drifter.tick(feed(self.clock) if feed else self.clock, self.player.duration)

    def gap(self):
        d = self.clock - self.player.pos
        return ((d + self.player.duration / 2) % self.player.duration) - self.player.duration / 2

    def master_seek(self, by):
        self.clock = (self.clock + by) % self.player.duration

    def locked_after(self, seconds, within=0.1):
        """Sim seconds until the gap stays within `within` for 1 s straight, or None."""
        held, t0 = 0.0, self.sim.t
        for _ in range(int(round(seconds / TICK))):
            self.run(TICK)
            held = held + TICK if abs(self.gap()) < within else 0.0
            if held >= 1.0:
                return round(self.sim.t - t0 - 1.0, 2)
        return None


def settle(desk):
    desk.run(5)
    assert abs(desk.gap()) < 0.1 and not desk.player.seeks


# ---- the rule

def test_master_seek_forward_inside_the_old_chase_range_is_one_exact_seek(monkeypatch):
    desk = Desk(monkeypatch)
    settle(desk)
    rates = len(desk.player.rates)
    desk.master_seek(+8.0)
    t = desk.locked_after(10)
    assert [s[2] for s in desk.player.seeks] == ['exact']
    assert t is not None and t < 2.0
    assert max(desk.player.rates[rates:]) < 1.2          # never a chase
    assert any('clock stepped +8.00s' in l for l in desk.lines)


def test_master_seek_backward_is_one_exact_seek(monkeypatch):
    desk = Desk(monkeypatch, start=300.0)
    settle(desk)
    desk.master_seek(-92.0)                             # the biggest delta read on 15/09
    t = desk.locked_after(10)
    assert [s[2] for s in desk.player.seeks] == ['exact']
    assert t is not None and t < 2.0


def test_a_slow_exact_seek_lands_late_and_is_chased_then_the_next_step_aims_right(monkeypatch):
    """mmal on single-keyframe content: an exact seek costs ~4 s, so it lands ~3.7 s late. A second
    seek would cost another 4 s to save that: the servo chases it. The cost is learned, and the
    next master seek lands inside the servo's range at once."""
    def chased(since):                                  # s spent at 1.5x or more
        return sum(1 for r in desk.player.rates[since:] if r >= 1.5) * TICK

    desk = Desk(monkeypatch, exactCost=4.0)
    settle(desk)
    rates = len(desk.player.rates)
    desk.master_seek(+40.0)
    t = desk.locked_after(30)
    assert [s[2] for s in desk.player.seeks] == ['exact']
    assert t is not None and t < 12.0                   # the 4 s freeze included (desk: 10.6)
    assert chased(rates) <= 4.0                         # the landing gap, once (old rule: 9 s)
    assert desk.drifter._seekLatEst > 2.5
    rates, seeks = len(desk.player.rates), len(desk.player.seeks)
    desk.master_seek(-60.0)
    t = desk.locked_after(30)
    assert [s[2] for s in desk.player.seeks[seeks:]] == ['exact']
    assert t is not None and t < 9.0                    # desk: 7.9
    assert chased(rates) <= 1.5


def test_an_exact_seek_landing_ahead_gets_one_aimed_retry(monkeypatch):
    """A latency learned on slow content, then a fast seek: the landing is AHEAD beyond the
    threshold -- slowing down at 0.2x would crawl for seconds. One more exact seek, aimed with the
    latency the landing measured; never the keyframe seek of the old rule."""
    desk = Desk(monkeypatch)
    settle(desk)
    desk.drifter._seekLatEst = 3.0
    desk.master_seek(+20.0)
    t = desk.locked_after(10)
    assert [s[2] for s in desk.player.seeks] == ['exact', 'exact']
    assert t is not None and t < 5.0                    # desk: 4.0, the servo trims the 2nd landing


def test_one_garbled_reading_is_not_a_seek(monkeypatch):
    """A quarter-frame assembly straddling a jump can decode to any time: one reading is no step."""
    desk = Desk(monkeypatch)
    settle(desk)
    n = [0]

    def feed(clock):
        n[0] += 1
        return clock + 40.0 if n[0] == 3 else clock
    desk.run(5, feed=feed)
    assert desk.player.seeks == []
    assert abs(desk.gap()) < 0.1


def test_the_master_loop_point_is_not_a_step(monkeypatch):
    desk = Desk(monkeypatch, start=25.0, duration=30.0)
    settle(desk)
    desk.run(20)                                        # wraps 30 -> 0 at least once, both sides
    assert desk.player.seeks == []
    assert not any('clock stepped' in l for l in desk.lines)
    assert abs(desk.gap()) < 0.1


def test_drift_is_still_the_servos(monkeypatch):
    """Only the CLOCK stepping is a seek. A player that falls behind on its own is drift: chased,
    as before (here a 1.5 s stall of the player, the clock running on)."""
    desk = Desk(monkeypatch)
    settle(desk)
    desk.player.frozen, desk.player.landAt = 1.5, desk.player.pos
    t = desk.locked_after(10)
    assert desk.player.seeks == [] and t is not None
    assert max(desk.player.rates) > 1.2                 # chased
    assert not any('clock stepped' in l for l in desk.lines)


# ---- what it replaces

def test_the_bug_it_fixes(monkeypatch):
    """reseek off = the servo of 15/09: the same +8 s master seek is chased at 2x, no seek; and a
    -92 s one meets a keyframe seek that lands up to a GOP early, then chases or JUMPs again."""
    desk = Desk(monkeypatch, reseek=None)
    settle(desk)
    desk.master_seek(+8.0)
    desk.run(2)
    assert desk.player.seeks == [] and max(desk.player.rates) >= 2.0

    desk = Desk(monkeypatch, reseek=None, start=300.0)
    settle(desk)
    desk.master_seek(-92.0)
    desk.run(20)
    assert desk.player.seeks and all(s[2] == 'keyframes' for s in desk.player.seeks)
    assert max(desk.player.rates) >= 2.0                # landed early: the chase is back


# ---- the Nowde slave wires it

pytest.importorskip("mido")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2            # noqa: E402
from core.interfaces.nowde import NowdeInterface    # noqa: E402


class FakePlaylist:
    def __init__(self, player):
        self.player, self.plays = player, []

    def play(self, pattern=None, index=-1, pause=False):
        self.plays.append(pattern)
        self.player.pos = 0.0

    def size(self):
        return 1


@pytest.fixture
def slave(monkeypatch):
    sim = Sim()
    monkeypatch.setattr(drifter_mod, 'time', types.SimpleNamespace(monotonic=sim.monotonic))
    hplayer = HPlayer2(mediaPath=[])
    player = SimPlayer(pos=0.0)
    player.sim = sim
    hplayer._players['player'] = player
    hplayer.playlist = FakePlaylist(player)
    i = NowdeInterface(hplayer, player, mode='slave')
    lines = []
    monkeypatch.setattr(i, 'log', lambda *a: lines.append(' '.join(str(x) for x in a)))
    i.drifter.log = lambda *a: lines.append(' '.join(str(x) for x in a))
    i.sim, i.fp, i.lines, i.clock = sim, player, lines, 0.0
    return i


def mtc(i, seconds):
    for _ in range(int(round(seconds / TICK))):
        i.sim.t += TICK
        i.clock += TICK
        i.fp.advance(TICK)
        i.handle_timecode('nowde.qf', types.SimpleNamespace(float=i.clock))


def test_nowde_slave_reseeks_a_master_seek(slave):
    assert slave.drifter.reseekThreshold == 2.0
    slave.handle_media_selection(3)
    mtc(slave, 30)
    assert abs(slave.clock - slave.fp.pos) < 0.1 and slave.fp.seeks == []
    slave.clock += 8.0                                  # the master's timeline, clicked
    slave.handle_timecode('nowde.ff', types.SimpleNamespace(float=slave.clock))   # the node's jump full-frame
    mtc(slave, 3)
    assert [s[2] for s in slave.fp.seeks] == ['exact']
    assert abs(slave.clock - slave.fp.pos) < 0.1
    assert max(slave.fp.rates) < 1.2


def test_nowde_reseek_zero_is_the_old_chase(slave, monkeypatch):
    cfg = slave._cfg
    monkeypatch.setattr(slave, '_cfg', lambda k: 0 if k == 'nowde-reseek' else cfg(k))
    slave.handle_media_selection(3)                     # live tunables apply at every media start
    assert slave.drifter.reseekThreshold is None
    mtc(slave, 30)
    slave.clock += 8.0
    mtc(slave, 2)
    assert slave.fp.seeks == [] and max(slave.fp.rates) >= 2.0
