"""A Nowde slave's node relinks (USB reset, node reboot) while the player plays the master's clip:
the clip must keep playing and the MTC chase correct it -- not stop, replay from 0 and JUMP back.

W4, 19/10 (biennale@a008e83): `- role slave` -> the profile stopped the player (a relink looked like
a boot: lastCC None) -> the Drifter's stall hook replayed the pattern from 0 -> JUMP to 226 s -> the
first CC#100 (lastCC reset by `_close_ports`) replayed it once more. 5-8 relinks a day per storming
slave (hplayer2#t-050). Measured here as the issue was measured there: plays and seeks per relink.

The profile's role rule is read from profiles/biennale.py itself, so the test follows the profile."""
import os
import re
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("mido")
pytest.importorskip("timecode")

from core.engine.hplayer import HPlayer2                        # noqa: E402
from core.interfaces.nowde import NowdeInterface, encode7, CMD_HELLO   # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICK = 0.25                                     # s between two MTC full frames fed to the servo


class FakePlayer:
    """Plays one file at a time; time advances only when the test says so (at the servo's speed)."""

    def __init__(self):
        self.name = 'player'
        self.media, self.time, self.playing, self.rate = None, 0.0, False, 1.0
        self.stops, self.seeks = 0, []

    def status(self, entry=None):
        st = {'isPlaying': self.playing, 'isPaused': False, 'media': self.media,
              'time': self.time, 'duration': 600.0}
        return st[entry] if entry else st

    def isPlaying(self):
        return self.playing

    def isPaused(self):
        return False

    def resume(self):
        pass

    def position(self):
        return self.time

    def speed(self, s):
        self.rate = s

    def seekTo(self, ms, exact=False):
        self.seeks.append(ms / 1000.0)
        self.time = ms / 1000.0

    def stop(self):
        self.stops += 1
        self.playing = False

    def advance(self, dt):
        if self.playing:
            self.time += dt * self.rate


class FakePlaylist:
    """playlist.play(pattern) as the slave uses it: the clip whose prefix the pattern names, from 0."""

    FILES = ['01_intro.mp4', '03_garden.mp4', '04_night.mp4']

    def __init__(self, player):
        self.player, self.plays, self._size = player, [], 0

    def play(self, pattern=None, index=-1, pause=False):
        alts = re.findall(r'(\d+)_\*', pattern or '')
        hits = [f for f in self.FILES if any(f.startswith(a + '_') for a in alts)]
        self.plays.append(pattern)
        self._size = len(hits)
        if hits:
            self.player.media, self.player.time, self.player.playing = hits[0], 0.0, True

    def size(self):
        return self._size


def profile_slave_role_stops(nowde, player):
    """The biennale profile's `nowde.role == 'slave'` rule, evaluated from its source."""
    src = open(os.path.join(REPO, 'profiles', 'biennale.py')).read()
    m = re.search(r"elif args\[0\] == 'slave':(?:\n\t+#[^\n]*)*\n\t+if ([^\n]+):\n\t+player\.stop\(\)", src)
    assert m, "profiles/biennale.py: the slave-role stop rule moved; update this test"
    return eval(m.group(1), {}, {'nowde': nowde, 'player': player})


class FakePort:
    def send(self, msg):
        pass

    def close(self):
        pass


def hello_slave(uptime_ms=5000):
    up = [(uptime_ms >> 24) & 0xFF, (uptime_ms >> 16) & 0xFF, (uptime_ms >> 8) & 0xFF, uptime_ms & 0xFF]
    return [0x7D, CMD_HELLO] + encode7(list(b'2.0.5'.ljust(8, b'\x00'))) + encode7(up) + [1, 0, 2, 2, 0]


@pytest.fixture
def rig(monkeypatch):
    hplayer = HPlayer2(mediaPath=[])
    player = FakePlayer()
    hplayer._players['player'] = player
    hplayer.playlist = FakePlaylist(player)
    i = NowdeInterface(hplayer, player, mode='auto')
    lines = []
    monkeypatch.setattr(i, 'log', lambda *a: lines.append(' '.join(str(x) for x in a)))
    i.drifter.log = lambda *a: lines.append(' '.join(str(x) for x in a))
    i.lines, i.fp, i.pl = lines, player, hplayer.playlist
    i.clock = 0.0
    return i


def link_slave(i):
    """The listener's connect, then the node's HELLO, then the profile's role rule."""
    i.port, i.out, i._linkDownSince = FakePort(), FakePort(), None
    i._handle_sysex(hello_slave())
    assert i.role == 'slave'
    if profile_slave_role_stops(i, i.fp):
        i.fp.stop()


