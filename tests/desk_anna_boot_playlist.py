"""
Boot test of profiles/26-anna.py's playlist (anna-players#t-017; the Anna-01 bench bug on 3c7757e):
after every boot the playlist IS the media folder, whatever the settings file holds.

The bug: HPlayer2.run() calls settings.load(), which replays every stored key as do-<key>, and
hplayer's own do-playlist binding (autoBind) runs playlist.load(<stored value>). A fresh card stores
None, which empties the list the profile built at import (LCD 0/0, next/play do nothing). A stored list
is stale once the USB sync's rsync --delete has changed /data/media, and then index sync breaks.

Nothing on that path is faked: the REAL HPlayer2.run() and autoBind, Settings, Playlist and FileManager
(on a temp media folder), with one FRESH process per boot, like a card (Settings keeps its values on the
class). Only the player, the interfaces and the network are stubs. os.system is refused while the profile
loads, so its USB sync (rsync --delete into /data/media) can never run on a dev machine.

    .venv/bin/python -u tests/desk_anna_boot_playlist.py [--profile PATH]     (PATH: an older 26-anna.py)
"""
import sys, os, types, json, shutil, subprocess, tempfile, inspect, runpy
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def stub_network():
    ni = types.ModuleType('netifaces')
    ni.AF_INET = 2; ni.AF_INET6 = 10; ni.AF_LINK = 17; ni.AF_PACKET = 17; ni.AF_BRIDGE = 7
    ni.interfaces = lambda: []
    ni.ifaddresses = lambda iface: {}
    sys.modules['netifaces'] = ni
    from core.engine import network
    network.has_interface = lambda iface: iface == 'wint'
    network.get_essid = lambda iface: 'pisync' if iface == 'wint' else None
    network.get_rssi = lambda iface: 70


# ─── one boot, in its own process ──────────────────────────────────────────────────────────────

def boot(media, cfg, profile):
    stub_network()
    import core.engine.hplayer as real
    from core.module import Module
    from core.engine.settings import Settings
    from core.engine.filemanager import FileManager
    from core.engine.playlist import Playlist
    from threading import Event

    class Player():
        name = 'mpv'
        def on(self, ev, fn=None):
            return fn if fn else (lambda f: f)
        def validExt(self, f): return f.lower().endswith(('.mp4', '.mp3', '.mov'))
        def start(self): pass
        def isRunning(self): return True
        def isReady(self): return True
        def isPlaying(self): return False
        def isPaused(self): return False
        def position(self): return 0.0
        def status(self, k=None): return None if k else {}
        def stop(self): pass

    class Stub():
        def __init__(self, *a, **k): self.args, self.kw = a, k
        def on(self, ev, fn=None): return fn if fn else (lambda f: f)
        def emit(self, *a): pass
        def start(self): pass

    class Lcd():
        def set_color(self, *rgb): pass

    class Keypad(Stub):
        CHAR_WIFI = 'W'; CHAR_PEERS = 'P'; CHAR_VOL = 'V'; CHAR_PLAY = '>'; CHAR_STOP = '#'; CHAR_LOVE = '<3'
        lcd = Lcd()
        def draw(self, lines=None): pass

    class Wallclock(Stub):
        def order(self, *a, **k): return True
        def mayAdvance(self): return True
        def isLeader(self): return False
        dupName = False

    class BootHPlayer2(real.HPlayer2):
        """The real constructor's component order (settings, files, playlist, files.add, autoBind),
        minus players/interfaces/imgen; the card's paths swapped for the temp folder and cfg."""
        def __init__(self, basepath, config):
            Module.__init__(self, None, 'HPlayer2', 'green')
            self._players = OrderedDict(); self._samplers = OrderedDict(); self._interfaces = OrderedDict()
            self._lastUsedPlayer = 0
            self._shutdown_event = Event(); self._shutdown_event.set()
            self.appReady = False; self.appRunning = False
            self.settings = Settings(self, cfg)
            self.files = FileManager(self)
            self.playlist = Playlist(self)
            self.files.add([media])
            self.autoBind(self)
            self.reachedRun = False                     # run() resets appRunning on its way out
            self.on('app-run', lambda *a: setattr(self, 'reachedRun', True))
        def addPlayer(self, ptype, name):
            p = Player(); self._players[name] = p
            self.emit('player-added', p)                # the real one does: FileManager refreshes on it
            return p
        def addInterface(self, name, *a, **k):
            cls = {'keypad': Keypad, 'wallclock': Wallclock}.get(name, Stub)
            obj = cls(*a, **k); self._interfaces[name] = obj
            return obj
        def running(self): return False                 # the real run() returns right after app-run
        def _stop_components(self): pass

    fake = types.ModuleType('core.engine.hplayer')
    fake.__dict__.update(real.__dict__)
    fake.HPlayer2 = BootHPlayer2
    sys.modules['core.engine.hplayer'] = fake

    import time as _time
    _sleep, _system = _time.sleep, os.system
    _time.sleep = lambda s: None                        # the profile waits 2 s for USB: not here
    def refuse(cmd):
        raise RuntimeError('desk: os.system refused: %s' % cmd)
    os.system = refuse
    try:
        g = runpy.run_path(profile)                     # ends with hplayer.run(): the real one
    finally:
        _time.sleep, os.system = _sleep, _system
    hp = g['hplayer']
    stored = None
    if os.path.isfile(cfg):
        with open(cfg) as fd:
            stored = json.load(fd).get('playlist')
    print('RESULT ' + json.dumps({'playlist': list(hp.playlist._playlist), 'index': hp.playlist.index(),
                                  'stored': stored, 'ran': hp.reachedRun}))
    sys.stdout.flush()
    os._exit(0)


