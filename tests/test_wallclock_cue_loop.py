"""A slave's playlist loop flag follows the master's mode AND its cue, every packet (hplayer2#t-052).

Rig run 21/11 (bench-02 master, bench-03 slave): a slave cue file shorter than the master's
logged its hold (« our file ends at 25.0s … stopped, waiting for it ») yet kept playing from 0
while the master sat at 33 s. The one-file cue playlist had wrapped it first: `loop` read 2.
Two ways in, both replayed here with the real Playlist.onMediaEnd:
  - playlist-owned master: the wallclock mirrored loop 0 once, on the mode change; the
    profile's play0 wrote 2 back at the slave's first playlist end, and nothing undid it;
  - seamless master: loop 2 was mirrored on purpose, but a cue file of another length must
    END (oneLoop False) — mpv stopped looping it, the playlist wrapped it anyway.
"""

from core.engine.playlist import Playlist
from core.interfaces.wallclock import WallclockInterface


class Settings:
    def __init__(self, loop):
        self.d = {'loop': loop}
        self.writes = []

    def get(self, key):
        return self.d.get(key)

    def set(self, key, val):
        if self.d.get(key) != val:
            self.d[key] = val
            self.writes.append((key, val))


class Files:
    def listFiles(self, plist):
        return list(plist) if isinstance(plist, list) else [plist]

    def validExt(self, f):
        return True


class HPlayer:
    def __init__(self, loop):
        self.settings = Settings(loop)
        self.files = Files()
        self.events = []

    def autoBind(self, module):
        return None

    def emit(self, event, *args):
        self.events.append(event)


class Player:
    def __init__(self, playing=True):
        self.playing = playing
        self.oneloop = []

    def isPlaying(self):
        return self.playing

    def _applyOneLoop(self, v):
        self.oneloop.append(v)


def _slave(hp, seamless, followIdx=0, sameDur=True, playing=True):
    w = WallclockInterface.__new__(WallclockInterface)
    w.hplayer = hp
    w.player = Player(playing)
    w.elected = False
    w._masterSeamless = seamless
    w._followIdx = followIdx
    w._sameDur = sameDur
    w._loopApplied = None
    return w


def _ends_with_restart(hp, cuefile):
    """One media-end on a one-file cue playlist: True = the playlist restarted the file."""
    pl = Playlist(hp)
    pl._playlist = [cuefile]
    pl._index = 0
    restarted = []
    pl.playindex = lambda i, pause=False: restarted.append(i)
    pl.onMediaEnd()
    return bool(restarted)


def test_playlist_owned_master_profile_rewrite_is_undone_next_packet():
    hp = HPlayer(loop=0)
    w = _slave(hp, seamless=False, followIdx=7, sameDur=False)
    hp.settings.set('loop', 2)              # play0 at the slave's playlist end (the rig's 22:22:00)
    w._mirrorLoop()                         # the next clock packet
    assert hp.settings.get('loop') == 0
    assert w.player.oneloop == [False]
    assert not _ends_with_restart(hp, '07_cueB-slave-short-25s.wav')


def test_seamless_master_shorter_cue_file_ends_instead_of_wrapping():
    hp = HPlayer(loop=2)                    # mirrored 2: the master loops one file in mpv
    w = _slave(hp, seamless=True, followIdx=7, sameDur=False)
    w._mirrorLoop()
    assert hp.settings.get('loop') == 0
    assert not _ends_with_restart(hp, '07_cueB-slave-short-25s.wav')


def test_seamless_master_same_length_still_wraps_seamlessly():
    hp = HPlayer(loop=0)
    w = _slave(hp, seamless=True, followIdx=7, sameDur=True)
    w._mirrorLoop()
    assert hp.settings.get('loop') == 2
    assert w.player.oneloop == [True]
    assert _ends_with_restart(hp, '07_cueB-slave-40s.wav')


def test_plain_wall_follows_the_master_mode_both_ways():
    hp = HPlayer(loop=2)
    w = _slave(hp, seamless=False)
    w._mirrorLoop()
    assert hp.settings.get('loop') == 0
    w._masterSeamless = True
    w._mirrorLoop()
    assert hp.settings.get('loop') == 2


def test_steady_state_writes_nothing():
    hp = HPlayer(loop=0)
    w = _slave(hp, seamless=False, followIdx=6, sameDur=False)
    for _ in range(50):
        w._mirrorLoop()
    assert hp.settings.writes == []
    assert w.player.oneloop == []


def test_stopped_player_gets_the_flag_but_no_mpv_command():
    hp = HPlayer(loop=2)
    w = _slave(hp, seamless=False, playing=False)
    w._mirrorLoop()
    assert hp.settings.get('loop') == 0
    assert w.player.oneloop == []
