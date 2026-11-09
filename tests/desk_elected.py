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
    /tmp/wallsync-venv/bin/python tests/desk_elected.py            # every test, ~12 min
    /tmp/wallsync-venv/bin/python tests/desk_elected.py takeover   # tests whose name matches
    /tmp/wallsync-venv/bin/python tests/desk_elected.py -v ...     # live node logs

Real-time sleeps: the servo, the takeover delay and the graces run at their real cadence.
"""
import sys, os, time, types, threading, queue, json, inspect, random, statistics
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
        self.clockCut = set()       # (src, dst) pairs where the clock is lost but presence passes
        self.mute = set()           # nodes whose packets reach nobody
        self.lastSend = {}          # node -> last CLOCK packet time (presence is not emitting)
        self.hello = {}             # node -> last presence packet time (#t-089)
        self.sent = []              # (time, node, decoded clock packet), last few hundred

    def deliver(self, src, port, data):
        now = time.time()
        try:
            pkt = json.loads(data.decode())
        except ValueError:
            pkt = None
        presence = isinstance(pkt, dict) and bool(pkt.get('hi'))
        with self.lock:
            if presence:
                self.hello[src] = now
            else:
                self.lastSend[src] = now
                if pkt is not None:
                    self.sent.append((now, src, pkt))
            if len(self.sent) > 600:
                del self.sent[:200]
            targets = [s for s in self.socks if s.port == port and s.node != src]
        if src in self.mute:
            return
        for s in targets:
            if (src, s.node) in self.cut or (not presence and (src, s.node) in self.clockCut):
                continue
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
        self.nodes = {}             # name -> Node (the latest under that name)
        self.members = []           # every Node ever started on this bus (two may share a name)
        self.hold = set()           # names cut off with libzyre's queueing: their traffic waits for release()
        self.held = []
        self.cut = set()            # (src, dst)
        self.drop = {}              # name -> number of next orders this node misses
        self.tcReady = True         # False: no zyre TimeClient ever finishes (packet clock only)
        self.orders = []            # (time, src, event, args, r)

    def broadcast(self, src, event, args=None, delay_ms=0, at=0, extra=None, owner=None):
        raw = Z.ZyreNode.makeMsg(None, event, args, delay_ms, at, extra)
        d0 = json.loads(raw.decode())
        self.orders.append((time.time(), src, event, d0.get('args'), d0.get('r')))
        for n in list(self.members):
            name = n.name
            if not n.alive:
                continue
            me = n is owner if owner is not None else name == src
            if not me:
                if (src, name) in self.cut:
                    continue
                if self.drop.get(name):
                    self.drop[name] -= 1
                    continue
            data = json.loads(raw.decode())
            data['from'] = 'self' if me else src
            data['group'] = 'broadcast'
            if me:
                n.zshim.preProcessor1(data)                         # zyre delivers to self inline
            elif src in self.hold or name in self.hold:
                self.held.append((n, data))                         # queued in the peer's DEALER until the heal
            else:
                threading.Timer(0.005, n.zshim.preProcessor1, args=[data]).start()

    def release(self):
        """The cut heals: what libzyre queued arrives now, LATE (preProcessor1 still plays it)."""
        self.hold.clear()
        held, self.held = self.held, []
        for n, data in held:
            if n.alive:
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
    def __init__(self, bus): self.status = 1 if bus.tcReady else 0; self.clockshift = 0

class FakePeer():
    def __init__(self, name, bus):
        self.name = name; self.active = True; self.ip = '127.0.0.1'
        self.timeclient = FakeTimeClient(bus)
    def clockshift(self): return 0

class FakeZyreNode():
    def __init__(self, me):
        self.me = me
        self.bus = ZBUS
        self.owner = None
        self.uuid = 'uuid-%s-%x' % (me, id(self))
    @property
    def book(self):
        """zyre's peer book, shaped like the real one: every live player on the bus keyed by its
        uuid — the node ITSELF included (ZyreNode.__init__ books itself), and any other one that
        carries our name."""
        return {n.hp.zyre.node.uuid: FakePeer(n.name, self.bus) for n in self.bus.members if n.alive}
    def broadcast(self, event, args=None, delay_ms=0, at=0, extra=None):
        self.bus.broadcast(self.me, event, args, delay_ms, at, extra, owner=self.owner)
    def peerByName(self, name):
        n = self.bus.nodes.get(name)
        return FakePeer(name, self.bus) if n and n.alive else None

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
    """Real-time position x speed x crystal error; ends at its duration (or wraps, loop=True).
    Like mpv, a new file takes openDelay to open: its position holds at 0 and no status event
    leaves meanwhile (a leader is silent for that long after a track change).
    mpvLike: position() is the LAST status event's value, rounded to 10 ms, like mpv.py's
    (_status['time'] <- each time-pos event), and the events come 45-85 ms apart, mpv's cadence on
    audio (measured 2026-11-06, mpv 0.41: median 55-80 ms). The default player answers the exact
    position at any instant, which no real player does: it hid a ~35 ms follower bias on the desk."""
    name = 'player'

    def __init__(self, rate=1.0, loop=False, openDelay=0.3, mpvLike=False):
        self.mpvLike = mpvLike
        self._cached = 0.0
        self.rate = rate
        self.loop = loop
        self.openDelay = openDelay
        self._openUntil = 0.0
        self.seekLog = []           # (track, target s, when)
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

    def _clock(self):
        return max(time.time(), self._openUntil)

    def opening(self):
        return self.playing and time.time() < self._openUntil

    def _now(self):
        if not self.playing:
            return 0.0
        if self.paused:
            return self._base
        cur = self._base + (self._clock() - self._t0) * self._speed * self.rate
        if self.loop and self.duration:
            cur %= self.duration
        return cur

    def position(self):
        with self.lock:
            if self.mpvLike:
                return self._cached
            return round(min(self._now(), self.duration or 1e9), 3)
    def isPlaying(self): return self.playing or self.paused
    def isPaused(self): return self.paused

    def play(self, media, pause=False):
        with self.lock:
            self.media = media
            self.duration = DUR.get(os.path.basename(media), 60.0)
            self._openUntil = time.time() + self.openDelay
            self._base = 0.0; self._t0 = self._openUntil; self._speed = 1.0
            self.playing = True; self.paused = False
            self._cached = 0.0                  # mpv.py: update('time', 0) on play
            self.plays.append(os.path.basename(media))
    def stop(self):
        with self.lock:
            self.playing = False; self.paused = False; self.media = None
            self._cached = 0.0
    def pause(self):
        with self.lock:
            if self.playing and not self.paused:
                self._base = self._now(); self.paused = True
    def resume(self):
        with self.lock:
            if self.paused:
                self._t0 = self._clock(); self.paused = False
    def speed(self, s):
        with self.lock:
            if s == self._speed: return
            self._base = self._now(); self._t0 = self._clock(); self._speed = s
    def seekTo(self, milli, exact=False):
        with self.lock:
            self._base = milli / 1000.0
            if self.loop and self.duration:
                self._base %= self.duration
            self._t0 = self._clock()
            self.seeks += 1
            self.seekLog.append((self.track(), round(self._base, 2), time.time()))
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
        self.hp = None
    def size(self): return len(self.files)
    def index(self): return self._index
    def trackAtIndex(self, k): return self.files[k] if 0 <= k < len(self.files) else None
    def playindex(self, k, pause=False):
        if 0 <= k < len(self.files):
            self._index = k
            if self.hp:
                self.hp.emit('playlist.do-play', self.files[k], k, pause)
            self.player.play(self.files[k])
        else:
            self.player.stop()                      # the real one: emit('stop') + emit('nomedia')
            if self.hp:
                self.hp.emit('playlist.nomedia')


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


ALL_NODES = []

class Node():
    def __init__(self, name, rate=1.0, files=FILES, role='elected', master=False, loop=False,
                 openDelay=0.3, mpvLike=False, **kw):
        self.name = name
        self.alive = True
        ALL_NODES.append(self)
        self.player = FakePlayer(rate=rate, loop=loop, openDelay=openDelay, mpvLike=mpvLike)
        self.playlist = FakePlaylist(self.player, files)
        self.hp = FakeHPlayer(self.player, self.playlist, FakeZyre(name))
        self.playlist.hp = self.hp
        self.zshim = ZShim(self)
        self.wc = WallclockInterface(self.hp, None, master, player=self.player, port=PORT,
                                     role=role, driftLog=None, **kw)
        self.wc._myName = name
        if self.wc.drifter:
            self.wc.drifter.doLog = VERBOSE
        self.advances = 0
        self.localAdvances = 0
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
            # The elected Anna end-of-track: one advance (the leader's), decided by the name; a
            # follower cut off alone moves on by itself, with no order (26-anna's track_end, #t-089)
            idx = pl.index()
            track = pl.trackAtIndex(idx)
            act = end_action(track)
            target = idx if act == 'loop' else idx + 1
            if act == 'stop' or (act == 'next' and idx >= pl.size() - 1):
                return
            if not wc.mayAdvance():
                if getattr(wc, 'advanceAlone', lambda: False)():
                    self.localAdvances += 1
                    threading.Timer(0.3, pl.playindex, args=[target]).start()   # the order buffer, like the parc's
                return
            self.advances += 1
            try:
                wc.order('unbuf_playindex', [target], 300, auto=True, source=track)
            except TypeError:                       # (an older wallclock: no track-end advances)
                wc.order('unbuf_playindex', [target], 300)
        hp.on('playlist.end')(onEnd)

    def _feed(self):
        # mpv's status events (20 Hz while it plays; none while paused) + its end of file.
        # mpvLike: mpv's own cadence on audio, and the value rounded and cached like mpv.py's.
        while not self._stop.wait(random.uniform(0.045, 0.085) if self.player.mpvLike else 0.05):
            p = self.player
            with p.lock:
                if not p.playing or p.paused or p.opening():
                    continue
                pos = p._now()
                ended = not p.loop and pos >= p.duration
                if ended:
                    p.stop()
                elif p.mpvLike:
                    pos = p._cached = round(pos, 2)
            if ended:
                self.hp.emit('playlist.end')
            else:
                self.hp.emit('player.status', 'time', round(pos, 3))

    def start(self):
        self.hp.zyre.node.owner = self
        self.hp.zyre.node.bus.members.append(self)
        self.hp.zyre.node.bus.nodes[self.name] = self
        self._udp = BUS
        BUS.mute.discard(self.name)         # a node restarted under a dead one's name speaks again
        self.wc.recvThread.daemon = True
        self.wc.start()
        self.feeder.start()
        return self

    def kill(self):
        """Power cut: the interface, its zyre and its player go at once — and nothing leaves it
        after that instant (no last packet)."""
        self.alive = False
        self.wc.stopped.set()
        bus = getattr(self, '_udp', None)
        if bus is not None:
            bus.mute.add(self.name)
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
    left = [n for n in ALL_NODES if n.alive]
    for n in left:
        n.kill()
    if left:
        time.sleep(0.5)


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
    s.hp.emit('zyre.event', {'event': 'unbuf_playindex', 'args': [1], 'r': [9, 0, 'WALL-SLAVE']})
    check(not s.wc.isLeader() and s.wc._rank is None, 'a ranked order changes nothing on a fixed node')
    m2 = Node('WALL-M2', role='fixed', master=True, loop=True).start()
    m2.player.play('/data/media/loop.mp4')
    time.sleep(3)
    check(s.wc._lockedName == 'WALL-MASTER', 'a second fixed master is ignored while the first is alive (first heard)')
    d = abs(m.player.position() - s.player.position()); d = min(d, 60.0 - d)
    check(d < 0.08, 'still locked on the first: |diff| = %.0f ms' % (d * 1000))
    m.kill(); s.kill(); m2.kill(); time.sleep(0.4)


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
    tOrder = time.time()
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


def t_slow_open():
    # A mixed fleet: the new leader opens its file in 1.5 s (a video on a 3B+), its followers in
    # 0.2 s (mp3). They play the new track for 1.3 s while the leader is still silent: their model
    # of the OLD track must not drive the new one (a seek to the old track's position)
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.003), ('Anna-3', 0.997)], openDelay=0.2)
    f['Anna-2'].player.openDelay = 1.5
    f['Anna-1'].order('unbuf_playindex', [0])
    time.sleep(7)                                    # a model of 01_intro now says 6+ s
    tOrder = time.time()
    f['Anna-2'].order('unbuf_playindex', [2])
    time.sleep(6)
    wild = [(n.name, s[1]) for n in f.alive() for s in n.player.seekLog
            if s[2] > tOrder and s[0] == '03_story.mp3' and s[1] > 3.0]
    check(not wild, 'no follower seeked the new track to the old track\'s position: %s' % wild)
    check(f.leaders() == ['Anna-2'], 'Anna-2 leads')
    # (the mp3 followers started 1.3 s ahead of the video leader: the servo slows them down, and
    # its last 80 ms is the Drifter's slow tail — converging, not the bug this test is about)
    sp = f.spread('Anna-2')
    check(sp < 0.15, 'converging on it: spread %.0f ms after 6 s' % (sp * 1000))
    f.shutdown()


def t_order_fires_not_received():
    # Leadership moves when the order FIRES, not when it arrives: during its `at` buffer the old
    # leader still leads and emits (adopting at reception would hand the clock to a node still
    # playing the old state).
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].order('unbuf_playindex', [0])
    time.sleep(3)
    f['Anna-2'].order('unbuf_playindex', [2], 1500)
    time.sleep(0.8)
    check(f.leaders() == ['Anna-1'] and f.emitting(0.3) == ['Anna-1'],
          'mid-buffer: Anna-1 still leads and emits (%s / %s)' % (f.leaders(), f.emitting(0.3)))
    check(set(f.tracks().values()) == {'01_intro.mp3'}, 'and everyone is still on the old state')
    t = wait_for(lambda: f.leaders() == ['Anna-2'], 2.0)
    check(t is not None, 'the order fired: Anna-2 leads (%.1f s later)' % (t or 0))
    f.shutdown()


def t_reboot_while_stopped():
    # The leader reboots while the fleet is stopped: nobody else emits, so it comes back at term 0
    # and its next order ranks BELOW what the followers remember of it.
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].order('unbuf_playindex', [2])
    time.sleep(3)
    f['Anna-1'].order('stop', None, 0)
    time.sleep(2)
    check(not any(n.player.isPlaying() for n in f.alive()), 'the fleet is stopped, Anna-1 leads %s' % (f['Anna-2'].wc._rank,))

    f['Anna-1'].kill()
    time.sleep(9.5)                                  # a real reboot: longer than takeoverAfter
    n = f.add('Anna-1')
    time.sleep(1.0)
    check(n.wc._rank is None, 'rebooted Anna-1 heard nothing (a stopped fleet has no clock but its leader\'s)')
    n.order('unbuf_playindex', [0])
    t = wait_for(lambda: n.wc._rank and all(f[x].wc._rank == n.wc._rank and f[x].wc._lockedName == 'Anna-1' for x in ('Anna-2', 'Anna-3')), 3.0)
    check(t is not None, 'its order at term %d is followed: the followers\' leader was silent > takeoverAfter (%.1f s)'
          % (n.wc._rank[0] if n.wc._rank else -1, t or 0))
    time.sleep(4)
    sp = f.spread('Anna-1')
    check(f.leaders() == ['Anna-1'] and sp < 0.08, 'one leader, locked: spread %.0f ms' % (sp * 1000))

    # a fast restart (within takeoverAfter), stopped again: followed once its old self is 8 s silent
    n.order('stop', None, 0)
    time.sleep(2)
    n.kill()
    t0 = time.time()
    time.sleep(2)
    n2 = f.add('Anna-1')
    time.sleep(0.5)
    n2.order('unbuf_playindex', [2])
    t = wait_for(lambda: all(f[x].wc._rank == n2.wc._rank for x in ('Anna-2', 'Anna-3')), 10.0)
    check(t is not None and time.time() - t0 < 11.0,
          'fast restart: followed %.1f s after the old leader went silent' % (time.time() - t0))
    time.sleep(3)
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'locked: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_restart_within_takeover():
    # The leader crashes while playing and is back in 3 s: it never reclaims; the takeover at ~8 s
    # still happens and the restarted node follows its successor.
    f = Fleet([('Anna-1', 1.001), ('Anna-2', 1.0), ('Anna-3', 0.998)])
    f['Anna-2'].order('unbuf_playindex', [2])
    time.sleep(5)
    f['Anna-2'].kill()
    t0 = time.time()
    time.sleep(3)
    n = f.add('Anna-2')
    t = wait_for(lambda: f.leaders() != [], 10.0)
    check(t is not None and 7.0 < time.time() - t0 < 10.5, 'takeover %.1f s after the crash' % (time.time() - t0))
    time.sleep(0.5)
    check(f.leaders() == ['Anna-1'] and not n.wc.isLeader(), 'by Anna-1; the restarted Anna-2 did not reclaim: %s' % f.leaders())
    t = wait_for(lambda: n.player.track() == '03_story.mp3', 6.0)
    check(t is not None, 'restarted Anna-2 joined the show')
    time.sleep(4)
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'in sync: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_stop_without_timeclient():
    # No zyre TimeClient (edge 15: the packet clock needs 3 one-second buckets after a lock
    # switch). The leader's stop needs no clock shift: it must be followed at once, not after it.
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    ZBUS.tcReady = False
    f['Anna-1'].order('unbuf_playindex', [2])
    time.sleep(6)
    ZBUS.drop['Anna-3'] = 2                     # Anna-3 misses the next two orders
    f['Anna-2'].order('unbuf_playindex', [4])
    t = wait_for(lambda: f['Anna-3'].wc._lockedName == 'Anna-2', 3.0)
    check(t is not None, 'Anna-3 locked on Anna-2 from its packets (fresh packet clock, %.1f s)' % ((t or 0)))
    time.sleep(0.3)
    t0 = time.time()
    f['Anna-2'].order('stop', None, 0)
    t = wait_for(lambda: not f['Anna-3'].player.isPlaying(), 8.0)
    check(t is not None and t < 3.6, 'Anna-3 followed the missed stop in %.1f s (stopGrace 2 s + a beat), clock shift or not' % (t or 99))
    f.shutdown()

def cut(names, others, hold=False):
    """WiFi cut between two groups: clock packets lost; zyre orders dropped, or held (libzyre's
    queue across a cut shorter than its 10 s expiry) and delivered late on heal()."""
    BUS.split(names, others)
    if hold:
        ZBUS.hold.update(names)
    else:
        for x in names:
            for y in others:
                ZBUS.cut.add((x, y)); ZBUS.cut.add((y, x))

def heal():
    BUS.heal()
    ZBUS.cut.clear()
    ZBUS.release()


def t_wanderer_cannot_undo_stop():
    # A player cut off across loop ends of a `_loop` track while the operator stops the fleet: its
    # track-end advances must never out-rank the stop (they used to stamp term+1, once per loop)
    f = Fleet([('Anna-1', 1.0), ('Anna-3', 1.002), ('Anna-9', 0.998)])
    f['Anna-3'].order('unbuf_playindex', [1])        # 02_ambiance_loop, 8 s
    time.sleep(2)
    cut(['Anna-1'], ['Anna-3', 'Anna-9'])            # the LOWER name wanders off: it wins every tie
    time.sleep(1)
    f['Anna-3'].order('stop', None, 300)
    time.sleep(15)                                   # Anna-1 loops alone, twice
    check(f['Anna-1'].player.isPlaying() and not f['Anna-3'].player.isPlaying(), 'while cut: the wanderer loops alone, the fleet is stopped')
    heal()
    time.sleep(5)
    check(not f['Anna-3'].player.isPlaying() and not f['Anna-9'].player.isPlaying(),
          'healed: the operator\'s stop stands (%s)' % f.tracks())
    check(not f['Anna-1'].player.isPlaying(), 'and the wanderer followed it (stopped)')
    check(f.leaders() == ['Anna-3'], 'the operator still leads: %s' % f.leaders())
    f.shutdown()


def t_late_advance_held():
    # The leader is cut off across its track end for 6 s, under zyre's 10 s expiry: libzyre holds
    # the advances and delivers them LATE. Nobody may restart the new track.
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].order('unbuf_playindex', [0])        # 01_intro, 12 s
    time.sleep(9)
    cut(['Anna-1'], ['Anna-2', 'Anna-3'], hold=True)
    time.sleep(6)                                    # the end falls inside the cut: every side advances
    heal()
    time.sleep(4)
    twice = {n.name: n.player.plays.count('02_ambiance_loop.mp3') for n in f.alive()}
    check(all(v == 1 for v in twice.values()), 'each player started 02_ambiance_loop exactly once: %s' % twice)
    check(set(f.tracks().values()) == {'02_ambiance_loop.mp3'}, 'all on it: %s' % f.tracks())
    sp = f.spread(f.leaders()[0]) if f.leaders() else 9
    check(len(f.leaders()) == 1 and sp < 0.1, 'one leader, in sync: %s, spread %.0f ms' % (f.leaders(), sp * 1000))
    f.shutdown()


def t_stale_wanderer_cannot_restart():
    # A player out of range misses the stop; the stop's giver then dies (silent > takeoverAfter);
    # the wanderer comes back still playing (it took its own clock alone): the stopped fleet stays stopped
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-4', 0.998)])
    f['Anna-2'].order('unbuf_playindex', [2])        # 03_story, 90 s
    time.sleep(4)
    cut(['Anna-4'], ['Anna-1', 'Anna-2'])
    time.sleep(1)
    f['Anna-2'].order('stop', None, 300)
    time.sleep(2)
    f['Anna-2'].kill()
    time.sleep(10)
    check(f['Anna-4'].player.isPlaying() and not f['Anna-4'].wc.isLeader(),
          'the wanderer plays on alone, and claims nothing: nobody hears it (#t-089)')
    heal()
    time.sleep(5)
    check(not f['Anna-1'].player.isPlaying(), 'healed: the stopped player stays stopped (%s)' % f.tracks())
    # paused variant: the same with a pause
    f.shutdown()


def t_dark_commander():
    # The commander has no media for its own order (an empty card): it must not lead the fleet
    # into a stop with p=0 beats. The others play on; a playing player takes the clock.
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    n = f['Anna-1']
    n.playlist.files = []                            # an empty media folder
    n.order('unbuf_playindex', [0])
    time.sleep(1.5)
    check(not n.player.isPlaying() and f['Anna-2'].player.isPlaying(), 'the commander is dark, the others play 01_intro')
    time.sleep(8.5)
    check(f['Anna-2'].player.isPlaying() and f['Anna-3'].player.isPlaying(), 'the fleet did NOT stop: %s' % f.tracks())
    check(f.leaders() == ['Anna-2'], 'a playing player took the clock: %s' % f.leaders())
    time.sleep(3)
    sp = f.spread('Anna-2')
    check(sp < 0.1, 'in sync on it: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_duplicate_name():
    # Two cards left as `Anna-0`: neither may lead; they say so; a uniquely named player takes the clock
    f = Fleet([('Anna-0', 1.0), ('Anna-1', 1.002), ('Anna-2', 0.998)])
    orig = f['Anna-0']
    twin = f.add('Anna-0', rate=1.001)
    f.nodes['Anna-0'] = orig                        # keep both in the fleet's view
    f.nodes['Anna-0x'] = twin
    time.sleep(3)
    first = [n for n in ZBUS.members if n.name == 'Anna-0']
    check(len(first) == 2 and all(n.wc.dupName for n in first), 'both Anna-0 see the other: %s' % [n.wc.dupName for n in first])
    first[0].order('unbuf_playindex', [2])
    time.sleep(1.5)
    check(not any(n.wc.isLeader() for n in first), 'a duplicate name never leads, even on its own order')
    t = wait_for(lambda: f['Anna-1'].wc.isLeader() and not f['Anna-2'].wc.isLeader(), 12.0)
    check(t is not None, 'Anna-1 took the clock (%.1f s)' % (t or 0))
    time.sleep(3)
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'every player in sync on it, both Anna-0 included: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_own_channel():
    # role='elected' has its own port/group; and a role='fixed' master heard anyway (a forced shared
    # port) is never a leader for elected players
    hpE = FakeHPlayer(FakePlayer(), FakePlaylist(None, []), FakeZyre('x'))
    e = WallclockInterface(hpE, None, False, player=hpE.player, role='elected', driftLog=None)
    hpF = FakeHPlayer(FakePlayer(), FakePlaylist(None, []), FakeZyre('y'))
    fx = WallclockInterface(hpF, None, False, player=hpF.player, driftLog=None)
    check((e.port, e.group) == (3738, '239.192.0.38') and (fx.port, fx.group) == (3737, '239.192.0.37'),
          'elected on 3738/239.192.0.38, fixed unchanged on 3737/239.192.0.37')
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002)])
    m = Node('WALL-MASTER', role='fixed', master=True, loop=True).start()
    m.player.play('/data/media/03_biennale.mp4')
    time.sleep(4)
    check(f['Anna-1'].wc._rank is None and not f['Anna-1'].player.isPlaying(), 'an elected player ignores a fixed master on its port')
    f.shutdown()


def t_pause_window():
    # The leader adopts the pause's rank, and only then pauses: a packet sent in between says t=T+1, z=0.
    # Widen that instant to 80 ms: followers already paused on the order must stay paused.
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].hp.on('zyre.event')(lambda ev, d=None, *a: time.sleep(0.08) if isinstance(d, dict) and d.get('event') == 'pause' else None)
    f['Anna-1'].order('unbuf_playindex', [2])
    time.sleep(4)
    undone = 0
    for i in range(3):
        f['Anna-1'].order('pause', None, 300)
        time.sleep(0.9)
        undone += sum(1 for x in ('Anna-2', 'Anna-3') if not f[x].player.isPaused())
        f['Anna-1'].order('resume', None, 300)
        time.sleep(2.5)
    check(undone == 0, 'no follower resumed by the leader\'s in-between packet: %d undone over 3 pauses' % undone)
    f.shutdown()


def t_dark_player_stops():
    # A player whose last play hit 'nomedia' (it lacks 05_extra) orders STOP: it must beat p=0, so a
    # wanderer cut off across the stop follows it on the heal instead of restarting the fleet
    f = Fleet([('Anna-1', 1.0), ('Anna-4', 0.998)])
    f.add('Anna-2', rate=1.002, files=FILES[:3])
    f['Anna-1'].order('unbuf_playindex', [4])        # 05_extra: Anna-2 has none
    time.sleep(3)
    check(f['Anna-2'].wc._dark and not f['Anna-2'].player.isPlaying(), 'Anna-2 is dark (no 05_extra)')
    cut(['Anna-4'], ['Anna-1', 'Anna-2'])
    time.sleep(1)
    f['Anna-2'].order('stop', None, 300)
    time.sleep(1.5)
    check(f.emitting() == ['Anna-2'], 'the dark player that ordered the stop leads it with p=0 beats: %s' % f.emitting())
    time.sleep(10)
    heal()
    time.sleep(6)
    check(not any(n.player.isPlaying() for n in f.alive()), 'healed: the stop stands everywhere: %s' % f.tracks())
    check(f.leaders() == ['Anna-2'], 'one leader, the stop\'s: %s' % f.leaders())
    f.shutdown()


def t_longer_cue_file():
    # A video follower's NN_ cue runs 4 s longer than the leader's mp3: the leader's track-end advance
    # is judged against the LEADER's track, so the follower switches with everyone (its tail is cut)
    DUR.update({'01_cue.mp3': 12.0, '01_cue.mp4': 16.0, '02_next.mp3': 60.0, '02_next.mp4': 60.0})
    f = Fleet([('Anna-1', 1.0), ('Anna-3', 0.998)], files=['01_cue.mp3', '02_next.mp3'])
    f.add('Anna-2', rate=1.002, files=['01_cue.mp4', '02_next.mp4'])
    f['Anna-1'].order('unbuf_playindex', [0])
    t0 = time.time(); seen = {}
    while time.time() - t0 < 16 and len(seen) < 3:
        for k, n in f.nodes.items():
            if n.player.track().startswith('02_') and k not in seen:
                seen[k] = time.time() - t0
        time.sleep(0.02)
    check(len(seen) == 3 and max(seen.values()) - min(seen.values()) < 0.3,
          'all three started 02_ together: %s' % {k: round(v, 2) for k, v in seen.items()})
    check(f['Anna-2'].player.plays == ['01_cue.mp4', '02_next.mp4'], 'the video player joined by the advance, not late: %s' % f['Anna-2'].player.plays)
    f.shutdown()


def t_fallback_skew():
    # The leader dies 3 s before a track end: every follower sends a fallback advance. With clock
    # shifts a few ms off, Anna-1 and Anna-3 execute each other's FIRST: the dropped one's rank must
    # still count, so the fleet elects ONE leader (the best rank) at once, not after an 8 s takeover
    real = ZShim.preProcessor1
    def skewed(self, data):
        if 'at' in data and data.get('a') is not None and {self.node.name, data.get('from')} == {'Anna-1', 'Anna-3'}:
            data['at'] -= 40000                     # 40 ms early, between Anna-1 and Anna-3 only
        real(self, data)
    ZShim.preProcessor1 = skewed
    try:
        f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
        f['Anna-2'].order('unbuf_playindex', [0])    # 01_intro, 12 s
        wait_for(lambda: 8.5 < f['Anna-2'].player.position() < 9.5, 12)
        f['Anna-2'].kill()
        t = wait_for(lambda: f['Anna-1'].player.track() == '02_ambiance_loop.mp3', 6.0)
        check(t is not None, 'the followers advanced on their own')
        time.sleep(1.5)
        ranks = {k: n.wc._rank for k, n in f.nodes.items() if n.alive}
        check(f.leaders() == ['Anna-1'] and f.emitting() == ['Anna-1'],
              'one leader at once, the best rank: leaders %s emitting %s ranks %s' % (f.leaders(), f.emitting(), ranks))
        f.shutdown()
    finally:
        ZShim.preProcessor1 = real


def t_dark_into_stopped():
    # Stopped by Anna-2, Anna-2 then gone; an empty-card commander orders play and never speaks;
    # Anna-4 missed that order: a playing player takes the clock at 8 s and Anna-4 joins it
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.003), ('Anna-3', 0.997), ('Anna-4', 1.0)])
    f['Anna-2'].order('unbuf_playindex', [2]); time.sleep(3)
    f['Anna-2'].order('stop', None, 300); time.sleep(3)
    f['Anna-2'].kill(); time.sleep(1)
    f['Anna-1'].playlist.files = []
    ZBUS.drop['Anna-4'] = 1
    f['Anna-1'].order('unbuf_playindex', [2])        # 03_story, 90 s
    t = wait_for(lambda: f['Anna-3'].wc.isLeader(), 12.0)
    check(t is not None and 7.0 < t < 10.5, 'Anna-3 (playing) took the clock after %.1f s' % (t or 0))
    t = wait_for(lambda: f['Anna-4'].player.track() == '03_story.mp3', 6.0)
    check(t is not None, 'Anna-4, which missed the order, joined it')
    time.sleep(4)
    sp = f.spread('Anna-3')
    check(sp < 0.1, 'in sync: spread %.0f ms' % (sp * 1000))
    f.shutdown()



def t_stop_track():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.002), ('Anna-3', 0.998)])
    f['Anna-1'].order('unbuf_playindex', [3])        # 04_final_stop, 8 s
    time.sleep(1)
    n0 = len(ZBUS.orders)
    t = wait_for(lambda: not any(n.player.isPlaying() for n in f.alive()), 10.0)
    check(t is not None, "'_stop' track ended: everyone stopped")
    time.sleep(2)
    check(len(ZBUS.orders) == n0, 'and nobody ordered anything: %s' % [(o[1], o[2], o[3]) for o in ZBUS.orders[n0:]])
    check(f.leaders() == ['Anna-1'], 'Anna-1 still leads the stopped fleet')
    f.shutdown()



def _record_ticks(node, ref):
    """Wrap a follower's Drifter.tick: every servo step records (when, the servo's diff, the TRUE
    offset ref - node from both players' exact timelines, locked, speed). + = the follower is late."""
    d = node.wc.drifter
    orig = d.tick
    samples = []
    def tick(clock, duration=0):
        res = orig(clock, duration)
        if res and not res.get('jumped'):
            with ref.player.lock, node.player.lock:
                true = ref.player._now() - node.player._now()
            samples.append((time.time(), res['diff'], true, res['locked'], res['speed']))
        return res
    d.tick = tick
    return samples


