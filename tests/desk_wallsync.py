"""
Wall-sync desk test: hardware-free validation of the wallclock continuous
sync (core/engine/drifter.py + core/interfaces/wallclock.py).

- Drifter servo simulation: convergence, loop-wrap without seek, hard-seek
  recovery (tests 1-3, fake player only).
- Full master->slave path over loopback UDP (unicast mode), with a fake
  zyre node providing a simulated clockshift (test 4).

No fleet, no mpv, no zyre/czmq needed. netifaces (C-ext) is stubbed.
Only termcolor + pymitter are required:

    python3 -m venv /tmp/wallsync-venv
    /tmp/wallsync-venv/bin/pip install termcolor pymitter
    /tmp/wallsync-venv/bin/python tests/desk_wallsync.py

Takes ~90s (real-time sleeps: the servo is exercised at its real cadence).
"""
import sys, os, time, types, threading, socket, json, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# --- stub netifaces (C-ext, not needed for the test) ------------------------
ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
ni.interfaces = lambda: []
ni.ifaddresses = lambda iface: {}
sys.modules['netifaces'] = ni

from core.engine.drifter import Drifter


# --- fake player -------------------------------------------------------------
class FakePlayer():
    """position advances with real time * speed, wraps at duration, 0.01s quantized"""
    def __init__(self, duration=60.0, media='/data/media/loop.mp4', rateError=1.0):
        self.duration = duration
        self.media = media
        self.rateError = rateError   # simulated crystal error (1.005 = 0.5% fast)
        self._speed = 1.0
        self._base = 0.0
        self._t0 = time.time()
        self.playing = True
        self.paused = False
        self.name = 'player'
        self.seeks = 0
        self.speedLog = []

    def _now(self):
        cur = self._base + (time.time() - self._t0) * self._speed * self.rateError
        return cur % self.duration

    def position(self): return round(self._now(), 2)
    def isPlaying(self): return self.playing
    def isPaused(self): return self.paused
    def resume(self): self.paused = False

    def speed(self, s):
        if s == self._speed: return
        self._base = self._now(); self._t0 = time.time()
        self._speed = s
        self.speedLog.append(s)

    def seekTo(self, milli):
        self._base = (milli / 1000.0) % self.duration; self._t0 = time.time()
        self.seeks += 1

    def status(self, key=None):
        if key == 'media': return self.media
        if key == 'duration': return self.duration
        return None


# --- TEST 1: Drifter convergence ----------------------------------------------
print("== TEST 1: drifter converges from 0.3s offset with 0.05% crystal error ==")
p = FakePlayer(duration=600.0, rateError=1.0005)
c = Drifter(p); c.doLog = False
c.arm()
t0 = time.time(); clock0 = p.position() + 0.3   # master 0.3s ahead
lastDiffs = []
for i in range(20 * 30):                        # 30s at 20Hz
    clock = (clock0 + (time.time() - t0)) % 600.0
    r = c.tick(clock, 600.0)
    if r and i > 20 * 25: lastDiffs.append(abs(r['diff']))
    time.sleep(0.05)
maxLast = max(lastDiffs) if lastDiffs else 99
print("   seeks=%d  max|diff| last 5s = %.0f ms" % (p.seeks, maxLast * 1000))
assert p.seeks == 0, "should converge without seeking"
# hysteresis rides the dead zone up to its 80ms exit bound; allow one tick beyond
assert maxLast < 0.1, "should hold within dead-zone bounds, got %.3f" % maxLast
print("   PASS")

# --- TEST 2: loop wrap produces no seek --------------------------------------
print("== TEST 2: loop wrap (10s media) crosses without seek ==")
p = FakePlayer(duration=10.0, rateError=1.0)
c = Drifter(p); c.doLog = False
c.arm()
t0 = time.time(); clock0 = p.position()
jumps = 0
for i in range(20 * 25):                        # 25s = 2+ wraps
    clock = (clock0 + (time.time() - t0)) % 10.0
    r = c.tick(clock, 10.0)
    if r and r['jumped']: jumps += 1
    time.sleep(0.05)
print("   seeks=%d jumps=%d" % (p.seeks, jumps))
assert p.seeks == 0 and jumps == 0, "wrap must not trigger seeks"
print("   PASS")

# --- TEST 3: big desync triggers one seek then relock ------------------------
print("== TEST 3: 5s desync -> single seek -> relock ==")
p = FakePlayer(duration=600.0, rateError=1.0)
c = Drifter(p); c.doLog = False
c.arm()
t0 = time.time(); clock0 = p.position() + 5.0
for i in range(20 * 8):
    clock = (clock0 + (time.time() - t0)) % 600.0
    r = c.tick(clock, 600.0)
    time.sleep(0.05)
