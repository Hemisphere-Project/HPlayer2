"""The lockout watchdog gives a fresh load LOAD_GRACE before it counts (sacvp-kernel4-2025 4b385be).

On a busy Pi 3B+ opening the next file can keep mpv silent for over a second; four 0.2 s
IPC timeouts used to kill a healthy player right after a cue (HPO 2026-10-15)."""
import core.players.mpv as mpv_module
from core.players.mpv import MpvPlayer, LOAD_GRACE


class DummyHPlayer:
    def autoBind(self, module) -> None:  # noqa: N802
        return None

    def emit(self, event: str, *args) -> None:
        return None


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make_player(monkeypatch):
    monkeypatch.setattr(mpv_module, 'read_audio_conf', lambda path=None: None)
    clock = Clock()
    monkeypatch.setattr(mpv_module, 'time', clock)
    player = MpvPlayer(DummyHPlayer(), "test")
    sent, emitted, killed = [], [], []
    player._mpv_send = sent.append
    player._force_stop_backend = lambda: killed.append(True)
    player.emit = lambda ev, *a: emitted.append(ev)
    player._ndi = False
    return player, clock, sent, emitted, killed


def silence(player, clock, seconds):
    """IPC silence: one watchdog call per 0.2 s socket timeout"""
    for _ in range(int(round(seconds / 0.2))):
        clock.t += 0.2
        player._ipcTimeout()


def test_fresh_load_survives_a_long_silence(monkeypatch):
    player, clock, sent, emitted, killed = make_player(monkeypatch)
    player._play('/data/media/cue.mp4')
    player.update('media', '/data/media/cue.mp4')
    player.update('isPlaying', True)
    silence(player, clock, LOAD_GRACE - 0.4)       # mpv busy opening the file: > 4 timeouts
    assert player._mpv_lockedout == 0
    assert 'hardreset' not in emitted and not killed


def test_hung_mpv_is_still_killed_after_the_grace(monkeypatch):
    player, clock, sent, emitted, killed = make_player(monkeypatch)
    player._play('/data/media/cue.mp4')
    player.update('media', '/data/media/cue.mp4')
    player.update('isPlaying', True)
    silence(player, clock, 20)
    assert killed and 'hardreset' in emitted
    # the watchdog's own reload is a load too: the cue's loadfile, then exactly one reload
    assert sum('"loadfile"' in m for m in sent) == 2


def test_playing_long_after_a_load_counts_at_once(monkeypatch):
    player, clock, sent, emitted, killed = make_player(monkeypatch)
    player._mpv_loadtime = clock.t - 60            # a clip that has been playing for a minute
    player.update('media', '/data/media/loop.mp4')
    player.update('isPlaying', True)
    player._ipcTimeout()
    assert player._mpv_lockedout == 1
    assert sent == ['{ "command": ["set_property", "pause", false] }']


def test_ndi_load_arms_the_grace(monkeypatch):
    player, clock, sent, emitted, killed = make_player(monkeypatch)
    player._ndi = True
    monkeypatch.setattr(player, '_ndi_source', lambda path: None)
    player._mpv_loadtime = 0
    player._play('/data/media/cam.ndi')
    assert player._mpv_loadtime == clock.t


def test_images_and_idle_never_count(monkeypatch):
    player, clock, sent, emitted, killed = make_player(monkeypatch)
    player._mpv_loadtime = clock.t - 60
    player.update('media', '/data/media/still.jpg')
    player.update('isPlaying', True)
    player._ipcTimeout()
    player.update('media', '/data/media/clip.mp4')
    player.update('isPlaying', False)
    player._ipcTimeout()
    assert player._mpv_lockedout == 0 and sent == []
