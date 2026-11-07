"""
profiles/ecel.py's keypad LCD, top line: the media name behind `▶1/3 ` (hplayer2#t-083).

The scroll offset is capped at `len(media) - 15 + len(prefix)`. For a name shorter than the
window that cap is negative, and `media[negative:]` keeps only the TAIL — `01_intro` read `ro`.
The profile runs here against a stub HPlayer2 (no mpv, no keypad plate, no /data/usb), and
its own `lcd_update` is called at chosen playback positions.
"""
import os
import runpy
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
PROFILE = os.path.join(REPO, 'profiles', 'ecel.py')

PLAY = '\x03'           # Keypad.CHAR_PLAY: one LCD cell, as on the plate


class Emitter():
    def __init__(self):
        self.h = {}
        self.emitted = []

    def on(self, ev, fn=None):
        def reg(f):
            self.h.setdefault(ev, []).append(f)
            return f
        return reg(fn) if fn else reg

    def emit(self, ev, *args):
        self.emitted.append((ev, args))


class Player():
    def __init__(self):
        self.media = None
        self.pos = 0.0

    def position(self):
        return self.pos

    def status(self, k=None):
        s = {'media': self.media, 'time': self.pos}
        return s[k] if k else s


class Playlist(Emitter):
    def __init__(self):
        super().__init__()
        self._index = 0
        self._size = 3

    def load(self, path):
        pass

    def index(self):
        return self._index

    def size(self):
        return self._size


class Settings():
    def __init__(self):
        self.v = {'volume': 80}

    def set(self, k, v):
        self.v[k] = v

    def get(self, k):
        return self.v.get(k)


class Lcd():
    def set_color(self, *rgb):
        self.color = rgb


class Keypad(Emitter):
    CHAR_WIFI = '\x00'
    CHAR_PEERS = '\x01'
    CHAR_VOL = '\x02'
    CHAR_PLAY = PLAY
    CHAR_STOP = '\x04'
    CHAR_LOVE = '\x05'

    def __init__(self, *a, **k):
        super().__init__()
        self.lcd = Lcd()

    def draw(self, lines=None):
        pass


class Dummy():
    def __init__(self, *a, **k):
        pass


class FakeHPlayer2(Emitter):
    last = None

    def __init__(self, base_path, cfg):
        super().__init__()
        FakeHPlayer2.last = self
        self.settings = Settings()
        self.playlist = Playlist()
        self.files = Emitter()
        self.ifaces = {}

    def addPlayer(self, kind, name):
        self.player = Player()
        return self.player

    def addInterface(self, name, *a, **k):
        obj = (Keypad if name == 'keypad' else Dummy)(*a, **k)
        self.ifaces[name] = obj
        return obj

    def log(self, *a):
        pass

    def run(self):
        pass


@pytest.fixture
def ecel(monkeypatch):
    """Run profiles/ecel.py on the stub; return (hplayer, keypad)."""
    fake = types.ModuleType('core.engine.hplayer')
    fake.HPlayer2 = FakeHPlayer2
    monkeypatch.setitem(sys.modules, 'core.engine.hplayer', fake)
    monkeypatch.setattr('time.sleep', lambda s: None)          # its 2 s wait for USB
    listdir = os.listdir
    monkeypatch.setattr(os, 'listdir', lambda p='.': [] if p == '/data/usb' else listdir(p))
    runpy.run_path(PROFILE)
    hp = FakeHPlayer2.last
    return hp, hp.ifaces['keypad']


def top_line(hp, kp, name, pos):
    hp.player.media = '/data/media/' + name + '.mp3'
    hp.player.pos = pos
    return kp.update()[0]


# a scroll cycle of the profile (scrollSpeed 3.08 cells/s), sampled every 0.25 s
POSITIONS = [k / 4 for k in range(0, 41)]


# up to 10 cells: the window behind `▶1/3 ` is 11, and the scroll always ends on one blank
@pytest.mark.parametrize('name', ['01_intro', '1', '02_ab', '03_abc', '04_abcd', '05_abcde',
                                  '06_abcdef', '07_abcdefg'])
def test_a_name_that_fits_shows_whole_all_the_time(ecel, name):
    hp, kp = ecel
    prefix = PLAY + '1/3 '
    assert len(prefix + name) <= 15, 'the case is a name that fits, blank included'
    for pos in POSITIONS:
        assert top_line(hp, kp, name, pos) == (prefix + name).ljust(16), 'at %.2f s' % pos


def test_a_long_name_still_scrolls_to_its_end(ecel):
    hp, kp = ecel
    name = '02_ambiance_loop'                       # 16 cells: the window behind `▶1/3 ` is 11
    assert top_line(hp, kp, name, 0.0) == PLAY + '1/3 02_ambiance'      # the intro holds the start
    assert top_line(hp, kp, name, 3.0) == PLAY + '1/3 mbiance_loo'      # offset 4
    assert top_line(hp, kp, name, 5.0) == PLAY + '1/3 iance_loop '      # capped at 6, + one blank
    offsets = {name.index(top_line(hp, kp, name, p)[5:].rstrip()[:5]) for p in POSITIONS}
    assert offsets == set(range(0, 7)), offsets


def test_the_prefix_width_moves_the_cap(ecel):
    """With `▶10/12 ` the window is 9 cells: a 7-cell name shows whole (it read `a` before)."""
    hp, kp = ecel
    hp.playlist._index, hp.playlist._size = 9, 12
    for pos in POSITIONS:
        line = top_line(hp, kp, '10_coda', pos)
        assert line == (PLAY + '10/12 10_coda').ljust(16), 'at %.2f s' % pos


def test_stopped_shows_the_count_only(ecel):
    hp, kp = ecel
    hp.player.media = None
    assert kp.update()[0] == ('\x04' + '1/3').ljust(16)