final = abs((clock0 + (time.time() - t0)) % 600.0 - p._now())
print("   seeks=%d final diff=%.0f ms" % (p.seeks, final * 1000))
assert p.seeks == 1, "expected exactly one hard seek, got %d" % p.seeks
assert final < 0.6, "should be near lock after jumpFix compensation, got %.3f" % final
print("   PASS")


# --- fakes for the wallclock interface ---------------------------------------
class FakeTimeClient():
    def __init__(self, cs): self.status = 1; self.clockshift = cs

class FakePeer():
    def __init__(self, name, cs_us):
        self.name = name; self.active = True; self.ip = '127.0.0.1'
        self.timeclient = FakeTimeClient(cs_us)
        self._cs = cs_us
    def clockshift(self): return self._cs

class FakeNode():
    def __init__(self, peer): self._peer = peer; self.book = {b'uuid': peer}
    def peerByName(self, name): return self._peer if name == self._peer.name else None

class FakeZyre():
    def __init__(self, peer): self.node = FakeNode(peer)

class FakeHPlayer():
    """minimal hplayer surface for BaseInterface + WallclockInterface"""
    def __init__(self, player, zyre):
        self._player = player; self._zyre = zyre; self.handlers = {}
    def players(self): return [self._player]
    def interface(self, name): return self._zyre if name == 'zyre' else None
    def autoBind(self, module): pass
    def on(self, event):
        def reg(f): self.handlers[event] = f; return f
        return reg
    def emit(self, *args): pass

from core.interfaces.wallclock import WallclockInterface, PRECISION

# --- TEST 4: end-to-end master -> slave over loopback ------------------------
print("== TEST 4: wallclock master->slave over loopback (unicast), simulated clockshift ==")
CS_US = 250000          # master clock is 250ms ahead of slave clock
driftCsv = os.path.join(tempfile.gettempdir(), 'wallsync-drift-test.csv')
if os.path.isfile(driftCsv): os.remove(driftCsv)

# master: fake player + fake zyre book pointing to 127.0.0.1
mPlayer = FakePlayer(duration=60.0, rateError=1.0)
mPeer = FakePeer('WALL-SLAVE', 0)
mHp = FakeHPlayer(mPlayer, FakeZyre(mPeer))
master = WallclockInterface(mHp, None, True, player=mPlayer, port=13737, rate=20,
                            unicast=True, driftLog=None)
master._myName = 'WALL-MASTER'
master._peerIps = lambda: ['127.0.0.1']   # real zyre book excludes self/loopback; force it for the test

# slave: its own fake player (starts 1.5s off), fake zyre resolving the master peer
sPlayer = FakePlayer(duration=60.0, rateError=1.002)
sPlayer._base = (mPlayer._now() + 1.5) % 60.0   # 1.5s ahead of master
sPeer = FakePeer('WALL-MASTER', CS_US)
sHp = FakeHPlayer(sPlayer, FakeZyre(sPeer))
slave = WallclockInterface(sHp, None, False, player=sPlayer, port=13737,
                           masterName='WALL-MASTER', staleness=1.0,
                           driftLog=driftCsv)
slave._myName = 'WALL-SLAVE'
slave.drifter.doLog = False

# feed the master latch the way mpv status events would (20Hz), skewing 'at'
# into the master's (simulated) clock: at = real_now + CS
def feeder():
    while not stopFeed.is_set():
        master._latch = (mPlayer.position(), int(time.time() * PRECISION) + CS_US)
        stopFeed.wait(0.05)
stopFeed = threading.Event()

# BaseInterface recvThread is non-daemon: a failing assert below would hang
# the process without this
slave.recvThread.daemon = True
master.recvThread.daemon = True
slave.start()
master.start()
f = threading.Thread(target=feeder, daemon=True); f.start()

time.sleep(12)   # let it lock

d = abs(mPlayer._now() - sPlayer._now())
d = min(d, 60.0 - d)
print("   after 12s: |master-slave| = %.0f ms  (slave seeks=%d)" % (d * 1000, sPlayer.seeks))
assert d < 0.08, "slave should be locked within 80ms, got %.3f" % d
assert sPlayer.seeks <= 1, "at most the initial catch-up seek"

# staleness: stop the master -> slave freewheels at speed 1.0
master.stopped.set(); stopFeed.set(); f.join()
time.sleep(2.0)
print("   master silent 2s: slave speed=%.2f freewheeling=%s" % (sPlayer._speed, slave._freewheeling))
assert sPlayer._speed == 1.0, "slave must freewheel at 1.0"
assert slave._freewheeling, "slave must report freewheeling"
print("   PASS")

slave.stopped.set()
time.sleep(0.5)
csv = open(driftCsv).read().splitlines()
print("   drift CSV: %d lines, header: %s" % (len(csv), csv[0]))

print("\nALL TESTS PASSED")
os._exit(0)
