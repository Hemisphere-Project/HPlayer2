"""
Elected clock leader desk test (hplayer2#t-086): hardware-free validation of
WallclockInterface(role='elected') — no fixed master, the node that gave the last transport
order emits the clock, every node still executes every order.

Several wallclock nodes run in ONE process over a fake UDP bus (clock packets) and a fake zyre
bus (orders), both able to drop an order for one node, mute a node's clock, kill a node and
split the fleet in two. What runs is the real thing: WallclockInterface, the Drifter servo, and
zyre's own order path (ZyreNode.makeMsg + preProcessor1/2: the `at` buffer, the busy-wait,
zyre.event then the order). The players are fakes on real time, each with its own crystal error.
The profile is the Anna shape role='elected' expects (anna-players#t-017 writes the real one):
zyre orders -> playlist/player, track end -> one advance decided by the track's name.

No fleet, no mpv, no zyre/czmq. Only termcolor + pymitter:

    python3 -m venv /tmp/wallsync-venv
    /tmp/wallsync-venv/bin/pip install termcolor pymitter
    /tmp/wallsync-venv/bin/python tests/desk_elected.py            # every test, ~3 min
    /tmp/wallsync-venv/bin/python tests/desk_elected.py takeover   # tests whose name matches
    /tmp/wallsync-venv/bin/python tests/desk_elected.py -v ...     # live node logs

Real-time sleeps: the servo, the takeover delay and the graces run at their real cadence.
"""
import sys, os, time, types, threading, queue, json, inspect
import socket as _socket

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

VERBOSE = '-v' in sys.argv
ONLY = [a for a in sys.argv[1:] if not a.startswith('-')]

# --- stub netifaces (C-ext, not needed) --------------------------------------
ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
ni.interfaces = lambda: []
ni.ifaddresses = lambda iface: {}
sys.modules['netifaces'] = ni

# --- logs: per node, kept in memory, printed on failure (or live with -v) -----
import core.module as _module
LOG = []
_logLock = threading.Lock()

def _log(self, *argv):
    who = getattr(self, '_myName', None) or getattr(self, 'name', '?')
    line = '%.3f %-8s %s' % (time.time() % 1000, who, ' '.join(str(a) for a in argv))
    with _logLock:
        LOG.append(line)
        if len(LOG) > 4000:
            del LOG[:1000]
    if VERBOSE:
        print(line)
_module.Module.log = _log

from core.interfaces import wallclock as W
from core.interfaces import zyre as Z
from core.interfaces.wallclock import WallclockInterface, rank_better, natural_key, end_action

PORT = 13737


# =============================================================================
#  Fake UDP bus: the clock packets
# =============================================================================
class UdpBus():
    def __init__(self):
        self.lock = threading.Lock()
        self.socks = []
        self.cut = set()            # (src, dst) pairs that do not hear each other
        self.mute = set()           # nodes whose packets reach nobody
        self.lastSend = {}          # node -> last packet time
        self.sent = []              # (time, node, decoded packet), last few hundred

    def deliver(self, src, port, data):
        now = time.time()
        with self.lock:
            self.lastSend[src] = now
            try:
                self.sent.append((now, src, json.loads(data.decode())))
            except ValueError:
                pass
            if len(self.sent) > 600:
                del self.sent[:200]
            targets = [s for s in self.socks if s.port == port and s.node != src]
        if src in self.mute:
            return
        for s in targets:
            if (src, s.node) not in self.cut:
                s.q.put((data, ('127.0.0.1', port)))

    def split(self, a, b):
        for x in a:
            for y in b:
                self.cut.add((x, y)); self.cut.add((y, x))

    def heal(self):
        self.cut.clear()

BUS = UdpBus()


def _owner():
    """The node a socket belongs to: the WallclockInterface up the creating thread's stack."""
    for fi in inspect.stack(0):
        s = fi.frame.f_locals.get('self')
        if isinstance(s, WallclockInterface):
            return s._myName
    return '?'


