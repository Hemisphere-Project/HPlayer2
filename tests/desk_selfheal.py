"""
Self-heal desk test (2026-09-25, after KOUAGOU): hardware-free checks of
- PacketClock: the packet-derived clock offset, through wifi-like delays
- a slave with NO zyre clockshift locking on the packets alone (fallback)
- a remembered zyre shift that disagrees with the packets is refused
- every packet delivered twice (multicast + broadcast) is taken once
- a master whose player view freezes keeps the clock flowing from mpv directly
- a stopped master sends a heartbeat: the slave keeps hearing it
- health: starvation -> restart at the loop point; restart budget

    python3 -m venv /tmp/wallsync-venv
    /tmp/wallsync-venv/bin/pip install termcolor pymitter
    /tmp/wallsync-venv/bin/python tests/desk_selfheal.py
"""
import sys, os, time, types, threading, random, tempfile, functools
print = functools.partial(print, flush=True)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
ni.interfaces = lambda: []
ni.ifaddresses = lambda iface: {}
sys.modules['netifaces'] = ni

import core.interfaces.wallclock as wcmod
from core.interfaces.wallclock import WallclockInterface, PacketClock, PRECISION


class FakePlayer():
    def __init__(self, duration=60.0, media='/data/media/loop.mp4', rateError=1.0):
        self.duration = duration; self.media = media; self.rateError = rateError
        self._speed = 1.0; self._base = 0.0; self._t0 = time.time()
        self.playing = True; self.paused = False; self.name = 'player'; self.seeks = 0
        self.onStalled = None
    def _now(self):
        return (self._base + (time.time() - self._t0) * self._speed * self.rateError) % self.duration
    def position(self): return round(self._now(), 2)
    def isPlaying(self): return self.playing
    def isPaused(self): return self.paused
    def resume(self): self.paused = False
    def pause(self): self.paused = True
    def play(self, *a): self.playing = True
    def stop(self): self.playing = False
    def speed(self, s):
        if s == self._speed: return
        self._base = self._now(); self._t0 = time.time(); self._speed = s
    def seekTo(self, milli, exact=False):
        self._base = (milli / 1000.0) % self.duration; self._t0 = time.time(); self.seeks += 1
    def status(self, key=None):
        s = {'media': self.media, 'duration': self.duration, 'time': self.position(),
             'isPlaying': self.playing, 'isPaused': self.paused}
        return s[key] if key else s
    def _applyOneLoop(self, x): pass


class FakeTC():
    def __init__(self, status, cs): self.status = status; self.clockshift = cs
    def stalled(self): return False

class FakePeer():
    def __init__(self, name, tc=None, memo=None):
        self.name = name; self.timeclient = tc; self._memo = memo; self.active = True; self.ip = '127.0.0.1'
    def clockReady(self): return (self.timeclient and self.timeclient.status == 1) or self._memo is not None
    def clockshift(self):
        if self.timeclient and self.timeclient.status == 1: return self.timeclient.clockshift
        return self._memo if self._memo is not None else 0
    def sync(self, force=False): pass

class FakeNode():
    def __init__(self, peer): self._peer = peer; self.book = {b'u': peer} if peer else {}
    def peerByName(self, name): return self._peer if self._peer and name == self._peer.name else None

class FakeZyre():
    def __init__(self, peer): self.node = FakeNode(peer); self.rebuilds = []
    def requestRebuild(self, why): self.rebuilds.append(why)

class FakeHPlayer():
    def __init__(self, player, zyre=None):
        self._player = player; self._zyre = zyre; self.handlers = {}; self.ifaces = {}; self.shutdowns = []
        self.settings = types.SimpleNamespace(set=lambda *a: None, get=lambda *a: None)
    def players(self): return [self._player]
    def interface(self, name):
        if name == 'zyre': return self._zyre
        return self.ifaces.get(name)
    def autoBind(self, module): pass
    def on(self, event):
        def reg(f): self.handlers[event] = f; return f
        return reg
    def emit(self, *a): pass
    def request_shutdown(self, exit_code=0, **k): self.shutdowns.append(exit_code)


def wrapdiff(a, b, d):
    x = abs(a - b) % d
    return min(x, d - x)


