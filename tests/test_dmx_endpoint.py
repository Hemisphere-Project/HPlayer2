"""http2's GET /dmx: the live DMX state as JSON, for a script or curl in the field (#t-059).

The page's meter gets `dmx-status`/`dmx-levels` over socket.io, which a stock Python client
only joins with `requests` installed, and a player's own venv has none. The endpoint serves
the same two messages over plain HTTP.

The REAL http2 server runs on a free port and the REAL DmxInterface pumps frames into a fake
serial from a sidecar conduite, against a fake player clock. No adapter, no browser.
"""
import json, os, socket, time, urllib.error, urllib.request

import core.interfaces.http2 as http2
from core.interfaces.dmx import DmxInterface
from core.module import EventEmitterX


class Settings:
    def __init__(self):
        self._settings = {}

    def get(self, k):
        return self._settings.get(k)

    def __call__(self):
        return dict(self._settings)


class Player:
    def __init__(self):
        self.media, self.t, self.playing = None, 0.0, False

    def status(self, key=None):
        st = {'media': self.media, 'time': self.t}
        return st.get(key) if key else st

    def position(self):
        return self.t

    def isPlaying(self):
        return self.playing


class Files:
    root_paths = ['/tmp']


class HPlayer(EventEmitterX):
    # EventEmitterX like production: emit() prepends the event name, the handlers rely on it
    files = Files()

    def __init__(self):
        super().__init__(wildcard=True, delimiter='.')
        self.settings = Settings()
        self.player = Player()
        self._interfaces = {}

    def players(self):
        return [self.player]

    def playlist(self):
        return []

    def interface(self, name):
        return self._interfaces.get(name)

    def autoBind(self, module):
        pass


class Http2Stub(EventEmitterX):
    def __init__(self, hplayer):
        super().__init__(wildcard=True, delimiter='.')
        self.hplayer = hplayer

    def config(self):
        return {'name': 'stub', 'page': 'full'}

    def send(self, event, message):     # Http2Interface.send, verbatim
        self.emit('do-socketio', event, message)

    def log(self, *args):
        pass


class FakeSerial:
    def __init__(self):
        self.break_condition = False

    def write(self, b):
        pass

    def flush(self):
        pass

    def close(self):
        pass


def freePort():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def serve(hplayer):
    iface = Http2Stub(hplayer)
    hplayer._interfaces['http2'] = iface
    port = freePort()
    http2.ThreadedHTTPServer(iface, port).start()
    return 'http://127.0.0.1:%d/dmx' % port


def get(url, timeout=5.0):
    deadline = time.time() + timeout
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
        except (ConnectionError, urllib.error.URLError):
            if time.time() > deadline:      # server thread still binding
                raise
            time.sleep(0.05)


def test_dmx_levels_follow_the_conduite(tmp_path):
    hp = HPlayer()
    url = serve(hp)
    dmx = DmxInterface(hp)
    hp._interfaces['dmx'] = dmx

    media = str(tmp_path / 'vague.mp4')
    open(media, 'w').close()
    (tmp_path / 'vague.dmx').write_text("def wash 1-2\n0:00 wash@0 3@255\n0:10 wash@100 fade 10\n")

    status, body = get(url)
    assert status == 200 and body == {'status': None, 'levels': None}     # nothing pumped yet

    # an adapter on the link, as _connect leaves it
    dmx.serial, dmx.port = FakeSerial(), '/dev/ttyUSB0'
    dmx._openProto, dmx._openFilter = 'open', dmx.filter
    hp.player.media, hp.player.playing = media, True

    hp.player.t = 0.0
    dmx._pump()
    status, body = get(url)
    assert status == 200
    assert body['status']['connected'] is True and body['status']['port'] == '/dev/ttyUSB0'
    assert body['status']['media'] == media and body['status']['channels'] == [1, 2, 3]
    assert body['levels'] == {'active': True, 'levels': {'1': 0, '2': 0, '3': 255}}

    hp.player.t = 20.0
    dmx._lastLevelsEmit = 0                 # past the meter's 5 Hz throttle
    dmx._pump()
    _, body = get(url)
    assert body['levels']['levels'] == {'1': 100, '2': 100, '3': 255}

    dmx._drop()                             # adapter gone: no frame is live any more
    _, body = get(url)
    assert body['status']['connected'] is False and body['levels'] is None


def test_dmx_404_without_a_dmx_interface():
    url = serve(HPlayer())
    status, body = get(url)
    assert status == 404 and 'error' in body