class FakeSock():
    def __init__(self, *a, **k):
        self.node = _owner()
        self.bus = BUS
        self.port = None
        self.q = queue.Queue()
        self.timeout = None
    def setsockopt(self, *a): pass
    def settimeout(self, t): self.timeout = t
    def bind(self, addr):
        self.port = addr[1]
        with self.bus.lock:
            self.bus.socks.append(self)
    def sendto(self, data, addr):
        self.bus.deliver(self.node, addr[1], data)
        return len(data)
    def recvfrom(self, n):
        try:
            return self.q.get(timeout=self.timeout)
        except queue.Empty:
            raise _socket.timeout()
    def close(self):
        with self.bus.lock:
            if self in self.bus.socks:
                self.bus.socks.remove(self)

_fs = types.ModuleType('fakesocket')
for _k in dir(_socket):
    if _k.isupper() or _k in ('inet_aton', 'timeout', 'error'):
        setattr(_fs, _k, getattr(_socket, _k))
_fs.socket = FakeSock
W.socket = _fs                  # the wallclock module's `socket` is the fake from here on


# =============================================================================
#  Fake zyre bus: the orders, through zyre's own makeMsg / preProcessor1 / preProcessor2
# =============================================================================
class ZyreBus():
    def __init__(self):
        self.nodes = {}             # name -> Node
        self.cut = set()            # (src, dst)
        self.drop = {}              # name -> number of next orders this node misses
        self.orders = []            # (time, src, event, args, r)

    def broadcast(self, src, event, args=None, delay_ms=0, at=0, extra=None):
        raw = Z.ZyreNode.makeMsg(None, event, args, delay_ms, at, extra)
        d0 = json.loads(raw.decode())
        self.orders.append((time.time(), src, event, d0.get('args'), d0.get('r')))
        for name, n in list(self.nodes.items()):
            if not n.alive:
                continue
            if name != src:
                if (src, name) in self.cut:
                    continue
                if self.drop.get(name):
                    self.drop[name] -= 1
                    continue
            data = json.loads(raw.decode())
            data['from'] = 'self' if name == src else src
            data['group'] = 'broadcast'
            if name == src:
                n.zshim.preProcessor1(data)                         # zyre delivers to self inline
            else:
                threading.Timer(0.005, n.zshim.preProcessor1, args=[data]).start()

ZBUS = ZyreBus()


class ZShim():
    """Just enough of a ZyreNode to run its real preProcessor1/2 on one node."""
    def __init__(self, node):
        self.node = node
        hp = node.hp
        self.interface = types.SimpleNamespace(
            log=lambda *a: _log(types.SimpleNamespace(_myName=node.name), '[zyre]', *a),
            emit=lambda ev, *a: hp.emit('zyre.' + ev, *a))
    def peer(self, uuid):
        return None                 # one process, one clock: no clockshift correction
    def preProcessor1(self, data):
        Z.ZyreNode.preProcessor1(self, data)
    def preProcessor2(self, data, at=0):
        Z.ZyreNode.preProcessor2(self, data, at)


class FakeTimeClient():
    def __init__(self): self.status = 1; self.clockshift = 0

class FakePeer():
    def __init__(self, name):
        self.name = name; self.active = True; self.ip = '127.0.0.1'
        self.timeclient = FakeTimeClient()
    def clockshift(self): return 0

class FakeZyreNode():
    def __init__(self, me):
        self.me = me
        self.book = {}
    def broadcast(self, event, args=None, delay_ms=0, at=0, extra=None):
        ZBUS.broadcast(self.me, event, args, delay_ms, at, extra)
    def peerByName(self, name):
        n = ZBUS.nodes.get(name)
        return FakePeer(name) if n and n.alive else None

class FakeZyre():
    def __init__(self, me): self.node = FakeZyreNode(me)


# =============================================================================
#  Fake hplayer / player / playlist
# =============================================================================
DUR = {}        # basename -> duration (s)

class Emitter():
    def __init__(self): self.h = {}
    def on(self, ev):
        def reg(f):
            self.h.setdefault(ev, []).append(f)
            return f
        return reg
    def emit(self, ev, *args):
        for f in list(self.h.get(ev, [])):
            f(ev, *args)


