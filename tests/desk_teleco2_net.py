"""
Teleco2 network transport desk test (hplayer2#t-090): the CoreS3 remote on WiFi, player side.

The REAL Teleco2Interface (core/interfaces/teleco2.py) with netport/probeport on free localhost
ports, a fake hplayer (player status, playlist, settings, zyre peers, wallclock leadership), and
plain sockets playing a fw 6 remote: UDP "find" -> "here", a TCP session speaking protocol v1.
USB is never opened (the serial filter matches nothing); the USB session is driven directly.

USB unchanged: the same script of events is played into the da75d1c teleco2.py (from git) and into
this one, with the clock pinned: the lines queued for the USB port must be identical.

    .venv/bin/python -u tests/desk_teleco2_net.py
"""
import sys, os, types, json, time, socket, subprocess, importlib.util, threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
ni.interfaces = lambda: []
ni.ifaddresses = lambda iface: {}
sys.modules['netifaces'] = ni

from core.engine import network
real_get_rssi = network.get_rssi
network.get_hostname = lambda: 'Anna-07'
network.get_ip = lambda iface=None: '10.8.0.107'
network.get_essid = lambda iface=None: 'pisync'
network.get_rssi = lambda iface=None: 72

import core.module as _module
LOG = []
def _log(self, *argv):
    LOG.append(' '.join(str(a) for a in argv))
_module.Module.log = _log

from core.module import Module
from core.interfaces import teleco2 as T

ok = 0
def check(cond, msg):
    global ok
    if not cond:
        print('   FAIL: ' + msg)
        print('   --- log ---')
        for l in LOG[-30:]:
            print('   | ' + l)
        sys.stdout.flush()
        os._exit(1)
    ok += 1
    print('   ok  ' + msg)


# ─── fake hplayer ────────────────────────────────────────────────────────────────────────────
class Player():
    def __init__(self): self.st = {'isPaused': False, 'isPlaying': True, 'media': '/data/media/03_story.mp3', 'time': 42.4, 'duration': 180.0}
    def status(self): return dict(self.st)
    def isPaused(self): return self.st['isPaused']
    def isPlaying(self): return self.st['isPlaying']

class Playlist():
    def __init__(self): self.items = ['/data/media/%02d_track%s.mp3' % (k + 1, 'é' if k == 2 else '') for k in range(11)]
    def index(self): return 2
    def size(self): return len(self.items)
    def export(self): return list(self.items)

class Settings():
    def __init__(self): self.v = {'volume': 80, 'mute': False, 'loop': -1}
    def get(self, k): return self.v.get(k)

class Peer():
    def __init__(self, name, ip, link): self.name, self.ip, self.link = name, ip, link

class Zyre():
    def peersList(self): return {1: Peer('Anna-07', '127.0.0.1', 3), 2: Peer('Anna-03', '10.8.0.103', 3), 3: Peer('Anna-11', '10.8.0.111', 1)}
    def activeCount(self): return 3

class Wallclock():
    lead = True
    def isLeader(self): return self.lead

class HP(Module):
    def __init__(self):
        super().__init__(None, 'HPlayer2', 'green')
        self.player = Player(); self.playlist = Playlist(); self.settings = Settings()
        self.ifaces = {'zyre': Zyre(), 'wallclock': Wallclock()}
        self.events = []
        self.on('teleco2.*')(lambda ev, *a: self.events.append((ev, a)))
    def activePlayer(self): return self.player
    def interface(self, name): return self.ifaces.get(name)
    def autoBind(self, m): pass


def free_port(kind):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Remote():
    """A fw 6 remote over TCP: line reader on a thread."""
    def __init__(self, port, chip='CHIPA'):
        self.s = socket.create_connection(('127.0.0.1', port), timeout=2)
        self.chip = chip
        self.lines = []
        self.eof = False
        self.lock = threading.Lock()
        threading.Thread(target=self._rx, daemon=True).start()
    def _rx(self):
        buf = b''
        while True:
            try:
                d = self.s.recv(4096)
            except OSError:
                d = b''
            if not d:
                self.eof = True
                return
            buf += d
            while b'\n' in buf:
                l, buf = buf.split(b'\n', 1)
                with self.lock:
                    self.lines.append(json.loads(l.decode()))
    def say(self, line):
        self.s.sendall((line + '\n').encode())
    def types(self):
        with self.lock:
            return [m['t'] for m in self.lines]
    def of(self, t):
        with self.lock:
            return [m for m in self.lines if m['t'] == t]
    def close(self):
        self.s.close()


def wait(pred, timeout, step=0.05):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(step)
    return False


def find(probeport, timeout=1.0):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.settimeout(timeout)
    u.sendto(b'find 1 6 CHIPA', ('127.0.0.1', probeport))
    try:
        d, _ = u.recvfrom(512)
        return json.loads(d.decode())
    except socket.timeout:
        return None
    finally:
        u.close()