def t_cached_position():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.0)], mpvLike=True)
    a, b = f['Anna-1'], f['Anna-2']
    samples = _record_ticks(b, a)
    a.order('unbuf_playindex', [2])                     # 03_story, 90 s: both start at the same `at`
    check(wait_for(lambda: f.leaders() == ['Anna-1'], 2.0) is not None, 'order from Anna-1 -> Anna-1 leads')
    time.sleep(8)
    t0 = time.time()
    time.sleep(6)
    win = [x for x in samples if x[0] >= t0]
    check(len(win) > 40, '%d servo ticks on Anna-2 in a 6 s window' % len(win))
    bias = statistics.median([x[1] - x[2] for x in win])
    check(abs(bias) < 0.008,
          "the servo's diff IS the true offset: median bias %+.1f ms (mpv-like cached position)" % (bias * 1000))
    off = statistics.median([x[2] for x in win])
    check(abs(off) < 0.030, 'fresh start: Anna-2 on the leader, true offset %+.1f ms' % (off * 1000))
    f.shutdown()


def t_fixed_cached_position():
    # hplayer2#t-097: the role='fixed' follower (the Biennale walls) compares like with like too.
    # The fixed master stamps `at` on its time-pos event exactly like the elected leader, so a
    # follower that reads its own cached position un-aged parks ~half an event interval ahead.
    Fleet([])
    DUR['loop.mp4'] = 60.0
    m = Node('WALL-MASTER', role='fixed', master=True, loop=True, mpvLike=True).start()
    s = Node('WALL-SLAVE', role='fixed', master=False, loop=True, mpvLike=True).start()
    samples = _record_ticks(s, m)
    m.player.play('/data/media/loop.mp4'); s.player.play('/data/media/loop.mp4')
    time.sleep(8)
    t0 = time.time()
    time.sleep(6)
    win = [x for x in samples if x[0] >= t0]
    check(len(win) > 40, '%d servo ticks on WALL-SLAVE in a 6 s window' % len(win))
    bias = statistics.median([x[1] - x[2] for x in win])
    check(abs(bias) < 0.008,
          "fixed: the servo's diff IS the true offset: median bias %+.1f ms (mpv-like cached position)"
          % (bias * 1000))
    off = statistics.median([x[2] for x in win])
    check(abs(off) < 0.030, 'fixed: WALL-SLAVE on the master, true offset %+.1f ms' % (off * 1000))
    m.kill(); s.kill(); time.sleep(0.4)


