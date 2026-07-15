"""
DMX interface offline test: no real player, no real serial, no adapter.

Validates the import chain (core.interfaces.dmx via the registry), the per-media
sidecar load, the pure-function frame evaluation against a fake player clock, the
http2 status/level bridge, and the exact bytes each protocol writes to the wire.

    /tmp/dmx-venv/bin/python tests/test_dmx_offline.py
"""
import sys, os, types, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# stub netifaces (pulled in transitively by some interfaces); not needed here
ni = types.ModuleType('netifaces')
ni.AF_INET = 2; ni.interfaces = lambda: []; ni.ifaddresses = lambda i: {}
sys.modules.setdefault('netifaces', ni)

from core.interfaces import getInterface

_fails = []
def check(name, got, want):
    ok = got == want
    print(('  ok  ' if ok else ' FAIL ') + name + ('' if ok else '  got=%r want=%r' % (got, want)))
    if not ok: _fails.append(name)


# --- minimal fakes -----------------------------------------------------------
# NB: use the codebase's EventEmitterX (core/module.py) so emit() prepends the
# event name to args exactly like production — the dmx handlers rely on it.
from core.module import EventEmitterX

class FakeSettings:
    def __init__(self): self._settings = {}
    def get(self, k): return self._settings.get(k)
    def set(self, k, v): self._settings[k] = v

class FakePlayer:
    def __init__(self): self._m = None; self._t = 0.0; self._p = False
    def status(self, k): return {'media': self._m}.get(k)
    def position(self): return self._t
    def isPlaying(self): return self._p

class FakeHttp2:
    def __init__(self): self.sent = []
    def send(self, ev, msg): self.sent.append((ev, msg))

class FakeHplayer(EventEmitterX):
    def __init__(self):
        super().__init__(wildcard=True, delimiter='.')
        self.settings = FakeSettings()
        self._player = FakePlayer()
        self._http2 = FakeHttp2()
    def players(self): return [self._player]
    def interface(self, name): return self._http2 if name == 'http2' else None
    def autoBind(self, m): pass

class FakeSerial:
    def __init__(self): self.written = bytearray(); self.break_condition = False
    def write(self, b): self.written += b
    def flush(self): pass
    def close(self): pass


print("[1] registry + construction")
cls = getInterface('dmx')
check("resolved class", cls.__name__, 'DmxInterface')
hp = FakeHplayer()
dmx = cls(hp)
check("defaults seeded", hp.settings.get('dmx-protocol'), 'open')

# sidecar next to a temp 'media'
d = tempfile.mkdtemp()
media = os.path.join(d, 'vague.mp4')
open(media, 'w').close()
with open(os.path.join(d, 'vague.dmx'), 'w') as f:
    f.write("def wash 1-2\n0:00 wash@0 3@255\n0:10 wash@100 fade 10\n")

print("\n[2] sidecar load on media change")
hp._player._m = media
dmx._syncMedia(media)
check("conduite file resolved", dmx._conduiteFile, os.path.join(d, 'vague.dmx'))
check("active channels", dmx._conduite.activeChannels(), [1, 2, 3])

print("\n[3] pure-function frame vs player clock")
check("t=0 wash off, ch3 on", (dmx._conduite.level(1, 0), dmx._conduite.level(3, 0)), (0, 255))
check("t=15 wash mid-fade ~50", dmx._conduite.level(1, 15), 50)
check("t=20 wash full", dmx._conduite.level(1, 20), 100)

print("\n[4] Open DMX wire bytes (start code 0 + 512 channels, break toggled)")
dmx.serial = FakeSerial(); dmx._openProto = 'open'
frame = bytearray(512); frame[0] = 200; frame[2] = 100
dmx._write(frame)
w = dmx.serial.written
check("open frame len = 1 startcode + 512", len(w), 513)
check("open start code", w[0], 0)
check("open ch1 payload", w[1], 200)
check("open ch3 payload", w[3], 100)
check("break released after write", dmx.serial.break_condition, False)

print("\n[5] DMX USB Pro packet framing 0x7E 06 <len> ... 0xE7")
dmx.serial = FakeSerial(); dmx._openProto = 'pro'
dmx._write(frame)
w = dmx.serial.written
check("pro header byte", w[0], 0x7E)
check("pro label 6", w[1], 0x06)
check("pro len LSB (513=0x0201)", w[2], 0x01)
check("pro len MSB", w[3], 0x02)
check("pro start code", w[4], 0x00)
check("pro ch1 payload", w[5], 200)
check("pro end byte", w[-1], 0xE7)
check("pro total len", len(w), 4 + 513 + 1)

print("\n[6] http2 editor load + save round-trip")
hp._http2.sent = []
hp.emit('http2.dmx-edit', media)
ev, msg = hp._http2.sent[-1]
check("edit reply event", ev, 'dmx-conduite')
check("edit reply carries text", 'wash' in msg['text'], True)
hp._http2.sent = []
hp.emit('http2.dmx-save', {'media': media, 'text': '0:00 5@255\nbadline\n'})
saved = [m for e, m in hp._http2.sent if e == 'dmx-saved']
check("save acked", len(saved), 1)
check("save reports 1 parse error", len(saved[0]['errors']), 1)
check("file rewritten", open(os.path.join(d, 'vague.dmx')).read().startswith('0:00 5@255'), True)

print("\n[7] blackout when stopped / no media")
hp._player._p = False
media2, t2, active2 = dmx._playerState()
check("player reports not active", active2, False)

print("\n" + ("ALL PASS" if not _fails else "FAILURES: " + ", ".join(_fails)))
sys.exit(1 if _fails else 0)
