"""The socket.io send queues of http2 and Regie drain from boot, browsed or not.

Both servers queue what their interface sends (http2's `sendQueue`, the Regie's `sendBuffer`)
and empty it from a background task. That task used to start on the first browser connect,
so a player whose page nobody opened kept every message since boot: the DMX level meter
alone (5 Hz, ~886 B a frame) grew it ~16 MB/h (#t-080).

The REAL server classes run here on a free port, on stub interfaces, with no client at all.
"""
import os, queue, socket, threading, time

import core.interfaces.http2 as http2
import core.interfaces.regie as regie


class Events:
    def __init__(self):
        self.handlers = {}

    def on(self, name):
        def deco(f):
            self.handlers.setdefault(name, []).append(f)
            return f
        return deco

    def emit(self, name, *args):
        for f in self.handlers.get(name, []):
            f(name, *args)


class Player:
    def status(self):
        return {'media': None, 'time': 0}


class Files:
    root_paths = ['/tmp']

    def __call__(self):
        return []


class HPlayer(Events):
    files = Files()

    def players(self):
        return [Player()]

    def settings(self):
        return {}

    def playlist(self):
        return []


class Http2Stub(Events):
    def __init__(self):
        super().__init__()
        self.hplayer = HPlayer()

    def config(self):
        return {'name': 'stub', 'page': 'full'}

    def log(self, *args):
        pass


class RegieStub(Events):
    def __init__(self, datapath):
        super().__init__()
        self.hplayer = HPlayer()
        self._datapath = datapath
        self._ndi_sources = []
        self._latency = 0

    def projectPath(self):
        return os.path.join(self._datapath, 'project.json')

    def projectRaw(self):
        return '{"pool":[], "project":[[]]}'

    def reload(self):
        pass

    def log(self, *args):
        pass


def freePort():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def drained(q, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if q.empty():
            return True
        time.sleep(0.05)
    return q.empty()


def test_http2_drains_with_no_browser():
    iface = Http2Stub()
    server = http2.ThreadedHTTPServer(iface, freePort())
    server.start()
    for n in range(200):
        iface.emit('do-socketio', 'dmx-levels', {'active': True, 'levels': {1: n % 256}})
    assert drained(server.sendQueue), f'{server.sendQueue.qsize()} messages still queued'


def test_regie_drains_with_no_browser(tmp_path):
    iface = RegieStub(str(tmp_path))
    server = regie.ThreadedHTTPServer(iface, freePort())
    server.start()
    try:
        for n in range(200):
            iface.hplayer.emit('files.dirlist-updated')
        assert drained(server.sendBuffer), f'{server.sendBuffer.qsize()} messages still queued'
    finally:
        server.stop()