def t_tight_deadzone_join():
    f = Fleet([('Anna-1', 1.0), ('Anna-2', 1.0001)], mpvLike=True)
    a, b = f['Anna-1'], f['Anna-2']
    for n in (a, b):                                    # what 26-anna sets after addInterface
        n.wc.drifter.deadZoneEnter, n.wc.drifter.deadZoneExit = 0.010, 0.030
    samples = _record_ticks(b, a)
    a.order('unbuf_playindex', [2])
    time.sleep(4)
    ZBUS.drop['Anna-2'] = 1                             # Anna-2 misses the next order: it JOINs
    a.order('unbuf_playindex', [4])
    t = wait_for(lambda: b.player.track() == '05_extra.mp3', 8.0)
    check(t is not None, 'Anna-2 missed the order and joined 05_extra from the packets (%.1f s)' % (t or 0))
    time.sleep(12)                                      # the JUMP, its landing, the servo
    t0 = time.time()
    time.sleep(8)
    win = [x for x in samples if x[0] >= t0]
    check(len(win) > 60, '%d servo ticks on Anna-2 in an 8 s window' % len(win))
    true = [x[2] for x in win]
    off = statistics.median(true)
    check(abs(off) < 0.020 and max(abs(v) for v in true) < 0.040,
          'joined Anna-2 sits on the leader: true offset median %+.1f ms, worst %.1f ms'
          % (off * 1000, max(abs(v) for v in true) * 1000))
    flips = sum(1 for i in range(1, len(win)) if win[i][3] != win[i - 1][3])
    tail = [x for x in win if x[0] >= t0 + 5.0]
    locked = sum(1 for x in tail if x[3]) / float(len(tail) or 1)
    check(flips <= 4 and locked >= 0.95,
          'dead zone 10/30 ms holds without hunting: %d lock flips in 8 s, locked %.0f%% of the last 3 s'
          % (flips, locked * 100))
    f.shutdown()