class FakePlayer():
    """Real-time position x speed x crystal error; ends at its duration (or wraps, loop=True)."""
    name = 'player'

    def __init__(self, rate=1.0, loop=False):
        self.rate = rate
        self.loop = loop
        self.lock = threading.RLock()
        self.media = None
        self.duration = 0.0
        self._base = 0.0
        self._t0 = time.time()
        self._speed = 1.0
        self.playing = False
        self.paused = False
        self.seeks = 0
        self.plays = []

    def _now(self):
        if not self.playing:
            return 0.0
        if self.paused:
            return self._base
        cur = self._base + (time.time() - self._t0) * self._speed * self.rate
        if self.loop and self.duration:
            cur %= self.duration
        return cur

    def position(self):
        with self.lock:
            return round(min(self._now(), self.duration or 1e9), 3)
    def isPlaying(self): return self.playing or self.paused
    def isPaused(self): return self.paused

    def play(self, media, pause=False):
        with self.lock:
            self.media = media
            self.duration = DUR.get(os.path.basename(media), 60.0)
            self._base = 0.0; self._t0 = time.time(); self._speed = 1.0
            self.playing = True; self.paused = False
            self.plays.append(os.path.basename(media))
    def stop(self):
        with self.lock:
            self.playing = False; self.paused = False; self.media = None
    def pause(self):
        with self.lock:
            if self.playing and not self.paused:
                self._base = self._now(); self.paused = True
    def resume(self):
        with self.lock:
            if self.paused:
                self._t0 = time.time(); self.paused = False
    def speed(self, s):
        with self.lock:
            if s == self._speed: return
            self._base = self._now(); self._t0 = time.time(); self._speed = s
    def seekTo(self, milli, exact=False):
        with self.lock:
            self._base = milli / 1000.0
            if self.loop and self.duration:
                self._base %= self.duration
            self._t0 = time.time()
            self.seeks += 1
    def status(self, key=None):
        s = {'media': self.media, 'duration': self.duration if self.media else 0, 'time': self.position()}
        return s[key] if key else s
    def _applyOneLoop(self, v): pass

    def track(self):
        return os.path.basename(self.media) if self.media else ''


class FakePlaylist():
    def __init__(self, player, files):
        self.player = player
        self.files = ['/data/media/' + f for f in files]
        self._index = -1
    def size(self): return len(self.files)
    def index(self): return self._index
    def trackAtIndex(self, k): return self.files[k] if 0 <= k < len(self.files) else None
    def playindex(self, k, pause=False):
        if 0 <= k < len(self.files):
            self._index = k
            self.player.play(self.files[k])
        else:
            self.player.stop()


class FakeSettings():
    def __init__(self): self.v = {}
    def set(self, k, v): self.v[k] = v
    def get(self, k): return self.v.get(k)


class FakeHPlayer(Emitter):
    def __init__(self, player, playlist, zyre):
        super().__init__()
        self.player = player
        self.playlist = playlist
        self.zyre = zyre
        self.settings = FakeSettings()
    def players(self): return [self.player]
    def interface(self, name): return self.zyre if name == 'zyre' else None
    def autoBind(self, module): pass


# =============================================================================
#  Nodes and fleets
# =============================================================================
FILES = ['01_intro.mp3', '02_ambiance_loop.mp3', '03_story.mp3', '04_final_stop.mp3', '05_extra.mp3']
DUR.update({'01_intro.mp3': 12.0, '02_ambiance_loop.mp3': 8.0, '03_story.mp3': 90.0,
            '04_final_stop.mp3': 8.0, '05_extra.mp3': 90.0})


