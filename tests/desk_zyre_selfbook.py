"""
The REAL ZyreNode books ITSELF under our own name (zyre.py: `self.book[self.uuid] = Peer(...)`).
The desk fleets fake zyre; this one runs the real ZyreNode.__init__ (only the czmq/zyre C bindings
are stubbed) under a real WallclockInterface(role='elected'): a player with a UNIQUE name must not
think its name is taken, and must lead after its own order (37projects-e2's review of e7d48a6).

    /tmp/wallsync-venv/bin/python tests/desk_zyre_selfbook.py
"""
import sys, os, types, threading, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
ni.interfaces = lambda: []; ni.ifaddresses = lambda i: {}
sys.modules['netifaces'] = ni

from core.interfaces import zyre as Z
from core.interfaces.wallclock import WallclockInterface
from core.engine import network

class FakeSockObj:
    def endpoint(self): return b'tcp://0.0.0.0:49152'
class FakeZsock:
    @staticmethod
    def new_xpub(ep): return FakeSockObj()
    @staticmethod
    def new_rep(ep): return FakeSockObj()
    @staticmethod
    def set_sndtimeo(s, v): pass
class FakeZyreLib:
    def __init__(self, x): self._name = b'?'
    def set_interface(self, i): pass
    def set_name(self, n): self._name = n
    def name(self): return self._name
    def set_header(self, k, v): pass
    def set_interval(self, v): pass
    def set_evasive_timeout(self, v): pass
    def set_silent_timeout(self, v): pass
    def set_expired_timeout(self, v): pass
    def start(self): pass
    def uuid(self): return 'SELF-UUID'
    def join(self, g): pass
class FakeZactor:
    def __init__(self, fn, arg): pass
    def sock(self): return None
class FakeZpoller:
    def __init__(self, *a): pass
    def wait(self, ms): time.sleep(ms / 1000.0); return None
Z.Zyre = FakeZyreLib; Z.Zsock = FakeZsock; Z.Zactor = FakeZactor; Z.zactor_fn = lambda f: f
Z.Zpoller = FakeZpoller
Z.ZyreEvent = type('FakeZyreEvent', (), {})

class Iface:
    def __init__(self):
        self.stopped = threading.Event()
        self.hplayer = types.SimpleNamespace(hostname=network.get_hostname)
    def log(self, *a): pass
    def emit(self, *a): pass

node = Z.ZyreNode(Iface(), 'wint')

class P:
    name = 'player'
    def isPlaying(self): return True
    def isPaused(self): return False
    def status(self, k=None): return None
    def position(self): return 0.0
class HP:
    def players(self): return [P()]
    def on(self, ev):
        return lambda f: f
    def interface(self, name): return types.SimpleNamespace(node=node) if name == 'zyre' else None
    def autoBind(self, m): pass

ok = 0
def check(cond, msg):
    global ok
    if not cond:
        print('   FAIL: ' + msg); sys.stdout.flush(); os._exit(1)
    ok += 1
    print('   ok  ' + msg)

print('== the real ZyreNode books itself: a unique name is not a duplicate ==')
selfs = [p for k, p in node.book.items() if k == node.uuid]
check(selfs and selfs[0].name == network.get_hostname(), 'the real book holds this node under our own name: %s' %
      {k: p.name for k, p in node.book.items()})
wc = WallclockInterface(HP(), 'wint', role='elected', driftLog=None)
wc.log = lambda *a: None
check(wc._myName == network.get_hostname(), 'wallclock and zyre share the name')
wc._checkDupName()
check(not wc.dupName, 'alone on the network: our name is NOT taken')
wc._adopt((1, 0, wc._myName), 'order playindex')
check(wc.isLeader(), 'and our own order makes us the leader')

class Twin:
    name = network.get_hostname(); active = True; ip = '10.8.0.99'
node.book['TWIN-UUID'] = Twin()
wc._dupCheckAt = 0
wc._checkDupName()
check(wc.dupName and not wc.isLeader(), 'a second card with our name: taken, and we step down')
print('\nALL %d CHECKS PASSED' % ok)
sys.stdout.flush()
os._exit(0)