# ── #t-089: takeover requires company ────────────────────────────────────────────────────────
def cut_all(names):
    """The router dies: nobody hears anybody (clock, presence, zyre orders)."""
    for x in names:
        for y in names:
            if x != y:
                BUS.cut.add((x, y)); ZBUS.cut.add((x, y))


def _ranks(f):
    return {n.name: n.wc._rank for n in f.alive()}


def anna_zone(f):
    """The dead zone 26-anna sets after addInterface (10/30 ms), on every node."""
    for n in f.nodes.values():
        n.wc.drifter.deadZoneEnter, n.wc.drifter.deadZoneExit = 0.010, 0.030
    return f


def watch_leaders(f, step=0.1):
    """Background sampler: (time, name) of every node seen leading. Stop it with the event."""
    seen, stop = [], threading.Event()
    def loop():
        while not stop.wait(step):
            for n in f.alive():
                if n.wc.isLeader():
                    seen.append((time.time(), n.name))
    threading.Thread(target=loop, daemon=True).start()
    return seen, stop


def t_lone_roamer():
    # Bench 2026-11-06: Anna-12, out of range both ways for 25 s, took over at 8 s ALONE; back in
    # range, the whole fleet re-locked on it. Alone, a follower claims nothing: it plays on, on its
    # model of the leader, and re-aligns on the leader the fleet kept.
    f = anna_zone(Fleet([('Anna-1', 0.999), ('Anna-2', 1.002), ('Anna-3', 1.0), ('Anna-4', 0.998), ('Anna-5', 1.001)]))
    f['Anna-3'].order('unbuf_playindex', [2])        # 03_story, 90 s
    time.sleep(5)
    check(f.leaders() == ['Anna-3'], 'Anna-3 leads')
    r0 = f['Anna-3'].wc._rank
    R = f['Anna-1']                                  # the lowest name: it would win every tie
    others = [k for k in f.nodes if k != 'Anna-1']
    seen, stop = watch_leaders(f)
    t0 = time.time()
    cut(['Anna-1'], others)
    time.sleep(25)
    check(R.player.track() == '03_story.mp3' and R.player.isPlaying(), 'cut off 25 s, Anna-1 plays on (on its model of Anna-3)')
    check(R.wc._rank == r0, 'and claimed nothing alone: its rank is still %s (%s)' % (r0, R.wc._rank))
    with R.player.lock, f['Anna-3'].player.lock:
        off = f['Anna-3'].player._now() - R.player._now()
    check(abs(off) < 0.05, 'free-running on its model, it stayed on the leader alone: true offset %+.0f ms' % (off * 1000))
    heal()
    time.sleep(6)
    stop.set()
    led = sorted(set(n for _, n in seen))
    check(led == ['Anna-3'], 'the fleet kept its leader through the cut and the return: ever led %s' % led)
    check(all(r == r0 for r in _ranks(f).values()), 'no rank moved anywhere: %s' % _ranks(f))
    check(f.emitting() == ['Anna-3'], 'one emitter: %s' % f.emitting())
    moved = {k: len([x for x in f[k].player.seekLog if x[2] > t0]) for k in others}
    check(not any(moved.values()), 'only the roamer re-aligns: no seek on the others %s' % moved)
    sp = f.spread('Anna-3')
    check(sp < 0.1, 'Anna-1 back in sync: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_roamer_track_end():
    # Out of range across a track end, for less than the takeover (6 s): alone, it moves on by
    # itself. An advance ORDER made alone is a rank, and the lower name wins the tie with the
    # leader's own advance: back in range, the fleet would re-lock on the roamer.
    f = anna_zone(Fleet([('Anna-1', 0.999), ('Anna-2', 1.0), ('Anna-3', 1.002)]))
    f['Anna-2'].order('unbuf_playindex', [0])        # 01_intro, 12 s
    t = wait_for(lambda: 8.5 < f['Anna-2'].player.position() < 9.0, 12.0)
    check(t is not None, 'the leader 3 s from the end of 01_intro')
    n0 = len(ZBUS.orders)
    cut(['Anna-1'], ['Anna-2', 'Anna-3'])
    time.sleep(6)                                    # the end falls inside the cut
    R = f['Anna-1']
    check(R.localAdvances == 1 and R.player.track() == '02_ambiance_loop.mp3',
          'alone at the track end, Anna-1 moved on by itself (%d local, on %s)' % (R.localAdvances, R.player.track()))
    byR = [(o[1], o[2], o[3], o[4]) for o in ZBUS.orders[n0:] if o[1] == 'Anna-1']
    check(not byR, 'with no order, so no rank: %s' % byR)
    heal()
    time.sleep(5)
    check(f.leaders() == ['Anna-2'], 'back in range, the fleet kept its leader: %s' % f.leaders())
    sp = f.spread('Anna-2')
    check(set(f.tracks().values()) == {'02_ambiance_loop.mp3'} and sp < 0.05,
          'and Anna-1 re-aligned on it: %s, spread %.0f ms' % (f.tracks(), sp * 1000))
    f.shutdown()


def t_roaming_leader():
    # The LEADER walks out of range: the group that lost it hears itself, so it takes over at ~8 s
    # (lowest name). Cut off, the old leader needs no company to keep its role: it emits on. Back,
    # it yields to the takeover's higher sub.
    f = anna_zone(Fleet([('Anna-1', 0.999), ('Anna-2', 1.002), ('Anna-3', 1.0), ('Anna-4', 0.998), ('Anna-5', 1.001)]))
    f['Anna-3'].order('unbuf_playindex', [2])        # 03_story, 90 s
    time.sleep(5)
    r0 = f['Anna-3'].wc._rank
    cut(['Anna-3'], [k for k in f.nodes if k != 'Anna-3'])
    t = wait_for(lambda: f['Anna-1'].wc.isLeader(), 14.0)
    check(t is not None and 7.0 < t < 11.0, 'the group took over after %.1f s (company: it hears itself)' % (t or 0))
    time.sleep(2)
    check(f.leaders() == ['Anna-1', 'Anna-3'], 'the group converged on Anna-1; cut off, Anna-3 still leads itself: %s' % f.leaders())
    check(f.emitting() == ['Anna-1', 'Anna-3'], 'and emits on, alone: %s' % f.emitting())
    r1 = f['Anna-2'].wc._rank
    check(r1 == (r0[0], r0[1] + 1, 'Anna-1'), 'the takeover kept the term, bumped the sub: %s' % (r1,))
    time.sleep(8)
    heal()
    t = wait_for(lambda: f.leaders() == ['Anna-1'], 3.0)
    check(t is not None, 'back in range, Anna-3 yielded to the higher sub (%.1f s): %s' % (t or 0, f.leaders()))
    time.sleep(5)
    check(f.emitting() == ['Anna-1'], 'one emitter: %s' % f.emitting())
    sp = f.spread('Anna-1')
    check(sp < 0.1, 'one show again: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_router_dead():
    # The router dies: everybody is alone. Nobody claims; every player plays on (the followers on
    # their model, the leader on its own clock, emitting on); the track ends inside the outage move
    # each player on by itself (the leader with orders nobody hears, the others with none). Back,
    # everyone follows the one that still emits.
    names = ['Anna-1', 'Anna-2', 'Anna-3', 'Anna-4']
    f = anna_zone(Fleet([('Anna-1', 0.999), ('Anna-2', 1.0), ('Anna-3', 1.002), ('Anna-4', 0.998)]))
    f['Anna-2'].order('unbuf_playindex', [0])        # 01_intro, 12 s, then 02_ambiance_loop (8 s, loops)
    time.sleep(4)
    r0 = f['Anna-2'].wc._rank
    seen, stop = watch_leaders(f)
    n0 = len(ZBUS.orders)
    cut_all(names)
    time.sleep(20)                                   # the end of 01_intro and a replay of 02, inside
    led = sorted(set(n for _, n in seen))
    check(led == ['Anna-2'], 'nobody claimed alone: only the leader ever led (%s)' % led)
    check(all(f[k].wc._rank == r0 for k in names if k != 'Anna-2'), 'no follower rank moved: %s' % _ranks(f))
    check('Anna-2' in f.emitting(), 'the isolated leader emitted on: %s' % f.emitting())
    byF = [(o[1], o[2], o[3]) for o in ZBUS.orders[n0:] if o[1] != 'Anna-2']
    check(not byF, 'no follower ordered anything: %s' % byF)
    loc = {k: f[k].localAdvances for k in names}
    check(all(loc[k] >= 1 for k in names if k != 'Anna-2') and loc['Anna-2'] == 0,
          'each follower moved on by itself, the leader by its orders: %s' % loc)
    check(set(f.tracks().values()) == {'02_ambiance_loop.mp3'}, 'everyone on 02_ambiance_loop: %s' % f.tracks())
    heal()
    time.sleep(6)
    stop.set()
    check(f.leaders() == ['Anna-2'] and f.emitting() == ['Anna-2'],
          'back: the one that still emits leads: %s / %s' % (f.leaders(), f.emitting()))
    rk = _ranks(f)
    check(len(set(rk.values())) == 1, 'one rank everywhere: %s' % rk)
    sp = f.spread('Anna-2')
    check(sp < 0.1, 'one show again: spread %.0f ms' % (sp * 1000))
    f.shutdown()


def t_edge_flapping():
    # A player at the edge of range: 10 s out, 5 s in, five times (each cut past the 8 s takeover).
    # It must never become the clock. The last return is ragged: for 1.5 s it hears the others'
    # presence but not the leader's clock (inside the 2 s company hold).
    f = anna_zone(Fleet([('Anna-1', 0.999), ('Anna-2', 1.0), ('Anna-3', 1.002), ('Anna-4', 0.998)]))
    f['Anna-2'].order('unbuf_playindex', [2])        # 03_story, 90 s
    time.sleep(4)
    r0 = f['Anna-2'].wc._rank
    others = ['Anna-2', 'Anna-3', 'Anna-4']
    seen, stop = watch_leaders(f)
    for k in range(5):
        cut(['Anna-1'], others)
        time.sleep(10)
        if k == 4:
            BUS.heal(); ZBUS.cut.clear()
            BUS.clockCut.add(('Anna-2', 'Anna-1'))
            time.sleep(1.5)
            BUS.clockCut.clear()
        else:
            heal()
        time.sleep(5)
    stop.set()
    led = sorted(set(n for _, n in seen))
    check(led == ['Anna-2'], 'five flaps and a ragged return: only Anna-2 ever led (%s)' % led)
    check(all(r == r0 for r in _ranks(f).values()), 'no rank moved anywhere: %s' % _ranks(f))
    sp = f.spread('Anna-2')
    check(sp < 0.1, 'Anna-1 in sync after its last return: spread %.0f ms' % (sp * 1000))
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
    ('slow file open: no model tick drives the new track', t_slow_open),
    ('fires, not received: the old leader leads through the order\'s buffer', t_order_fires_not_received),
    ('reboot while stopped: the rebooted leader\'s lower-term order is followed', t_reboot_while_stopped),
    ('restart within takeoverAfter: no reclaim, takeover at ~8 s, it follows', t_restart_within_takeover),
    ("'_stop' track in a fleet: everyone stops, nobody orders", t_stop_track),
    ('missed stop with no TimeClient: followed before the clock-shift gate', t_stop_without_timeclient),
    ('wanderer: its track-end advances never undo the operator\'s stop', t_wanderer_cannot_undo_stop),
    ('late advances: held across a track end, delivered late, nobody restarts', t_late_advance_held),
    ('stale wanderer: back after the stop\'s giver died, it restarts nobody', t_stale_wanderer_cannot_restart),
    ('dark commander: no media for its own order, the fleet plays on', t_dark_commander),
    ('duplicate name: neither Anna-0 leads, a unique one takes the clock', t_duplicate_name),
    ('own channel: elected port/group; a fixed master is never a leader', t_own_channel),
    ('pause window: the leader\'s in-between packet resumes nobody', t_pause_window),
    ('dark player orders stop: it beats p=0, the stop stands on the heal', t_dark_player_stops),
    ('longer NN_ cue on a follower: it switches with the fleet', t_longer_cue_file),
    ('fallback advances in a different order per node: one leader at once', t_fallback_skew),
    ('dark commander into a stopped fleet, its leader gone: a player takes over', t_dark_into_stopped),
    ('mpv-like cached position: the follower servo compares like with like', t_cached_position),
    ('fixed mpv-like cached position: the fixed slave compares like with like', t_fixed_cached_position),
    ('mpv-like join with a 10/30 ms dead zone: on the leader, no hunting', t_tight_deadzone_join),
    ('lone roamer (#t-089): out 25 s, it claims nothing; the fleet keeps its leader', t_lone_roamer),
    ('lone roamer across a track end: it moves on by itself, no order, no rank', t_roamer_track_end),
    ('roaming leader: the group takes over, the leader emits on alone, yields back', t_roaming_leader),
    ('router dead: everyone alone, nobody claims; back, all follow the emitter', t_router_dead),
    ('edge flapping 10 s out / 5 s in x5 + a ragged return: never the clock', t_edge_flapping),
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
