"""The servo's per-tick correction line is debug on the wallclock (hplayer2#t-066): a chasing
follower printed several lines a second into a journal that lives in RAM on a Pi player, for
numbers the drift CSV and the `drift 60s` summary already carry. The rare lines (JUMP) stay, and
the Nowde servo keeps its per-tick lines: the Pi-tools blackbox counts them (`servo=`)."""

from core.engine.drifter import Drifter
from core.interfaces.wallclock import WallclockInterface


class StubPlayer:
    name = 'player'

    def __init__(self, pos=10.0):
        self._pos = pos

    def position(self):
        self._pos += 0.001               # must move or the tick is dropped
        return self._pos

    def isPaused(self):
        return False

    def isPlaying(self):
        return True

    def resume(self):
        pass

    def speed(self, s):
        pass

    def seekTo(self, ms, exact=False):
        pass

    def status(self, k=None):
        return None


def _drifter(lines, **kw):
    d = Drifter(StubPlayer(10.0), log=lambda *a: lines.append(' '.join(str(x) for x in a)), **kw)
    d.arm()
    d.kickStart = 0                      # past the start grace
    return d


def test_default_servo_logs_every_chasing_tick():
    lines = []
    d = _drifter(lines)
    for _ in range(5):
        d.tick(10.5)                     # 0.5 s late: speed off 1.0 on every tick
    assert sum('timedelay=' in l and 'speed=' in l for l in lines) == 5


def test_tick_lines_off_keeps_the_jump_line():
    lines = []
    d = _drifter(lines)
    d.logTicks = False
    for _ in range(5):
        d.tick(10.5)
    assert lines == []                   # a chase writes nothing
    for _ in range(3):                   # 10 s late: beyond servo reach once the median of 5 moves
        d.tick(20.0)
    assert len(lines) == 1 and 'JUMP' in lines[0]


class HP:
    def __init__(self):
        self.player = StubPlayer()

    def players(self):
        return [self.player]

    def on(self, ev):
        return lambda f: f

    def interface(self, name):
        return None

    def autoBind(self, m):
        pass


def test_wallclock_follower_chase_lines_are_debug():
    wc = WallclockInterface(HP(), None, False, driftLog=None)
    assert wc.drifter is not None and wc.drifter.logTicks is False
    wc = WallclockInterface(HP(), None, False, driftLog=None, logChase=True)
    assert wc.drifter.logTicks is True


def test_elected_follower_chase_lines_are_debug():
    wc = WallclockInterface(HP(), None, role='elected', driftLog=None)
    assert wc.drifter is not None and wc.drifter.logTicks is False