class Node():
    def __init__(self, name, rate=1.0, files=FILES, role='elected', master=False, loop=False, **kw):
        self.name = name
        self.alive = True
        self.player = FakePlayer(rate=rate, loop=loop)
        self.playlist = FakePlaylist(self.player, files)
        self.hp = FakeHPlayer(self.player, self.playlist, FakeZyre(name))
        self.zshim = ZShim(self)
        self.wc = WallclockInterface(self.hp, None, master, player=self.player, port=PORT,
                                     role=role, driftLog=None, **kw)
        self.wc._myName = name
        if self.wc.drifter:
            self.wc.drifter.doLog = VERBOSE
        self.advances = 0
        self._install_profile()
        self._stop = threading.Event()
        self.feeder = threading.Thread(target=self._feed, daemon=True)

    def _install_profile(self):
        hp, wc, pl, p = self.hp, self.wc, self.playlist, self.player
        hp.on('zyre.unbuf_playindex')(lambda ev, idx, *a: pl.playindex(int(idx)))
        hp.on('zyre.stop')(lambda ev, *a: p.stop())
        hp.on('zyre.pause')(lambda ev, *a: p.pause())
        hp.on('zyre.resume')(lambda ev, *a: p.resume())

        def onEnd(ev, *a):
            # The elected Anna end-of-track: one advance (the leader's), decided by the name
            if not wc.mayAdvance():
                return
            idx = pl.index()
            act = end_action(pl.trackAtIndex(idx))
            if act == 'loop':
                self.advances += 1
                wc.order('unbuf_playindex', [idx], 300)
            elif act == 'next' and idx < pl.size() - 1:
                self.advances += 1
                wc.order('unbuf_playindex', [idx + 1], 300)
        hp.on('playlist.end')(onEnd)

    def _feed(self):
        # mpv's status events (20 Hz while it plays; none while paused) + its end of file
        while not self._stop.wait(0.05):
            p = self.player
            with p.lock:
                if not p.playing or p.paused:
                    continue
                pos = p._now()
                ended = not p.loop and pos >= p.duration
                if ended:
                    p.stop()
            if ended:
                self.hp.emit('playlist.end')
            else:
                self.hp.emit('player.status', 'time', round(pos, 3))

    def start(self):
        ZBUS.nodes[self.name] = self
        self.wc.recvThread.daemon = True
        self.wc.start()
        self.feeder.start()
        return self

    def kill(self):
        """Power cut: the interface, its zyre and its player go at once."""
        self.alive = False
        self.wc.stopped.set()
        self._stop.set()
        self.player.stop()

    def order(self, event, args=None, delay_ms=300):
        self.wc.order(event, args, delay_ms)


class Fleet():
    def __init__(self, specs, **kw):
        global BUS, ZBUS
        BUS = UdpBus()
        ZBUS = ZyreBus()
        self.nodes = {}
        for spec in specs:
            name, rate = spec if isinstance(spec, tuple) else (spec, 1.0)
            self.nodes[name] = Node(name, rate=rate, **kw)
        for n in self.nodes.values():
            n.start()

    def __getitem__(self, k): return self.nodes[k]
    def alive(self): return [n for n in self.nodes.values() if n.alive]

    def add(self, name, rate=1.0, **kw):
        n = Node(name, rate=rate, **kw)
        self.nodes[name] = n
        return n.start()

    def leaders(self):
        return sorted(n.name for n in self.alive() if n.wc.isLeader())

    def emitting(self, within=1.0):
        now = time.time()
        return sorted(k for k, t in BUS.lastSend.items() if now - t < within)

    def tracks(self):
        return {n.name: n.player.track() for n in self.alive()}

    def spread(self, ref):
        """max |position - ref's| over the alive nodes playing ref's track."""
        r = self.nodes[ref].player
        t = r.track()
        worst = 0.0
        for n in self.alive():
            if n.player.track() == t and n.player.playing:
                worst = max(worst, abs(n.player.position() - r.position()))
        return worst

    def shutdown(self):
        for n in self.alive():
            n.kill()
        time.sleep(0.4)


# =============================================================================
#  Harness
# =============================================================================
RESULTS = []

class Fail(Exception):
    pass

def check(cond, msg):
    if not cond:
        raise Fail(msg)
    print('   ok  ' + msg)

def wait_for(pred, timeout, step=0.05):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return time.time() - t0
        time.sleep(step)
    return None

def run(name, fn):
    if ONLY and not any(o in name for o in ONLY):
        return
    print('== %s ==' % name)
    del LOG[:]
    t0 = time.time()
    try:
        fn()
        RESULTS.append((name, True, time.time() - t0))
        print('   PASS (%.0f s)' % (time.time() - t0))
    except Fail as e:
        RESULTS.append((name, False, time.time() - t0))
        print('   FAIL: %s' % e)
        print('   --- last node logs ---')
        for line in LOG[-60:]:
            print('   | ' + line)


