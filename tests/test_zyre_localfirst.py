"""A sync master obeys its own page even when its network is gone (hplayer2#t-067).

In sync mode the profile rebinds the page's play/pause/resume/stop to a zyre broadcast, and the
master used to act on it only through shout(): send to the peers, then ask zyre_own_groups()
whether we are in the group, then deliver to ourself. Both calls go through the zyre actor. On a
master cut off from its network (dongle reset, interface gone, node mid-rebuild) a call that
fails or never returns left the master deaf to its own page while http2 kept serving it
(KOUAGOU/TAUPAKI, Lyon 2026-09-18). broadcast(localFirst=True) delivers to self first, without
touching zyre, then sends to the peers.

No czmq/zyre here: the bindings are replaced by fakes, and the zyre handle can be made to fail
or to hang.
"""
import ast, json, os, threading, time, types

import pytest

import core.interfaces.zyre as zyremod

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeSock:
    def endpoint(self):
        return b'tcp://0.0.0.0:49152'

    def send(self, *a):
        pass

    def __del__(self):
        pass


class FakeZsock:
    @staticmethod
    def new_xpub(ep):
        return FakeSock()

    @staticmethod
    def new_rep(ep):
        return FakeSock()

    @staticmethod
    def set_sndtimeo(s, v):
        pass


class FakeZactor:
    def __init__(self, fn, arg):
        self._sock = FakeSock()

    def sock(self):
        return self._sock


class FakePoller:
    def __init__(self, *a):
        pass

    def wait(self, ms):
        time.sleep(ms / 1000.0)
        return None


class FakeZlist:
    def __init__(self, items):
        self.items = [i.encode() for i in items]

    def pop(self):
        return self.items.pop(0) if self.items else None


class FakeZyre:
    """The zyre handle. `mode`: 'ok' | 'fail' (every actor call raises) | 'hang' (shouts and
    own_groups block until released) — the three states of a master's network."""
    mode = 'ok'

    def __init__(self, _):
        self.shouted = []
        self.release = threading.Event()
        self.destroyed = False
        self.touchedDead = False

    def set_interface(self, *a):
        pass
    set_name = set_header = set_interval = set_interface
    set_evasive_timeout = set_silent_timeout = set_expired_timeout = set_interface

    def start(self):
        pass

    def name(self):
        return b'master'

    def uuid(self):
        return 'SELF-UUID'

    def join(self, g):
        pass

    def _actor(self):
        if self.destroyed:
            self.touchedDead = True     # the real handle is freed: libzyre aborts, no `except` saves it
            raise AssertionError('zyre call on a destroyed handle')
        if FakeZyre.mode == 'fail':
            raise OSError('zyre actor gone')
        if FakeZyre.mode == 'hang':
            self.release.wait(5)

    def shouts(self, group, data):
        self._actor()
        self.shouted.append((group, json.loads(data.decode())))

    def own_groups(self):
        self._actor()
        return FakeZlist(['broadcast', 'sync'])

    def __del__(self):
        self.destroyed = True


class Iface:
    """The ZyreInterface as the node sees it: emit() is what the engine's handlers receive."""
    def __init__(self):
        self.stopped = threading.Event()
        self.hplayer = types.SimpleNamespace(hostname=lambda: 'master')
        self.got = []           # (event, args) delivered to this player
        self.planned = []
        self.logs = []
        self.raiseOn = None

    def log(self, *a):
        self.logs.append(' '.join(str(x) for x in a))

    def emit(self, ev, *args):
        if ev == 'planned':
            self.planned.append(args[0])
            return
        if ev == 'event' or ev.startswith('peer.'):
            return                  # the raw message, and the self-peer's link state at boot
        if ev == self.raiseOn:
            raise RuntimeError('handler blew up')
        self.got.append((ev, list(args)))


@pytest.fixture
def node(monkeypatch):
    monkeypatch.setattr(zyremod, 'Zyre', FakeZyre)
    monkeypatch.setattr(zyremod, 'Zsock', FakeZsock)
    monkeypatch.setattr(zyremod, 'Zactor', FakeZactor)
    monkeypatch.setattr(zyremod, 'zactor_fn', lambda f: f)
    monkeypatch.setattr(zyremod, 'Zpoller', FakePoller)
    monkeypatch.setattr(zyremod, 'ZyreEvent', type('FakeZyreEvent', (), {}))
    FakeZyre.mode = 'ok'
    iface = Iface()
    n = zyremod.ZyreNode(iface, 'wlan0')
    yield n
    n.zyre.release.set()
    iface.stopped.set()
    n._tsStop = True