def mtc(i, seconds):
    """The master's clock runs; the node streams it (full frames) and the player plays on."""
    for _ in range(int(seconds / TICK)):
        i.clock += TICK
        i.fp.advance(TICK)
        i.handle_timecode('nowde.ff', types.SimpleNamespace(float=i.clock))


def freewheel(i, seconds):
    """Link down: the master's clock runs, the player plays on, no MTC reaches the servo."""
    i.clock += seconds
    i.fp.advance(seconds)


def garden_slave_playing_3(i):
    link_slave(i)
    i.handle_media_selection(3)
    assert i.pl.plays == ['(003_*|03_*|3_*)'] and i.fp.media == '03_garden.mp4'
    mtc(i, 60)                                  # a minute in, locked
    assert abs(i.fp.time - i.clock) < 0.3


def relink(i):
    """W4's shape: the port vanishes, 3.4 s of freewheel, the node comes back."""
    i._close_ports()
    freewheel(i, 3.4)
    plays, stops, seeks = len(i.pl.plays), i.fp.stops, len(i.fp.seeks)
    link_slave(i)
    mtc(i, 2)                                   # MTC resumes before the master's next CC#100
    i.handle_media_selection(3)                 # ... which names the clip already playing
    mtc(i, 5)
    return len(i.pl.plays) - plays, i.fp.stops - stops, len(i.fp.seeks) - seeks


def test_a_relink_keeps_the_clip_playing(rig):
    garden_slave_playing_3(rig)
    replays, stops, seeks = relink(rig)
    assert (replays, stops, seeks) == (0, 0, 0)
    assert rig.fp.playing and rig.fp.media == '03_garden.mp4'
    assert abs(rig.fp.time - rig.clock) < 0.3   # still on the master's clock
    assert any('after a relink: already playing it' in l for l in rig.lines)
    assert not any('Video ended, restarting' in l for l in rig.lines)
    assert rig.lastCC == 3 and not rig.relinking()


def test_the_bug_it_fixes(rig):
    """Same relink with the relink memory wiped (= the code before #t-050): stop, replay from 0, JUMP."""
    garden_slave_playing_3(rig)
    rig._close_ports()
    rig._relinkCC = None
    freewheel(rig, 3.4)
    plays, seeks = len(rig.pl.plays), len(rig.fp.seeks)
    link_slave(rig)
    assert rig.fp.stops == 1                    # the profile took the relink for a boot
    mtc(rig, 2)
    rig.handle_media_selection(3)
    mtc(rig, 5)
    assert len(rig.pl.plays) - plays == 2       # the stall hook's replay, then CC#100's
    assert len(rig.fp.seeks) - seeks >= 1       # and the JUMP back to the master
    assert any('Video ended, restarting' in l for l in rig.lines)


def test_boot_play_is_still_dropped_for_the_master(rig):
    rig.pl.play('(001_*|01_*|1_*)')            # what boot started (default pattern) before the role
    link_slave(rig)
    assert rig.fp.stops == 1 and not rig.fp.playing
    rig.handle_media_selection(1)               # the master's clip: played by CC#100, not kept
    assert len(rig.pl.plays) == 2 and rig.fp.playing


def test_a_relink_onto_another_clip_switches(rig):
    garden_slave_playing_3(rig)
    rig._close_ports()
    link_slave(rig)
    rig.handle_media_selection(4)               # the master moved on during the gap
    assert rig.pl.plays[-1] == '(004_*|04_*|4_*)' and rig.fp.media == '04_night.mp4'


def test_a_relink_with_the_player_stopped_replays(rig):
    garden_slave_playing_3(rig)
    rig._close_ports()
    rig.fp.stop()                               # whatever stopped it meanwhile, the master's CC#100 restarts it
    link_slave(rig)
    rig.handle_media_selection(3)
    assert len(rig.pl.plays) == 2 and rig.fp.playing


def test_a_relink_after_a_stop_carries_nothing(rig):
    garden_slave_playing_3(rig)
    rig.handle_media_selection(0)
    rig._close_ports()
    assert not rig.relinking()
    rig._close_ports()                          # the listener's final cleanup closes twice
    assert not rig.relinking()


def test_the_silence_guard_ends_the_relink_memory(rig, monkeypatch):
    garden_slave_playing_3(rig)
    rig._close_ports()
    assert rig.relinking()
    monkeypatch.setattr(rig, '_cfg_seconds', lambda key: 5.0 if key == 'nowde-silence-stop' else 0.0)
    rig._slave_watch(1000.0)
    rig._slave_watch(1006.0)                    # link down past the grace: the guard stops us
    assert rig._guardStopped and not rig.fp.playing
    assert rig._relinkCC is None
    link_slave(rig)
    rig.handle_media_selection(3)               # the master's CC#100 resumes us: a real play
    assert len(rig.pl.plays) == 2 and rig.fp.playing