# =============================================================================
#  Tests
# =============================================================================
def t_pure():
    check(sorted(['Anna-10', 'Anna-2', 'Anna-1'], key=natural_key) == ['Anna-1', 'Anna-2', 'Anna-10'],
          'natural name order: Anna-1 < Anna-2 < Anna-10')
    check(rank_better((5, 0, 'Anna-9'), (4, 7, 'Anna-1')), 'a higher term (an order) beats any takeover of the term before')
    check(rank_better((4, 1, 'Anna-9'), (4, 0, 'Anna-1')), 'same term: a takeover (sub+1) beats the leader it replaces')
    check(rank_better((4, 0, 'Anna-2'), (4, 0, 'Anna-10')), 'same term and sub: the lower NATURAL name wins')
    check(rank_better((0, 0, 'x'), None) and not rank_better(None, (0, 0, 'x')), 'any rank beats no leader')
    check(rank_better((1, 0, 'Anna-2'), (1, 0, 'anna-02')) != rank_better((1, 0, 'anna-02'), (1, 0, 'Anna-2')),
          'naturally-equal names still have one total order')
    check(end_action('/data/media/02_ambiance_loop.mp3') == 'loop', "'_loop' in the name replays")
    check(end_action('04_final_stop.mp3') == 'stop', "'_stop' in the name stops")
    check(end_action('03_story.mp3') == 'next' and end_action('_loop.mp3') == 'next', 'anything else moves on')
    m = json.loads(Z.ZyreNode.makeMsg(None, 'unbuf_playindex', [3], 300, 0, {'r': [7, 0, 'Anna-4']}).decode())
    check(m['r'] == [7, 0, 'Anna-4'] and m['args'] == [3] and 'at' in m, 'zyre makeMsg merges the rank into the order')
    m = json.loads(Z.ZyreNode.makeMsg(None, 'stop').decode())
    check(set(m) == {'event', 'args'}, 'zyre makeMsg without extra: the wire is unchanged')


def t_fixed_unchanged():
    # role='fixed' (the Biennale/LEA/KARIKIS fleets): first-heard master, no rank on the wire
    f = Fleet([], )
    m = Node('WALL-MASTER', role='fixed', master=True, loop=True).start()
    s = Node('WALL-SLAVE', rate=1.002, role='fixed', master=False, loop=True).start()
    m.player.play('/data/media/loop.mp4'); s.player.play('/data/media/loop.mp4')
    DUR['loop.mp4'] = 60.0
    m.player.duration = s.player.duration = 60.0
    s.player.seekTo(((m.player.position() + 1.5) % 60.0) * 1000)
    time.sleep(12)
    d = abs(m.player.position() - s.player.position()); d = min(d, 60.0 - d)
    check(d < 0.08, 'fixed slave locked on the fixed master: |diff| = %.0f ms after 12 s' % (d * 1000))
    pk = [p for (_, src, p) in BUS.sent if src == 'WALL-MASTER']
    check(pk and not any(k in pk[-1] for k in ('t', 'u', 'z')), 'fixed packets carry no rank/pause fields (%s)' % sorted(pk[-1]))
    check(m.wc.isLeader() and not s.wc.isLeader() and s.wc.leader() == 'WALL-MASTER', 'roles are the profile\'s: master leads, slave locked on it')
    check(not m.wc.elected and s.wc.mayAdvance(), 'fixed: every node may advance (unchanged)')
    m.kill(); s.kill(); time.sleep(0.4)


