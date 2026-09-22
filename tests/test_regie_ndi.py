"""NDI discovery in the Regie interface: which nodes get asked, and what the union does
when one of them is missing, slow, or not walked at all this tick.

No network, no player, no flask: the two methods are called on a bare instance with a
stub hplayer, exactly as the interface calls them from listen()'s thread.
"""
import json, threading, queue, urllib.request

import core.interfaces.regie as regie


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def fakeUrlopen(answers, calls=None):
    """answers: base URL -> list of source names, or an Exception to raise"""
    def urlopen(url, timeout=None):
        base = url[:-len('/sources')]
        if calls is not None:
            calls.append(base)
        answer = answers.get(base)
        if answer is None or isinstance(answer, Exception):
            raise answer or ConnectionRefusedError(base)
        return FakeResponse([{'name': n} for n in answer])
    return urlopen


class FakeServer:
    def __init__(self):
        self.sendBuffer = queue.Queue()


class FakePeer:
    def __init__(self, ip, active=True):
        self.ip, self.active = ip, active


def regieStub(peers=(), server=None):
    iface = regie.RegieInterface.__new__(regie.RegieInterface)
    iface._ndi_sources, iface._ndi_seen, iface._ndi_cursor, iface._ndi_miss = [], {}, 0, False
    iface._server = server
    iface.stopped = threading.Event()
    iface.log = lambda *a: None

    class Node:
        book = {str(i): p for i, p in enumerate(peers)}

    class Zyre:
        node = Node()

    class HPlayer:
        def interface(self, name):
            return Zyre() if name == 'zyre' and peers else None

    iface.hplayer = HPlayer()
    return iface


def test_ndi_nodes_from_the_boot_file(tmp_path, monkeypatch):
    f = tmp_path / 'ndi-nodes.txt'
    f.write_text('# the two minis\n\n10.0.0.11\n10.0.0.12:9000\n')
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', str(f))
    # the file wins over discovery, and a host without a port gets the default one
    assert regieStub(peers=[FakePeer('10.0.0.99')]).ndiNodes() == \
        ['http://10.0.0.11:8791', 'http://10.0.0.12:9000']


def test_ndi_nodes_falls_back_to_self_and_active_peers(monkeypatch):
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', '/nonexistent/ndi-nodes.txt')
    peers = [FakePeer('127.0.0.1'),            # self's own book entry: de-duped
             FakePeer('10.0.0.11'),
             FakePeer('10.0.0.12', active=False)]   # gone: not asked
    assert regieStub(peers=peers).ndiNodes() == ['http://127.0.0.1:8791', 'http://10.0.0.11:8791']
    assert regieStub().ndiNodes() == ['http://127.0.0.1:8791']   # no zyre at all: still works


def test_poll_unions_the_fleet_and_pushes_once(monkeypatch):
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', '/nonexistent/ndi-nodes.txt')
    monkeypatch.setattr(urllib.request, 'urlopen', fakeUrlopen({
        'http://127.0.0.1:8791': [],                 # the Regie's own box: no node
        'http://10.0.0.11:8791': ['KMINI-1 (cam)'],
        'http://10.0.0.12:8791': ['KMINI-2 (cam)', 'KMINI-1 (cam)'],   # dup across nodes
    }))
    server = FakeServer()
    iface = regieStub(peers=[FakePeer('10.0.0.11'), FakePeer('10.0.0.12')], server=server)
    iface.pollNdiSources()
    assert iface._ndi_sources == ['KMINI-1 (cam)', 'KMINI-2 (cam)']
    assert server.sendBuffer.get_nowait() == ('data', {'ndiSources': iface._ndi_sources})
    iface.pollNdiSources()                           # unchanged: nothing pushed
    assert server.sendBuffer.empty()


def test_a_dead_node_only_drops_its_own_sources(monkeypatch):
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', '/nonexistent/ndi-nodes.txt')
    answers = {'http://127.0.0.1:8791': [],
               'http://10.0.0.11:8791': ['KMINI-1 (cam)'],
               'http://10.0.0.12:8791': ['KMINI-2 (cam)']}
    monkeypatch.setattr(urllib.request, 'urlopen', fakeUrlopen(answers))
    iface = regieStub(peers=[FakePeer('10.0.0.11'), FakePeer('10.0.0.12')])
    iface.pollNdiSources()
    assert iface._ndi_sources == ['KMINI-1 (cam)', 'KMINI-2 (cam)']
    answers['http://10.0.0.12:8791'] = TimeoutError('mini rebooting')
    iface.pollNdiSources()
    assert iface._ndi_sources == ['KMINI-1 (cam)']


def test_one_empty_sweep_does_not_blank_the_picker(monkeypatch):
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', '/nonexistent/ndi-nodes.txt')
    answers = {'http://10.0.0.11:8791': ['KMINI-1 (cam)']}
    monkeypatch.setattr(urllib.request, 'urlopen', fakeUrlopen(answers))
    iface = regieStub(peers=[FakePeer('10.0.0.11')])
    iface.pollNdiSources()
    assert iface._ndi_sources == ['KMINI-1 (cam)']
    answers['http://10.0.0.11:8791'] = TimeoutError('one slow answer')
    iface.pollNdiSources()
    assert iface._ndi_sources == ['KMINI-1 (cam)']   # held: one miss proves nothing
    iface.pollNdiSources()
    assert iface._ndi_sources == []                  # two in a row agree: the source is gone


def test_a_truncated_sweep_resumes_at_the_next_tick(monkeypatch):
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', '/nonexistent/ndi-nodes.txt')
    monkeypatch.setattr(regie, 'NDI_SWEEP_S', -1)    # budget spent: one node per tick
    calls = []
    monkeypatch.setattr(urllib.request, 'urlopen', fakeUrlopen({
        'http://127.0.0.1:8791': ['LOCAL (cam)'],
        'http://10.0.0.11:8791': ['KMINI-1 (cam)'],
    }, calls))
    iface = regieStub(peers=[FakePeer('10.0.0.11')])
    iface.pollNdiSources()
    assert calls == ['http://127.0.0.1:8791'] and iface._ndi_sources == ['LOCAL (cam)']
    iface.pollNdiSources()                           # the next tick walks the one left behind,
    assert calls[-1] == 'http://10.0.0.11:8791'      # and the first node's answer is kept
    assert iface._ndi_sources == ['LOCAL (cam)', 'KMINI-1 (cam)']


def test_a_stopping_interface_abandons_the_sweep(monkeypatch):
    monkeypatch.setattr(regie, 'NDI_NODES_FILE', '/nonexistent/ndi-nodes.txt')
    calls = []
    monkeypatch.setattr(urllib.request, 'urlopen', fakeUrlopen({
        'http://127.0.0.1:8791': [], 'http://10.0.0.11:8791': [], 'http://10.0.0.12:8791': [],
    }, calls))
    iface = regieStub(peers=[FakePeer('10.0.0.11'), FakePeer('10.0.0.12')])
    iface.stopped.set()
    iface.pollNdiSources()
    assert calls == ['http://127.0.0.1:8791']        # shutdown waits for one host, never N
