"""http2's pages load ALIVE in a real browser — the check `node --check` cannot be (#t-048).

#t-042 and #t-043 each left a statement without its `;` right before one of script.js's panel
IIFEs `(function(){…})()`. Valid syntax — `node --check` passes it — but ASI joins the two into
a call, `$(...).on(...) is not a function` is thrown at document-ready, and every panel below it
(radar, nowde, schedule, dmx) silently never registers its socket handlers. It shipped twice
before an eye on player-000 caught it (fixed 4510939).

So each page is loaded here the way an operator opens it: the REAL http2 server on a free port,
on stub players, and a headless Chromium driven over the DevTools protocol. A page fails on ANY
uncaught exception, console.error or failed resource load, and must prove its ready handler ran
to its LAST panel (`window.dmxEdit`) with the socket's `config` applied (`#playerName`).

DevTools, never `--dump-dom`: `--dump-dom` does not return on a page holding a live socket —
every http2 page — so a naive check hangs instead of failing. Every wait here has a deadline.

No Chromium on the box → skipped, saying so; `HPLAYER_SMOKE_BROWSER=<path>` picks one.
"""
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request

import pytest
import simple_websocket

import core.interfaces.http2 as http2
from core.engine.settings import Settings
from core.module import EventEmitterX

NAME = 'smoke-player'
PAGES = ['full', 'simple', 'mini']

# the ready handler's LAST panel (the DMX IIFE) defines it: typeof 'function' = it ran to the end
PROBE = """(function() {
    var n = document.getElementById('playerName');
    return { ready: document.readyState,
             lastPanel: typeof window.dmxEdit,
             name: n ? n.textContent.trim() : null };
})()"""


#
# Stub player: the real http2 interface, server and Settings around it
#
class Player:
    def status(self, key=None):
        st = {'isReady': True, 'isPlaying': True, 'isPaused': False,
              'media': '/media/clip.mp4', 'time': 12.5, 'duration': 60.0, 'speed': 1.0}
        return st.get(key) if key else st

    def hasSurface(self):          # True: the profile-gated cards render too
        return True

    def hasBrightness(self):
        return True


class Files:
    def __init__(self, root):
        self.root_paths = [root]

    def validExt(self, filename):
        return True

    def refresh(self):
        pass


class HPlayer(EventEmitterX):
    def __init__(self, root):
        super().__init__(wildcard=True, delimiter='.')
        self.files = Files(root)
        self.player = Player()
        self.settings = Settings(self)

    def hostname(self):
        return NAME

    def isRPi(self):
        return False

    def autoBind(self, module):
        pass

    def players(self):
        return [self.player]

    def playlist(self):
        return [os.path.join(self.files.root_paths[0], 'clip.mp4')]

    def interface(self, name):
        return None


def freePort():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def waitHttp(url, deadline, proc=None):
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.read()
        except OSError:
            if proc is not None and proc.poll() is not None:
                raise RuntimeError('exited with code %s' % proc.returncode)
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


@pytest.fixture(scope='module')
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp('media')
    (root / 'clip.mp4').write_bytes(b'')
    (root / 'loops').mkdir()
    (root / 'loops' / 'idle.mov').write_bytes(b'')

    hplayer = HPlayer(str(root))
    # the REAL interface, so config() resolves its gates as on a player; its listen() is NOT
    # started (it advertises on the LAN) — the server is, as listen() would
    iface = http2.Http2Interface(hplayer, 0)
    port = freePort()
    http2.ThreadedHTTPServer(iface, port).start()
    base = 'http://127.0.0.1:%d' % port
    waitHttp(base + '/style.css', time.monotonic() + 10)
    return base


#
# Headless Chromium over the DevTools protocol
#
def findBrowser():
    env = os.environ.get('HPLAYER_SMOKE_BROWSER')
    if env:
        return env
    for name in ('chrome-headless-shell', 'chromium', 'chromium-browser',
                 'google-chrome-stable', 'google-chrome'):
        path = shutil.which(name)
        if path:
            return path
    # a Playwright download, newest first
    cache = os.path.expanduser('~/.cache/ms-playwright')
    for pattern in ('chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell',
                    'chromium-*/chrome-linux64/chrome'):
        found = glob.glob(os.path.join(cache, pattern))
        found.sort(key=lambda p: [int(n) for n in re.findall(r'\d+', p)], reverse=True)
        if found:
            return found[0]
    return None