def t_order_moves_leadership():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.003), ('Anna-3', 0.997)])
    time.sleep(0.5)
    check(f.leaders() == [] and f.emitting() == [], 'a fleet nobody ordered yet: no leader, no clock')

    f['Anna-1'].order('unbuf_playindex', [0])
    t = wait_for(lambda: f.leaders() == ['Anna-1'], 2.0)
    check(t is not None, 'order from Anna-1 -> Anna-1 leads (%.2f s)' % (t or 0))
    time.sleep(6)
    check(set(f.tracks().values()) == {'01_intro.mp3'}, 'everyone plays the ordered track')
    check(f.emitting() == ['Anna-1'], 'only the leader emits: %s' % f.emitting())
    sp = f.spread('Anna-1')
    check(sp < 0.08, 'followers locked on it: spread %.0f ms' % (sp * 1000))
    check(f['Anna-2'].wc.leader() == 'Anna-1' and f['Anna-3'].wc._lockedName == 'Anna-1', 'followers know their leader')

    # ── leadership moves to Anna-2 with its order: no clock gap on Anna-3
    gaps = []
    stop = threading.Event()
    def sampler():
        last = f['Anna-3'].wc.hLastAccept
        while not stop.wait(0.01):
            v = f['Anna-3'].wc.hLastAccept
            if v != last:
                gaps.append(v - last); last = v
    th = threading.Thread(target=sampler, daemon=True); th.start()
    time.sleep(1.0)
    f['Anna-2'].order('unbuf_playindex', [2])
    t = wait_for(lambda: f.leaders() == ['Anna-2'], 2.0)
    check(t is not None, 'order from Anna-2 -> Anna-2 leads, Anna-1 demoted (%.2f s)' % (t or 0))
    time.sleep(5)
    stop.set(); th.join()
    check(f.emitting() == ['Anna-2'], 'only the new leader emits: %s' % f.emitting())
    check(gaps and max(gaps) < 1.0, 'Anna-3 heard a clock all along: largest gap %.0f ms' % (max(gaps or [9]) * 1000))
    check(set(f.tracks().values()) == {'03_story.mp3'}, 'everyone on the new track')
    sp = f.spread('Anna-2')
    check(sp < 0.08, 'locked on the new leader: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_missed_order():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].order('unbuf_playindex', [2])
    time.sleep(4)
    ZBUS.drop['Anna-3'] = 1                     # Anna-3 misses the next order
    f['Anna-2'].order('unbuf_playindex', [4])
    time.sleep(1.0)
    check(f['Anna-3'].player.track() == '03_story.mp3' and f['Anna-2'].player.track() == '05_extra.mp3',
          'Anna-3 missed the order: still on 03_story, the others on 05_extra')
    t = wait_for(lambda: f['Anna-3'].player.track() == '05_extra.mp3', 8.0)
    check(t is not None, 'Anna-3 adopted the rank from the packets and joined 05_extra (%.1f s after)' % ((t or 0) + 1))
    check(f['Anna-3'].wc.leader() == 'Anna-2' and f.leaders() == ['Anna-2'], 'Anna-3 follows Anna-2')
    time.sleep(5)
    sp = f.spread('Anna-2')
    check(sp < 0.1, 'Anna-3 at the leader\'s position: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_missed_stop_pause_resume():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].order('unbuf_playindex', [2])
    time.sleep(4)

    ZBUS.drop['Anna-3'] = 1
    f['Anna-1'].order('pause', None, 0)
    time.sleep(0.3)
    check(f['Anna-1'].player.isPaused() and not f['Anna-3'].player.isPaused(), 'Anna-3 missed the pause')
    t = wait_for(lambda: f['Anna-3'].player.isPaused(), 5.0)
    check(t is not None, 'Anna-3 paused from the leader\'s z=1 beats (%.1f s)' % ((t or 0) + 0.3))
    time.sleep(2.0)
    check(f['Anna-3'].player.isPaused(), 'and stays paused (no model tick resumed it)')

    ZBUS.drop['Anna-3'] = 1
    f['Anna-1'].order('resume', None, 0)
    t = wait_for(lambda: not f['Anna-3'].player.isPaused(), 5.0)
    check(t is not None, 'missed resume: the next chase tick resumed Anna-3 (%.1f s)' % (t or 0))
    time.sleep(4)
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'back in sync after the pause: spread %.0f ms' % (sp * 1000))

    ZBUS.drop['Anna-3'] = 1
    f['Anna-1'].order('stop', None, 0)
    time.sleep(0.3)
    check(not f['Anna-1'].player.isPlaying() and f['Anna-3'].player.isPlaying(), 'Anna-3 missed the stop')
    t = wait_for(lambda: not f['Anna-3'].player.isPlaying(), 6.0)
    check(t is not None, 'Anna-3 stopped from the leader\'s p=0 beats (%.1f s)' % ((t or 0) + 0.3))
    time.sleep(10)
    check(f.leaders() == ['Anna-1'], 'a stopped fleet: nobody claims, Anna-1 still leads (%s)' % f.leaders())
    f.shutdown()


def t_takeover_and_restart():
    f = Fleet([('Anna-1', 1.001), ('Anna-2', 1.002), ('Anna-3', 1.0), ('Anna-4', 0.998)])
    f['Anna-3'].order('unbuf_playindex', [2])
    time.sleep(6)
    check(f.leaders() == ['Anna-3'], 'Anna-3 leads')
    t0 = time.time()
    f['Anna-3'].kill()
    t = wait_for(lambda: len(f.leaders()) >= 1, 14.0)
    check(t is not None and 7.0 < t < 10.5, 'a takeover after ~8 s of silence (%.1f s)' % (t or 0))
    time.sleep(1.0)
    check(f.leaders() == ['Anna-1'], 'simultaneous claims converged on the lowest name: %s' % f.leaders())
    check(all(n.player.track() == '03_story.mp3' for n in f.alive()), 'nobody stopped playing through the outage')
    time.sleep(4)
    check(f.emitting() == ['Anna-1'], 'one emitter: %s' % f.emitting())
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'the fleet is locked on the successor: spread %.0f ms' % (sp * 1000))
    r = f['Anna-2'].wc._rank
    check(r[1] == 1 and r[2] == 'Anna-1', 'the takeover kept the term, bumped the sub: %s' % (r,))

    # ── the dead leader comes back (term 0, stopped): it follows, never reclaims
    n = f.add('Anna-3')
    t = wait_for(lambda: n.player.track() == '03_story.mp3', 8.0)
    check(t is not None, 'restarted Anna-3 joined the show from the packets (%.1f s)' % (t or 0))
    time.sleep(5)
    check(f.leaders() == ['Anna-1'] and n.wc.leader() == 'Anna-1', 'and follows Anna-1: %s' % f.leaders())
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'in sync: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_partition_heal():
    f = Fleet([('Anna-2', 1.001), ('Anna-3', 0.999), ('Anna-5', 1.0), ('Anna-7', 1.002)])
    f['Anna-5'].order('unbuf_playindex', [2])
    time.sleep(5)
    A, B = ['Anna-5', 'Anna-7'], ['Anna-2', 'Anna-3']
    BUS.split(A, B)
    for x in A:
        for y in B:
            ZBUS.cut.add((x, y)); ZBUS.cut.add((y, x))
    t = wait_for(lambda: f['Anna-2'].wc.isLeader(), 14.0)
    check(t is not None, 'side B lost Anna-5: Anna-2 took over (%.1f s)' % (t or 0))
    f['Anna-7'].order('unbuf_playindex', [4])  # side A: a real order, one term up
    time.sleep(3)
    check(f['Anna-7'].wc.isLeader() and f['Anna-2'].wc.isLeader(), 'two leaders while split: %s' % f.leaders())
    check(f['Anna-2'].player.track() == '03_story.mp3' and f['Anna-5'].player.track() == '05_extra.mp3',
          'side A moved to 05_extra, side B still on 03_story')
    BUS.heal(); ZBUS.cut.clear()
    t = wait_for(lambda: f.leaders() == ['Anna-7'], 3.0)
    check(t is not None, 'healed: the ORDER side wins, though Anna-2 < Anna-7 by name (%s)' % f.leaders())
    t = wait_for(lambda: set(f.tracks().values()) == {'05_extra.mp3'}, 8.0)
    check(t is not None, 'side B rejoined the latest order: %s' % f.tracks())
    time.sleep(5)
    sp = f.spread('Anna-7')
    check(sp < 0.1, 'one show again: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_two_orders_in_buffer():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-2'].order('unbuf_playindex', [0])
    time.sleep(3)
    f['Anna-1'].order('unbuf_playindex', [2])        # the remote...
    time.sleep(0.05)
    f['Anna-3'].order('unbuf_playindex', [4])        # ...and a keypad, 50 ms later
    terms = [o[4][0] for o in ZBUS.orders[-2:]]
    check(terms[0] == terms[1], 'both orders carry the same term (%s)' % terms)
    time.sleep(6)
    check(f.leaders() == ['Anna-1'], 'one leader, the lower name of the two: %s' % f.leaders())
    check(set(f.tracks().values()) == {'05_extra.mp3'}, 'everyone on the LATER order\'s state: %s' % f.tracks())
    sp = f.spread('Anna-1')
    check(sp < 0.08, 'and in sync: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_track_end():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-2'].order('unbuf_playindex', [0])        # 01_intro, 12 s
    time.sleep(1)
    n0 = len(ZBUS.orders)
    t = wait_for(lambda: f['Anna-1'].player.track() == '02_ambiance_loop.mp3', 16.0)
    check(t is not None, 'end of 01_intro -> the fleet moved on to 02_ambiance_loop')
    adv = ZBUS.orders[n0:]
    check(len(adv) == 1 and adv[0][1] == 'Anna-2' and adv[0][3] == [1],
          'ONE advance, by the leader: %s' % [(o[1], o[2], o[3]) for o in adv])
    n0 = len(ZBUS.orders)
    plays0 = len(f['Anna-1'].player.plays)
    t = wait_for(lambda: len(f['Anna-1'].player.plays) > plays0, 10.0)  # 02_ambiance_loop is 8 s
    check(t is not None, '02_ambiance_loop ended and was replayed (%.1f s)' % (t or 0))
    time.sleep(0.5)
    adv = ZBUS.orders[n0:]
    check(len(adv) == 1 and adv[0][3] == [1], "'_loop' track: one replay order, same index: %s" % [(o[1], o[3]) for o in adv])
    check(set(f.tracks().values()) == {'02_ambiance_loop.mp3'}, 'everyone replays it')

    # ── the leader dies 3 s before the end: the followers advance themselves (no takeover yet)
    t = wait_for(lambda: 4.5 < f['Anna-2'].player.position() < 5.5, 7.0)
    check(t is not None, 'leader 3 s from the end of the replay (%.1f s)' % (t or 0))
    f['Anna-2'].kill()
    n0 = len(ZBUS.orders)
    t = wait_for(lambda: len(ZBUS.orders) > n0, 6.0)
    check(t is not None, 'leader dead before the track end: a follower ordered the replay (%.1f s)' % (t or 0))
    time.sleep(1.5)
    adv = ZBUS.orders[n0:]
    check(all(o[3] == [1] for o in adv) and 1 <= len(adv) <= 2, 'one order per surviving player at most: %s' % [(o[1], o[3]) for o in adv])
    check(set(f.tracks().values()) == {'02_ambiance_loop.mp3'}, 'the survivors replay it: %s' % f.tracks())
    check(f.leaders() == ['Anna-1'], 'and the fallback order made a leader: %s' % f.leaders())
    f.shutdown()