def wait_for(cond, timeout=1.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


# ── the defect, as it stands on the plain path ────────────────────────────────

def test_plain_broadcast_leaves_a_cut_off_master_deaf(node):
    FakeZyre.mode = 'fail'
    with pytest.raises(OSError):
        node.broadcast('stop')
    assert node.interface.got == []


def test_plain_broadcast_hangs_before_the_master_obeys(node):
    FakeZyre.mode = 'hang'
    t = threading.Thread(target=node.broadcast, args=('stop',), daemon=True)
    t.start()
    time.sleep(0.2)
    assert t.is_alive() and node.interface.got == []


# ── local first ───────────────────────────────────────────────────────────────

def test_local_first_obeys_once_and_sends_once_on_a_healthy_network(node):
    node.broadcast('stop', localFirst=True)
    assert node.interface.got == [('stop', [])]
    assert [(g, d['event']) for g, d in node.zyre.shouted] == [(b'broadcast', 'stop')]


def test_local_first_obeys_when_every_zyre_call_fails(node):
    FakeZyre.mode = 'fail'
    node.broadcast('stop', localFirst=True)
    assert node.interface.got == [('stop', [])]
    assert any('not sent to peers' in l for l in node.interface.logs)


def test_local_first_obeys_before_a_hanging_zyre_returns(node):
    FakeZyre.mode = 'hang'
    t = threading.Thread(target=node.broadcast, args=('stop',), kwargs={'localFirst': True},
                         daemon=True)
    t.start()
    assert wait_for(lambda: node.interface.got == [('stop', [])])
    assert t.is_alive()                     # the send is still stuck: the master did not wait for it
    node.zyre.release.set()
    t.join(2)
    assert [d['event'] for _, d in node.zyre.shouted] == ['stop']


def test_a_synchronised_play_keeps_one_instant_for_self_and_peers(node):
    node.broadcast('play', ['/data/media/01_wall.mp4'], 200, localFirst=True)
    assert len(node.interface.planned) == 1 and len(node.zyre.shouted) == 1
    assert node.interface.planned[0]['at'] == node.zyre.shouted[0][1]['at']
    assert node.interface.got == []         # programmed, not played yet
    assert wait_for(lambda: node.interface.got == [('play', ['/data/media/01_wall.mp4'])])


def test_a_synchronised_play_still_fires_locally_with_the_network_gone(node):
    FakeZyre.mode = 'fail'
    node.broadcast('play', ['/data/media/01_wall.mp4'], 200, localFirst=True)
    assert wait_for(lambda: node.interface.got == [('play', ['/data/media/01_wall.mp4'])])


def test_a_local_handler_error_does_not_cost_the_peers_their_command(node):
    node.interface.raiseOn = 'stop'
    node.broadcast('stop', localFirst=True)
    assert [d['event'] for _, d in node.zyre.shouted] == ['stop']


def test_a_closed_node_handles_locally_and_never_touches_the_destroyed_handle(node):
    node.done = True                        # actor already gone: stop() skips its 1 s wait
    node.stop()
    assert node.closed and node.zyre.destroyed
    node.broadcast('stop', localFirst=True)
    assert node.interface.got == [('stop', [])]
    assert node.zyre.shouted == []
    assert not node.zyre.touchedDead


# ── the Lyon profile takes the local-first path ───────────────────────────────

def test_the_biennale_profile_broadcasts_local_first():
    src = open(os.path.join(REPO, 'profiles', 'biennale.py')).read()
    fn = next(f for f in ast.walk(ast.parse(src))
              if isinstance(f, ast.FunctionDef) and f.name == 'zbroadcast')
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Attribute) and c.func.attr == 'broadcast']
    assert calls, 'zbroadcast no longer calls node.broadcast'
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert 'localFirst' in kw and getattr(kw['localFirst'], 'value', None) is True
