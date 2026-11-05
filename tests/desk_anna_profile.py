"""
Smoke test of profiles/26-anna.py (anna-players#t-017) with no hardware: the profile runs
against a stub HPlayer2 (players, interfaces and playlist are recording fakes; hplayer.run()
returns at once), then its handlers are fired and what they order is checked:

 - the interfaces it builds: health(restart=False) first, zyre + wallclock(role='elected') on `wint`
 - keypad / numpad / CoreS3 remote -> wallclock.order(...) with the 300 ms buffer on transport
   orders, none on volume; keylock gates the keypad, not the remote
 - zyre orders -> playlist; track end -> ONE advance decided by name, only when mayAdvance()
 - fresh settings file -> loop -1 + volume 95 at app-run
 - keypad LCD: the short-name clamp (hplayer2#t-083) and the leader `*`

    /tmp/wallsync-venv/bin/python tests/desk_anna_profile.py      (termcolor + pymitter)
"""
import sys, os, types, runpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
ni.interfaces = lambda: []
ni.ifaddresses = lambda iface: {}
sys.modules['netifaces'] = ni

from core.engine import network
network.has_interface = lambda iface: iface == 'wint'
network.get_essid = lambda iface: 'pisync' if iface == 'wint' else None
network.get_rssi = lambda iface: 70


class Emitter():
    def __init__(self): self.h = {}; self.emitted = []
    def on(self, ev, fn=None):
        def reg(f):
            self.h.setdefault(ev, []).append(f)
            return f
        return reg(fn) if fn else reg
    def emit(self, ev, *args):
        self.emitted.append((ev, args))
        for f in list(self.h.get(ev, [])):
            f(ev, *args)


class Player():
    def __init__(self):
        self.playing = False; self.paused = False; self.pos = 0.0
        self.media = None
    def isPlaying(self): return self.playing or self.paused
    def isPaused(self): return self.paused
    def position(self): return self.pos
    def status(self, k=None):
        s = {'media': self.media}
        return s[k] if k else s


class Playlist(Emitter):
    def __init__(self):
        super().__init__()
        self.items = []; self._index = -1
    def load(self, items): self.items = list(items)
    def size(self): return len(self.items)
    def index(self): return self._index
    def trackAtIndex(self, k): return self.items[k] if 0 <= k < len(self.items) else None
    def nextIndex(self): return min(self._index + 1, len(self.items) - 1)
    def prevIndex(self): return max(self._index - 1, 0)
    def findIndex(self, pattern):
        import re
        pattern = pattern.replace('*', '.+').replace('?', '.')
        for k, m in enumerate(self.items):
            if re.search(pattern, m):
                return k
        return -1


class Files(Emitter):
    def currentList(self):
        return ['/data/media/' + f for f in ('01_intro.mp3', '02_ambiance_loop.mp3', '03_story.mp3', '04_final_stop.mp3')]


class Settings():
    def __init__(self): self.v = {'volume': 100, 'loop': 0}
    def set(self, k, v): self.v[k] = v
    def get(self, k): return self.v.get(k)


class Wallclock():
    def __init__(self, *a, **k):
        self.args, self.kw = a, k
        self.orders = []; self.advance = True; self.leading = False
    def order(self, event, args=None, delay_ms=0): self.orders.append((event, args, delay_ms))
    def mayAdvance(self): return self.advance
    def isLeader(self): return self.leading


class Lcd():
    def set_color(self, *rgb): self.color = rgb


class Keypad(Emitter):
    CHAR_WIFI = 'W'; CHAR_PEERS = 'P'; CHAR_VOL = 'V'; CHAR_PLAY = '>'; CHAR_STOP = '#'; CHAR_LOVE = '<3'
    def __init__(self, *a, **k):
        super().__init__(); self.lcd = Lcd()
    def draw(self, lines=None): pass


class Zyre():
    def __init__(self, *a, **k): self.args = a; self.node = None
    def activeCount(self): return 4


class Dummy():
    def __init__(self, *a, **k): self.args, self.kw = a, k


class FakeHPlayer2(Emitter):
    last = None
    def __init__(self, base_path, cfg):
        super().__init__()
        FakeHPlayer2.last = self
        self.cfg = cfg
        self.settings = Settings()
        self.playlist = Playlist()
        self.files = Files()
        self.added = []
        self.ifaces = {}
    def addPlayer(self, kind, name):
        self.player = Player(); return self.player
    def addInterface(self, name, *a, **k):
        cls = {'wallclock': Wallclock, 'keypad': Keypad, 'zyre': Zyre}.get(name, Dummy)
        obj = cls(*a, **k)
        self.added.append((name, a, k))
        self.ifaces[name] = obj
        return obj
    def log(self, *a): pass
    def run(self): pass


fake = types.ModuleType('core.engine.hplayer')
fake.HPlayer2 = FakeHPlayer2
sys.modules['core.engine.hplayer'] = fake

import time as _time
_sleep = _time.sleep
_time.sleep = lambda s: None            # the profile waits 2 s for USB: not here
mod = runpy.run_path(os.path.join(REPO, 'profiles', '26-anna.py'))
_time.sleep = _sleep

hp = FakeHPlayer2.last
wc = hp.ifaces['wallclock']
kp = hp.ifaces['keypad']
ok = 0

def check(cond, msg):
    global ok
    if not cond:
        print('   FAIL: ' + msg); sys.stdout.flush(); os._exit(1)
    ok += 1
    print('   ok  ' + msg)