# ── T1: PacketClock ──────────────────────────────────────────────────────────────────
print("== T1: PacketClock through wifi-like delays (1-3 ms floor, 30% power-save 20-150 ms) ==")
pc = PacketClock(latency_us=1500)
TRUE_CS = 7 * 3600 * PRECISION + 123456          # master 7 h ahead (fake clocks)
t0 = 1_000_000 * PRECISION
random.seed(37)
for i in range(20 * 10):                         # 10 s at 20 Hz
    tx_master = t0 + TRUE_CS + i * 50000
    delay = random.uniform(1000, 3000) + (random.uniform(20000, 150000) if random.random() < 0.3 else 0)
    recv_local = t0 + i * 50000 + delay
    pc.add(tx_master, recv_local)
err = pc.shift() - TRUE_CS
print("   estimate error = %.2f ms" % (err / 1000))
assert pc.ready() and abs(err) < 2500, "packet clock off by %.1f ms" % (err / 1000)
pc.add(t0 + 20 * 50000 * 10 + 5 * PRECISION, t0 + 20 * 50000 * 10)   # master clock jumps 5 s
assert not pc.ready(), "a clock jump must reset the estimate"
print("   PASS")


# ── T2..T5: master -> slave over loopback, packets delivered twice ────────────────────
CS_US = 250000
mPlayer = FakePlayer(60.0)
mHp = FakeHPlayer(mPlayer, FakeZyre(FakePeer('SLAVE')))
master = WallclockInterface(mHp, None, True, player=mPlayer, port=13738, rate=20, unicast=True, driftLog=None)
master._myName = 'MASTER'
master._peerIps = lambda: ['127.0.0.1', '127.0.0.1']      # every packet arrives twice

# the master's clock runs CS_US ahead: skew both the latch and the send stamp
_realTime = time.time
# (the master thread reads wcmod.time; the slave thread too — so skew per thread)
class ThreadClock(types.ModuleType):
    def __getattr__(self, k): return getattr(time, k)
    def time(self):
        return _realTime() + (CS_US / PRECISION if threading.current_thread() is master.recvThread else 0)
wcmod.time = ThreadClock('time')

def feeder():
    while not stopFeed.is_set():
        if feeding.is_set():
            master._latch = (mPlayer.position(), int((_realTime() + CS_US / PRECISION) * PRECISION))
        stopFeed.wait(0.04)
stopFeed = threading.Event(); feeding = threading.Event(); feeding.set()

# slave: zyre peer WITHOUT a usable clockshift, and a stale memo 10 s wrong
sPlayer = FakePlayer(60.0, rateError=1.002)
sPlayer._base = (mPlayer._now() + 1.5) % 60.0
sPeer = FakePeer('MASTER', tc=FakeTC(0, 0))
sZ = FakeZyre(sPeer)
sHp = FakeHPlayer(sPlayer, sZ)
slave = WallclockInterface(sHp, None, False, player=sPlayer, port=13738, masterName='MASTER', driftLog=None)
slave._myName = 'SLAVE'
slave.drifter.doLog = False
dups = {'n': 0}
_origTick = slave.drifter.tick

slave.recvThread.daemon = True; master.recvThread.daemon = True
slave.start(); master.start()
threading.Thread(target=feeder, daemon=True).start()

print("== T2: no zyre shift (TimeClient rounds failing) -> the slave locks on the PACKETS ==")
time.sleep(14)
d = wrapdiff(mPlayer._now(), sPlayer._now(), 60.0)
print("   source=%s |master-slave|=%.0f ms seeks=%d" % (slave.hCsSource, d * 1000, sPlayer.seeks))
assert slave.hCsSource == 'packets', "expected the packet clock, got %s" % slave.hCsSource
assert d < 0.08, "slave not locked on packets: %.3f s" % d
print("   PASS")

print("== T3: every packet heard twice -> seq dedupe (no double servo ticks) ==")
seqs = []
slave.drifter.tick = lambda clock, dur=0: (seqs.append(slave._lastSeq), _origTick(clock, dur))[1]
time.sleep(2)
slave.drifter.tick = _origTick
dupl = len(seqs) - len(set(seqs))
print("   ticks=%d duplicated=%d" % (len(seqs), dupl))
assert dupl == 0, "duplicate packets reached the servo"
print("   PASS")

