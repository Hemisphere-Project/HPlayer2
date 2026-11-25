"""A card with no role file plays its media in a loop on boot (hplayer2#t-104).

RastaOS-7.5's generic card has no /boot/hplayer2.conf, so hplayer2@auto runs profiles/default.py.
That profile started idle (autoplay off, nothing bound to app-run): the image's 0_mire never showed.
Thomas, 2026-11-20: a blank card plays its media folder in a loop, so a freshly burned card proves
itself on a screen with no laptop.

The real profile file runs on the real HPlayer2 (Settings, Playlist, FileManager). The card's /data
is a tmp folder (no USB key: /data/usb is absent, as on bench-03), the player a stub that records
what it was told to play, interfaces are skipped and run() is the boot's last two steps.
"""
import copy
import json
import pathlib
import runpy

import pytest

import core.engine.hplayer as engine
from core.engine.settings import Settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles' / 'default.py'
DEFAULTS = copy.deepcopy(Settings._settings)


class StubPlayer:
    def __init__(self):
        self.playing = False
        self.played = []

    def validExt(self, f):
        return f.endswith('.mp4')

    def isPlaying(self):
        return self.playing

    def play(self, media, pause=False):
        self.played.append(media)
        self.playing = True

    def stop(self):
        self.playing = False


@pytest.fixture
def card(tmp_path, monkeypatch):
    """Boot profiles/default.py on a card whose /data is <tmp>/data; returns (hplayer, player, played, data)."""
    monkeypatch.setattr(Settings, '_settings', copy.deepcopy(DEFAULTS))
    data = tmp_path / 'data'
    (data / 'media').mkdir(parents=True)
    real = engine.HPlayer2

    def remap(p):
        return str(data / p[len('/data/'):]) if isinstance(p, str) and p.startswith('/data/') else p

    def _boot(media=(), before_run=None, stored=None):
        if stored is not None:
            (data / 'hplayer2.cfg').write_text(json.dumps(stored))
        for name in media:
            (data / 'media' / name).write_bytes(b'')
        made = {}

        def factory(mediaPath=None, config=None):
            hp = real(mediaPath=[remap(p) for p in mediaPath], config=remap(config),
                      datadir=str(tmp_path / 'hp'))
            player = StubPlayer()
            hp._players['player'] = player
            hp.addPlayer = lambda ptype, name: player       # no mpv
            hp.addInterface = lambda *a, **k: None          # no keyboard / OSC / http2 sockets
            listFiles = hp.files.listFiles
            hp.files.listFiles = lambda entries, origin=None: listFiles(
                [remap(e) for e in entries] if isinstance(entries, list) else remap(entries), origin)

            def run():                                      # run(): settings.load(), then app-run
                if before_run:
                    before_run(hp, player)
                hp.settings.load()
                hp.appRunning = True
                hp.emit('app-run')

            hp.run = run
            made.update(hplayer=hp, player=player, played=player.played)
            return hp

        monkeypatch.setattr(engine, 'HPlayer2', factory)
        runpy.run_path(str(PROFILE))
        return made['hplayer'], made['player'], made['played'], data

    return _boot


def test_a_blank_card_plays_its_clip_on_boot_and_loops_it(card):
    hplayer, _, played, data = card(['0_mire.mp4'])

    assert played == [str(data / 'media' / '0_mire.mp4')]
    assert hplayer.settings.get('loop') == 2                # loop all: one file loops in mpv
    hplayer.playlist.onMediaEnd()                            # the clip ends -> it plays again
    assert played[-1] == str(data / 'media' / '0_mire.mp4') and len(played) == 2


def test_every_file_of_the_media_folder_plays_in_order_then_wraps(card):
    hplayer, _, played, data = card(['02_b.mp4', '01_a.mp4'])
    files = [str(data / 'media' / n) for n in ('01_a.mp4', '02_b.mp4')]

    assert hplayer.playlist.export() == files
    hplayer.playlist.onMediaEnd()
    hplayer.playlist.onMediaEnd()
    assert played == files + files[:1]


def test_a_stored_loop_off_or_old_playlist_does_not_keep_a_card_idle(card):
    # an earlier session over http2 turned the loop off and left a list whose file is gone
    hplayer, _, played, data = card(['0_mire.mp4'],
                                    stored={'loop': 0, 'playlist': ['/data/media/gone.mp4']})

    assert played == [str(data / 'media' / '0_mire.mp4')]
    assert hplayer.settings.get('loop') == 2


def test_a_card_with_no_media_waits_then_plays_what_arrives(card):
    hplayer, player, played, data = card([])
    assert played == []

    (data / 'media' / '0_mire.mp4').write_bytes(b'')         # an upload over http2, a copy into p3
    hplayer.files.refresh()                                  # what the folder watcher runs
    assert played == [str(data / 'media' / '0_mire.mp4')]


def test_new_media_never_interrupt_what_is_loaded(card):
    hplayer, player, played, data = card(['0_mire.mp4'])
    player.playing = True

    (data / 'media' / '1_new.mp4').write_bytes(b'')
    hplayer.files.refresh()
    assert len(played) == 1                                  # the loop keeps its list until the next boot

    player.playing = False                                   # stopped by hand: stays stopped
    hplayer.files.refresh()
    assert len(played) == 1


def test_a_media_event_before_app_run_plays_nothing(card):
    seen = []

    def early(hp, player):                                   # the folder watcher fires during boot
        hp.files.refresh()
        seen.append(list(hp.playlist.export()))
    _, _, played, _ = card(['0_mire.mp4'], before_run=early)

    assert seen == [[]]
    assert len(played) == 1                                  # app-run's play, once
