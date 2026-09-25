"""
Zyre storm desk test (2026-09-25, after Kouagou01-64 ran out of threads during kouagou03's
link-flap storm). REAL zyre/czmq over loopback, two processes:

  A ("MASTER"): one ZyreNode, left alone, watched: thread count, time-server answers
  B ("FLAPPER"): rebuilds its node N times in a row (new uuid each time = EXIT + ENTER + JOIN
                 on A), then stays up and must get a clock sync from A

    .venv/bin/python tests/desk_zyre_storm.py [rebuilds=40] [iface=lo]

Prints A's thread count before/peak/after and B's clock-sync result; exit 1 on a failure.
"""
import sys, os, time, threading, subprocess, functools

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
print = functools.partial(print, flush=True)


class FakeHP():
    def __init__(self, name): self._n = name
    def hostname(self): return self._n


class FakeIface():
    def __init__(self, name):
        self.hplayer = FakeHP(name)
        self.stopped = threading.Event()
        self.events = []
    def log(self, *a):
        pass
    def emit(self, ev, *a):
        self.events.append(ev)


def threads():
    return len(os.listdir('/proc/self/task'))


def isolate():
    """Beacon on a private UDP port (15670): safe to run on a live player, whose own node beacons
    on 5670 — the test's nodes never meet it. ZyreNode calls set_interval before start()."""
    import core.interfaces.zyre as zm
    orig = zm.Zyre.set_interval
    def set_interval(self, i):
        self.set_port(15670)
        return orig(self, i)
    zm.Zyre.set_interval = set_interval


def run_master(iface, seconds):
    isolate()
    from core.interfaces.zyre import ZyreNode
    fi = FakeIface('MASTER')
    node = ZyreNode(fi, iface)
    node.subscribe(['status'])
    base = threads()
    peak = base
    t0 = time.time()
    while time.time() - t0 < seconds:
        time.sleep(0.05)
        peak = max(peak, threads())
    time.sleep(1)
    print('MASTER threads base=%d peak=%d end=%d book=%d' % (base, peak, threads(), len(node.book)))
    fi.stopped.set()
    os._exit(0)


def run_flapper(iface, rebuilds):
    isolate()
    from core.interfaces.zyre import ZyreNode
    fi = FakeIface('FLAPPER')
    time.sleep(2)
    node = None
    for i in range(rebuilds):
        node = ZyreNode(fi, iface)
        node.subscribe(['status'])
        time.sleep(0.3)
        node.stop()
    node = ZyreNode(fi, iface)
    node.subscribe(['status'])
    ok = False
    t0 = time.time()
    while time.time() - t0 < 30:
        p = node.peerByName('MASTER')
        tc = p and p.timeclient
        if tc and tc.status == 1:
            ok = True
            break
        time.sleep(0.2)
    print('FLAPPER clock sync with MASTER after storm: %s (%.1f s)' % ('OK' if ok else 'NONE', time.time() - t0))
    fi.stopped.set()
    os._exit(0 if ok else 1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('master', 'flapper'):
        role, iface, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
        if role == 'master':
            run_master(iface, n)
        else:
            run_flapper(iface, n)
    rebuilds = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    iface = sys.argv[2] if len(sys.argv) > 2 else 'lo'
    dur = 2 + rebuilds * 0.45 + 40
    m = subprocess.Popen([sys.executable, __file__, 'master', iface, str(int(dur))], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    f = subprocess.Popen([sys.executable, __file__, 'flapper', iface, str(rebuilds)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    fo, _ = f.communicate()
    mo, _ = m.communicate()
    keep = lambda o: [l for l in o.splitlines() if l.startswith(('MASTER', 'FLAPPER', 'Traceback', 'RuntimeError', 'AttributeError', 'Exception', '  File', '    '))]
    for l in keep(mo) + keep(fo):
        print(l)
    sys.exit(f.returncode)