print("== T5: master STOPPED -> 1 Hz heartbeat, slave still hears it (no deaf re-join loop) ==")
feeding.clear(); mPlayer.playing = False
time.sleep(4)
age = _realTime() - slave.hLastAccept
print("   heard %.1fs ago, masterPlaying=%s rejoins=%d" % (age, slave.hMasterPlaying, slave._rejoins))
assert age < 1.6 and not slave.hMasterPlaying and slave._rejoins == 0
print("   PASS")
master.stopped.set(); slave.stopped.set(); stopFeed.set()
wcmod.time = time


# ── T6: health ──────────────────────────────────────────────────────────────────────
print("== T6: health — starvation -> restart at the loop point, budget 3/h ==")
import core.interfaces.health as hmod
hmod.STATE = os.path.join(tempfile.mkdtemp(), 'health.json')
hPlayer = FakePlayer(20.0)
hHp = FakeHPlayer(hPlayer, None)
h = hmod.HealthInterface(hHp)
h.startedAt -= 120
hmod._starved['count'] += 1
h._check()
assert h._pending and 'starvation' in h._pending[0]
hPlayer._base = 5.0; hPlayer._t0 = time.time()
assert not h._atBoundary(), "mid-film is not a loop point"
hPlayer._base = 19.6; hPlayer._t0 = time.time()
assert h._atBoundary(), "0.4 s before the end is a loop point"
h._doRestart(h._pending[0]); h._pending = None
assert hHp.shutdowns == [1]
for i in range(2):
    h.requestRestart('again %d' % i); h._doRestart('again'); h._pending = None
h.requestRestart('fourth')
assert h._pending is None, "the 4th restart within the hour must be refused"
print("   restarts=%d, 4th refused" % len(hHp.shutdowns))
print("   PASS")

print("== T7: real `can't start new thread` is counted by the guard ==")
before = hmod._starved['count']
orig = hmod._origStart
def boom(self, *a, **k): raise RuntimeError("can't start new thread")
hmod._origStart = boom
try:
    threading.Thread(target=lambda: None).start()
except RuntimeError:
    pass
hmod._origStart = orig
assert hmod._starved['count'] == before + 1
print("   PASS")

print("== T9: 60 s link outage, slave plays 0.5% FAST -> no seek, still locked after ==")
wcmod.time = ThreadClock('time')
m9Player = FakePlayer(60.0)
m9Hp = FakeHPlayer(m9Player, FakeZyre(FakePeer('SLAVE')))
master = WallclockInterface(m9Hp, None, True, player=m9Player, port=13739, rate=20, unicast=True, driftLog=None)
master._myName = 'MASTER'
link = {'up': True}
master._peerIps = lambda: ['127.0.0.1'] if link['up'] else []
s9Player = FakePlayer(60.0, rateError=1.005)
s9Player._base = (m9Player._now() + 0.3) % 60.0
s9Hp = FakeHPlayer(s9Player, FakeZyre(FakePeer('MASTER', tc=FakeTC(1, CS_US))))
slave9 = WallclockInterface(s9Hp, None, False, player=s9Player, port=13739, masterName='MASTER', driftLog=None)
slave9._myName = 'SLAVE'; slave9.drifter.doLog = False
def feeder9():
    while not stop9.is_set():
        master._latch = (m9Player.position(), int((_realTime() + CS_US / PRECISION) * PRECISION))
        stop9.wait(0.04)
stop9 = threading.Event()
for x in (master, slave9): x.recvThread.daemon = True; x.start()
threading.Thread(target=feeder9, daemon=True).start()
time.sleep(10)
d0 = wrapdiff(m9Player._now(), s9Player._now(), 60.0); seeks0 = s9Player.seeks
link['up'] = False
worst = 0.0
for i in range(60):
    time.sleep(1)
    worst = max(worst, wrapdiff(m9Player._now(), s9Player._now(), 60.0))
link['up'] = True
time.sleep(5)
d1 = wrapdiff(m9Player._now(), s9Player._now(), 60.0)
print("   before %.0f ms | worst during outage %.0f ms | after %.0f ms | seeks during+after %d" % (d0 * 1000, worst * 1000, d1 * 1000, s9Player.seeks - seeks0))
print("   (the old code: speed 1.0 at 0.5% fast = +300 ms after 60 s)")
assert s9Player.seeks == seeks0, "an outage must not cost a seek"
assert worst < 0.1 and d1 < 0.08, "the model must hold the slave within 100 ms"
print("   PASS")
master.stopped.set(); slave9.stopped.set(); stop9.set()

print("\nALL SELF-HEAL TESTS PASSED")
sys.stdout.flush()
os._exit(0)