# ─── the scenarios ─────────────────────────────────────────────────────────────────────────────

ok = 0

def check(cond, msg):
    global ok
    if not cond:
        print('   FAIL: ' + msg); sys.stdout.flush(); os._exit(1)
    ok += 1
    print('   ok  ' + msg)


def run_boot(media, cfg, profile):
    r = subprocess.run([sys.executable, '-u', os.path.abspath(__file__), '--boot', media, cfg, profile],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    line = [l for l in r.stdout.splitlines() if l.startswith('RESULT ')]
    if r.returncode != 0 or not line:
        print(r.stdout[-4000:]); print(r.stderr[-4000:])
        check(False, 'the boot ran (exit %d)' % r.returncode)
    return json.loads(line[-1][len('RESULT '):])


def folder(media):
    return sorted(os.path.join(media, f) for f in os.listdir(media) if not f.startswith('.'))


def touch(*paths):
    for p in paths:
        open(p, 'w').close()


def main(profile):
    stub_network()
    from core.engine.hplayer import HPlayer2
    print('== the real boot path the test drives (a drift here voids the scenarios) ==')
    src = inspect.getsource(HPlayer2.run)
    check(0 <= src.find('self.settings.load()') < src.find("self.emit('app-run')"),
          "HPlayer2.run(): settings.load() runs, then app-run")
    src = inspect.getsource(HPlayer2.autoBind)
    k = src.find("@module.on('do-playlist')")
    check(k >= 0 and 'self.playlist.load(' in src[k:k + 200],
          "autoBind: settings' do-playlist -> playlist.load(<stored value>)")

    tmp = tempfile.mkdtemp(prefix='desk-anna-boot-')
    try:
        media = os.path.join(tmp, 'media'); os.mkdir(media)
        a, b = os.path.join(media, '01_mire.mp4'), os.path.join(media, '02_film.mp4')
        touch(a, b)
        print('== %s: the playlist after app-run is the media folder ==' % os.path.relpath(profile, REPO))

        cfg = os.path.join(tmp, 'fresh.cfg')
        r = run_boot(media, cfg, profile)
        check(r['ran'], 'the boot reached app-run')
        check(r['playlist'] == [a, b], "fresh card (no cfg, 'playlist' None): %s" % r['playlist'])
        check(r['stored'] == [a, b], 'the folder list is stored in the cfg: %s' % r['stored'])
        check(r['index'] == -1, 'nothing selected yet: the first next/play takes track 1')

        cfg = os.path.join(tmp, 'none.cfg')
        with open(cfg, 'w') as fd:
            json.dump({'playlist': None, 'volume': 80, 'loop': -1}, fd)
        r = run_boot(media, cfg, profile)
        check(r['playlist'] == [a, b], "cfg with 'playlist': None: %s" % r['playlist'])

        cfg = os.path.join(tmp, 'stale.cfg')
        gone = os.path.join(media, '00_old.mp4')
        with open(cfg, 'w') as fd:
            json.dump({'playlist': [gone, a], 'volume': 80, 'loop': -1}, fd)
        r = run_boot(media, cfg, profile)
        check(r['playlist'] == [a, b], 'cfg with a stale list [00_old (gone), 01]: %s' % r['playlist'])

        # the USB sync between two boots: rsync --delete drops 02, brings 03
        cfg = os.path.join(tmp, 'sync.cfg')
        r = run_boot(media, cfg, profile)
        check(r['stored'] == [a, b], 'boot 1 stores [01, 02]')
        c = os.path.join(media, '03_new.mp4')
        os.remove(b); touch(c)
        r = run_boot(media, cfg, profile)
        check(r['playlist'] == folder(media) == [a, c], 'boot 2 after the sync (02 gone, 03 new): %s' % r['playlist'])
        check(r['stored'] == [a, c], 'and the cfg follows: %s' % r['stored'])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print('\nALL %d CHECKS PASSED' % ok)
    sys.stdout.flush()
    os._exit(0)


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--boot':
        boot(*sys.argv[2:5])
    prof = os.path.join(REPO, 'profiles', '26-anna.py')
    if len(sys.argv) == 3 and sys.argv[1] == '--profile':
        prof = os.path.abspath(sys.argv[2])
    main(prof)