@pytest.fixture(scope='module')
def browser(tmp_path_factory):
    exe = findBrowser()
    if not exe:
        pytest.skip('no Chromium found (PATH, ~/.cache/ms-playwright): '
                    'set HPLAYER_SMOKE_BROWSER=<path> to run the http2 page smoke check')

    if '/snap/' in os.path.realpath(exe) or exe.startswith('/snap/'):
        # snap confinement refuses a profile under /tmp
        profile = os.path.expanduser('~/snap/chromium/common/hplayer2-smoke-%d' % os.getpid())
    else:
        profile = str(tmp_path_factory.mktemp('chromium-profile'))
    errlog = tmp_path_factory.mktemp('chromium-log') / 'stderr.log'

    port = freePort()
    args = [exe, '--disable-gpu', '--no-first-run', '--no-default-browser-check',
            '--no-sandbox', '--remote-debugging-port=%d' % port, '--remote-allow-origins=*',
            '--user-data-dir=' + profile, 'about:blank']
    if 'headless-shell' not in os.path.basename(exe):
        args.insert(1, '--headless=new')

    with open(errlog, 'wb') as err:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=err)
    devtools = 'http://127.0.0.1:%d' % port
    try:
        waitHttp(devtools + '/json/version', time.monotonic() + 20, proc)
    except Exception as e:
        proc.kill()
        proc.wait(timeout=10)
        tail = errlog.read_text(errors='replace')[-1500:]
        pytest.fail('%s never answered DevTools (%s):\n%s' % (exe, e, tail))

    yield devtools

    proc.kill()
    proc.wait(timeout=10)
    if profile.startswith(os.path.expanduser('~/snap/')):
        shutil.rmtree(profile, ignore_errors=True)


class Tab:
    """One fresh /json/new tab; every DevTools event received is kept in `events`."""

    def __init__(self, devtools):
        req = urllib.request.Request(devtools + '/json/new?about:blank', method='PUT')
        with urllib.request.urlopen(req, timeout=5) as r:
            target = json.loads(r.read())
        self.devtools, self.id = devtools, target['id']
        self.ws = simple_websocket.Client.connect(target['webSocketDebuggerUrl'])
        self.lastId = 0
        self.events = []

    def close(self):
        try:
            self.ws.close()
        finally:
            try:
                urllib.request.urlopen(self.devtools + '/json/close/' + self.id, timeout=5).read()
            except OSError:
                pass

    def _recv(self, deadline):
        left = deadline - time.monotonic()
        raw = self.ws.receive(timeout=left) if left > 0 else None
        if raw is None:
            raise TimeoutError
        msg = json.loads(raw)
        if 'method' in msg:
            self.events.append(msg)
        return msg

    def call(self, method, timeout=10, **params):
        self.lastId += 1
        mid = self.lastId
        self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params}))
        deadline = time.monotonic() + timeout
        while True:
            msg = self._recv(deadline)
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise AssertionError('%s: %s' % (method, msg['error']))
                return msg.get('result', {})

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        try:
            while True:
                self._recv(deadline)
        except TimeoutError:
            pass

    def evaluate(self, expression):
        res = self.call('Runtime.evaluate', expression=expression, returnByValue=True)
        return res.get('result', {}).get('value')

    def errors(self):
        out = []
        for ev in self.events:
            m, p = ev['method'], ev.get('params', {})
            if m == 'Runtime.exceptionThrown':
                d = p.get('exceptionDetails', {})
                desc = (d.get('exception') or {}).get('description') or d.get('text')
                out.append('uncaught: %s (%s:%s)' % (desc, d.get('url', '?'), d.get('lineNumber')))
            elif m == 'Runtime.consoleAPICalled' and p.get('type') in ('error', 'assert'):
                args = [a.get('value', a.get('description', '')) for a in p.get('args', [])]
                out.append('console.%s: %s' % (p['type'], ' '.join(str(a) for a in args)))
            elif m == 'Log.entryAdded' and p.get('entry', {}).get('level') == 'error':
                e = p['entry']
                out.append('%s: %s %s' % (e.get('source'), e.get('text'), e.get('url', '')))
        return out


@pytest.mark.parametrize('page', PAGES)
def test_page_loads_alive(server, browser, page):
    tab = Tab(browser)
    try:
        for domain in ('Runtime', 'Log', 'Page'):
            tab.call(domain + '.enable')
        nav = tab.call('Page.navigate', url='%s/%s' % (server, page))
        assert not nav.get('errorText'), nav

        # the page is alive once its ready handler reached its last panel and the socket
        # delivered `config` — or it never will; a throw already says which, no need to wait
        deadline = time.monotonic() + 20
        state = None
        while time.monotonic() < deadline:
            state = tab.evaluate(PROBE)
            if tab.errors() or (state and state['ready'] == 'complete'
                                and state['lastPanel'] == 'function' and state['name'] == NAME):
                break
            tab.pump(0.25)

        # let the live socket feed it a while: status at 10 Hz, files, settings, playlist
        tab.pump(1.5)
        errors = tab.errors()

        assert not errors, '/%s threw in the browser:\n  %s' % (page, '\n  '.join(errors))
        assert state and state['lastPanel'] == 'function', \
            "/%s: script.js's ready handler never reached its last panel: %s" % (page, state)
        assert state['name'] == NAME, \
            '/%s: the socket never applied `config` (#playerName): %s' % (page, state)
    finally:
        tab.close()