print('== profiles/26-anna.py on a stub HPlayer2 ==')
names = [a[0] for a in hp.added]
check(hp.cfg == '/data/hplayer2-26-anna.cfg', 'settings file: %s' % hp.cfg)
check(names[0] == 'health' and hp.added[0][2] == {'restart': False}, 'health first, restart=False: %s' % (hp.added[0],))
check(('zyre', ('wint',), {}) in hp.added, 'zyre on wint')
check(('wallclock', ('wint',), {'role': 'elected'}) in hp.added, 'wallclock on wint, role=elected')
check(set(names) >= {'keypad', 'http', 'keyboard', 'teleco2'}, 'keypad, http, numpad, CoreS3 remote: %s' % names)
check(hp.settings.get('loop') == -1, 'loop -1 at load')
hp.emit('app-run')
check(hp.settings.get('loop') == -1 and hp.settings.get('volume') == 95, 'app-run on a fresh card: loop -1, volume 95')
check(hp.playlist.size() == 4, 'playlist = the media folder')

# keypad: locked by default
hp.playlist._index = 1
hp.emit('keypad.right')
check(wc.orders == [], 'keypad locked at boot: right does nothing')
# (run_path returns a copy of the globals: drive the lock through the handlers' live globals)
g = mod['go_next'].__globals__
g['keylock'] = False
hp.emit('keypad.right')
check(wc.orders[-1] == ('unbuf_playindex', [2], 300), 'unlocked keypad right -> playindex(next) buffered 300 ms: %s' % (wc.orders[-1],))
hp.player.playing = True; hp.player.pos = 10.0
hp.emit('keypad.left')
check(wc.orders[-1] == ('unbuf_playindex', [1], 300), 'left past the intro rewinds the current track: %s' % (wc.orders[-1],))
hp.emit('keypad.select')
check(wc.orders[-1] == ('stop', [], 300), 'select -> stop, buffered: %s' % (wc.orders[-1],))
hp.emit('keypad.up')
check(wc.orders[-1] == ('volume', [96], 0), 'up -> volume +1, immediate: %s' % (wc.orders[-1],))
g['keylock'] = True

# numpad + remote (not gated by keylock)
hp.emit('keyboard.KEY_KP3-down')
check(wc.orders[-1] == ('unbuf_playz', [3], 300), 'numpad 3 -> playz 3: %s' % (wc.orders[-1],))
hp.emit('keyboard.KEY_KPENTER-down')
check(wc.orders[-1] == ('stop', [], 300), 'numpad enter -> stop')
hp.emit('teleco2.remote-next')
check(wc.orders[-1][0] == 'unbuf_playindex', 'remote next works while the keypad is locked')
hp.emit('teleco2.remote-playpause')
check(wc.orders[-1] == ('pause', [], 300), 'remote playpause while playing -> pause, buffered: %s' % (wc.orders[-1],))
hp.player.paused = True
hp.emit('teleco2.remote-playpause')
check(wc.orders[-1] == ('resume', [], 300), '... and resume when paused')
hp.player.paused = False
hp.emit('teleco2.remote-playindex', 3)
check(wc.orders[-1] == ('unbuf_playindex', [3], 300), 'remote playindex 3')
hp.emit('http.playh', '2')
check(wc.orders[-1] == ('unbuf_playindex', [2], 300), 'http playh 2')

# zyre orders -> playlist
hp.emit('zyre.unbuf_playindex', 2)
check(hp.playlist.emitted[-1] == ('playindex', (2,)), 'zyre playindex -> playlist')
hp.emit('zyre.unbuf_playz', 4)
check(hp.playlist.emitted[-1] == ('playindex', (3,)), 'zyre playz 4 -> the 04_ track (index 3)')

# track end: by name, only when mayAdvance()
n = len(wc.orders)
for idx, want in ((0, ('unbuf_playindex', [1], 300)), (1, ('unbuf_playindex', [1], 300)), (2, ('unbuf_playindex', [3], 300))):
    hp.playlist._index = idx
    hp.emit('playlist.end')
    check(wc.orders[-1] == want, 'end of %s -> %s' % (os.path.basename(hp.playlist.trackAtIndex(idx)), want))
hp.playlist._index = 3
n = len(wc.orders)
hp.emit('playlist.end')
check(len(wc.orders) == n, "end of 04_final_stop ('_stop', and the last track) -> no order")
wc.advance = False
hp.playlist._index = 0
hp.emit('playlist.end')
check(len(wc.orders) == n, 'a follower (mayAdvance False) orders nothing at the track end')

# keypad LCD (the locked presses above left a "Locked !" alert up: clear it)
g['lockAlertCounter'] = 0
upd = kp.update
hp.player.media = '/data/media/01_intro.mp3'; hp.player.pos = 0.0; hp.player.playing = True
hp.playlist._index = 0
l0, l1 = upd()
check('01_intro' in l0, "a name shorter than the window shows whole (hplayer2#t-083): %r" % l0)
wc.leading = True
l0, l1 = upd()
check(l1.endswith('*') and len(l1) <= 16, "the leader shows `*`: %r" % l1)
wc.leading = False
l0, l1 = upd()
check(not l1.endswith('*'), 'a follower does not: %r' % l1)

print('\nALL %d CHECKS PASSED' % ok)
sys.stdout.flush()
os._exit(0)