TESTS = [
    ('pure: rank order, natural names, end-of-track by name, zyre wire', t_pure),
    ('fixed: role=fixed unchanged (first-heard master, no rank on the wire)', t_fixed_unchanged),
    ('order: the last commander leads; leadership moves with no clock gap', t_order_moves_leadership),
    ('missed order: adopt the rank from the packets, follow the media', t_missed_order),
    ('missed pause / resume / stop: follow the leader\'s state', t_missed_stop_pause_resume),
    ('takeover: dead leader -> ~8 s -> lowest name; the dead one restarts as a follower', t_takeover_and_restart),
    ('partition: an order on one side beats a takeover on the other', t_partition_heal),
    ('two orders 50 ms apart: one leader, the later state everywhere', t_two_orders_in_buffer),
    ('track end: one advance by the leader, _loop/_stop by name, fallback when it is dead', t_track_end),
]

for name, fn in TESTS:
    run(name, fn)

print()
for name, ok, dt in RESULTS:
    print('%s  %4.0fs  %s' % ('PASS' if ok else 'FAIL', dt, name))
bad = [r for r in RESULTS if not r[1]]
print('\n' + ('ALL %d PASSED' % len(RESULTS) if not bad else '%d of %d FAILED' % (len(bad), len(RESULTS))))
sys.stdout.flush()
os._exit(1 if bad else 0)            # node threads are daemons; skip their teardown