# ─── 0. the signal is a percentage (0..100), whatever iw says ────────────────────────────────
print('== network.get_rssi: a percentage, capped ==')
_which, _out = network.shutil.which, network.subprocess.check_output
network.shutil.which = lambda c: '/usr/sbin/iw'
try:
    got = {}
    for dbm in (-13, -40, -60, -85, -95):
        network.subprocess.check_output = lambda cmd, stderr=None, d=dbm: ('Connected to aa:bb\n\tsignal: %d dBm\n' % d).encode()
        got[dbm] = real_get_rssi('wint')
    network.subprocess.check_output = lambda cmd, stderr=None: b'Not connected.\n'
    got['none'] = real_get_rssi('wint')
finally:
    network.shutil.which, network.subprocess.check_output = _which, _out
check(got == {-13: 100, -40: 100, -60: 56, -85: 0, -95: 0, 'none': 0},
      'next to the router (-13 dBm) reads 100, not 160; -60 -> 56; out of range / not connected -> 0: %s' % got)


# ─── 1. the USB path is byte-identical to da75d1c's ──────────────────────────────────────────
def load_old():
    src = subprocess.run(['git', '-C', REPO, 'show', 'da75d1c:core/interfaces/teleco2.py'],
                         capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader('core.interfaces.teleco2_da75d1c', loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = 'core.interfaces'
    mod.__file__ = os.path.join(REPO, 'core', 'interfaces', 'teleco2.py')
    exec(compile(src, 'teleco2@da75d1c', 'exec'), mod.__dict__)
    return mod


def usb_script(mod):
    """Play one USB story into a teleco2 module with a pinned clock; return the queued lines."""
    clock = [1000.0]
    real = mod.time.time
    mod.time.time = lambda: clock[0]
    try:
        hp = HP()
        itf = mod.Teleco2Interface(hp, False, 'wint', filter='^NOMATCH-desk$')
        itf._fwBin = None                       # no flash on the desk
        out = []
        def drain():
            while not itf._txQueue.empty():
                out.append(itf._txQueue.get_nowait())
        itf.onConnect(); itf.tick(); drain()                 # silent until hello
        clock[0] += 1; itf.onLine('hello 1 5'); drain()      # v5 remote: full dump
        clock[0] += 0.2; hp.emit('status'); itf.tick(); drain()
        clock[0] += 0.4; hp.player.st['time'] = 43.6; hp.emit('status'); itf.tick(); drain()
        hp.player.st['isPlaying'] = False; hp.emit('player.stopped'); itf.tick(); drain()
        hp.settings.v['volume'] = 70; hp.emit('settings.updated'); itf.tick(); drain()
        hp.emit('playlist.updated'); itf.tick(); drain()
        hp.emit('zyre.peer.link'); clock[0] += 1.1; itf.tick(); drain()
        for _ in range(5):
            clock[0] += 0.7; itf.tick(); drain()             # net keepalive cadence
        itf.onLine('next'); itf.onLine('playindex 4'); itf.onLine('playindex x'); itf.onLine('junk')
        itf.onLine('getall'); drain()
        clock[0] += 12; itf.onDisconnect(); itf.onConnect(); clock[0] += 10.5; itf.tick(); drain()   # no hello: dump at 10 s
        hp.emit('app-closing'); drain()
        return out, list(hp.events)
    finally:
        mod.time.time = real


print('== USB: the same lines, in the same order, as da75d1c ==')
old_out, old_ev = usb_script(load_old())
new_out, new_ev = usb_script(T)
check(len(old_out) >= 25, 'the story queued %d USB lines on da75d1c' % len(old_out))
check(new_out == old_out, 'USB lines identical (%d) — a v6 player with a v5 remote behaves as today' % len(new_out))
check(new_ev == old_ev and ('teleco2.remote-next', ()) in new_ev and ('teleco2.remote-playindex', (4,)) in new_ev,
      'the same remote-* events: %s' % [e[0] for e in new_ev])


# ─── 2. the network transport ────────────────────────────────────────────────────────────────
print('== network: discovery, session, heartbeat, dedupe, battery ==')
tcp, udp = free_port(socket.SOCK_STREAM), free_port(socket.SOCK_DGRAM)
hp = HP()
itf = T.Teleco2Interface(hp, False, 'wint', filter='^NOMATCH-desk$', netport=tcp, probeport=udp)
fwCalls = []
realFw = itf._fwCheck
itf._fwCheck = lambda fw: fwCalls.append(fw) or False
itf.start()
check(wait(lambda: any('network remote: tcp' in l for l in LOG), 2.0), 'the net thread listens: tcp %d + udp %d' % (tcp, udp))

h = find(udp)
check(h is not None and h['t'] == 'here' and h['nm'] == 'Anna-07' and h['port'] == tcp and h['lead'] == 1
      and h['rssi'] == 72 and 'fw' in h, 'find -> here: %s' % h)
hp.ifaces['wallclock'].lead = False
h = find(udp)
check(h and h['lead'] == 0, 'a follower answers lead 0: %s' % h)
del hp.ifaces['wallclock']
h = find(udp)
check(h and h['lead'] == 0, 'no wallclock interface: lead 0')
u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); u.settimeout(0.5)
u.sendto(b'hi there', ('127.0.0.1', udp))
try:
    u.recvfrom(512); answered = True
except socket.timeout:
    answered = False
u.close()
check(not answered, 'anything but "find" gets no answer')

r = Remote(tcp)
time.sleep(0.3)
check(r.types() == [], 'connected: the player waits for the hello (as on USB)')
r.say('hello 1 6 CHIPA')
check(wait(lambda: 'peers' in r.types(), 2.0), 'hello -> full dump')
ty = r.types()
check(ty[:4] == ['hello', 'vol', 'st', 'net'] and ty.count('list') == 2,
      'dump order hello/vol/st/net + 11 media in 2 chunks: %s' % ty)
check(r.of('list')[0]['items'][2] == '03_tracke', 'media names ascii-folded, as on USB: %s' % r.of('list')[0]['items'][2])
check(fwCalls == [], 'no auto-flash check over TCP (fw 6 hello): %s' % fwCalls)

n0 = len(r.of('net'))
for _ in range(3):
    time.sleep(1.0); r.say('hb')
n1 = len(r.of('net'))
check(n1 - n0 >= 2 and not r.eof, 'heartbeat: %d net lines in 3 s (1 s cadence), session alive on hb' % (n1 - n0))

r.say('next'); r.say('playindex 5'); r.say('playindex x'); r.say('volup')
check(wait(lambda: ('teleco2.remote-volup', ()) in hp.events, 1.0), 'commands over TCP become the same remote-* events')
check(('teleco2.remote-next', ()) in hp.events and ('teleco2.remote-playindex', (5,)) in hp.events
      and not any(e[0] == 'teleco2.remote-playindex' and e[1] == () for e in hp.events), 'bad args dropped')

k = len(r.of('st'))
hp.player.st['isPaused'] = True; hp.emit('player.paused')
check(wait(lambda: len(r.of('st')) > k, 1.0) and r.of('st')[-1]['pl'] == 2, 'a transition is pushed at once (st pl=2)')

LOG.clear()
for line in ('bat 80 0', 'bat 75 0', 'bat 69 0', 'bat 69 1', 'bat x'):
    r.say(line)
time.sleep(0.4)
bl = [l for l in LOG if 'battery' in l]
check(len(bl) == 3 and '80%' in bl[0] and '69%' in bl[1] and 'charging' in bl[2],
      'battery logged on a 10-point move or a charge change: %s' % bl)

r2 = Remote(tcp, 'CHIPB')
r2.say('hello 1 6 CHIPB')
check(wait(lambda: 'peers' in r2.types(), 2.0), 'a second remote gets its own session and dump')
r2.say('stop')
check(wait(lambda: ('teleco2.remote-stop', ()) in hp.events, 1.0), 'and its orders count too')

# remote A plugs into our USB: its TCP session is a ghost
itf.usb.onLine('hello 1 6 CHIPA')
check(wait(lambda: r.eof, 1.5), 'remote CHIPA on our USB: its TCP session is closed')
check(fwCalls == [6], 'the USB hello (and only it) went through the auto-flash check: %s' % fwCalls)
check(not r2.eof, 'remote CHIPB untouched')
itf.serial = object()                       # USB "connected" with CHIPA on it
r3 = Remote(tcp, 'CHIPA')
r3.say('hello 1 6 CHIPA')
check(wait(lambda: r3.eof, 1.5) and 'peers' not in r3.types(), 'CHIPA over TCP while it is on our USB: refused, no dump')
itf.serial = None

# half-open: a remote that stops talking
LOG.clear()
t0 = time.time()
check(wait(lambda: r2.eof, 6.0), 'remote CHIPB silent: session closed after %.1f s (dead at %.1f s)' % (time.time() - t0, T.NET_DEAD))
check(any('silent' in l for l in LOG), 'logged as silent (half-open or gone)')

# bye on shutdown
r4 = Remote(tcp, 'CHIPC'); r4.say('hello 1 6 CHIPC')
wait(lambda: 'peers' in r4.types(), 2.0)
hp.emit('app-closing')
check(wait(lambda: 'bye' in r4.types(), 1.5), 'app-closing: bye to every session')
itf.quit(join=False)
check(wait(lambda: r4.eof, 2.0), 'player stopping: sessions closed')

print('\nALL %d CHECKS PASSED' % ok)
sys.stdout.flush()
os._exit(0)
