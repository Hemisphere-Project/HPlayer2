"""
settings.load() replays every stored key as do-<key>, and hplayer's own do-playlist binding runs
playlist.load(<stored value>). A profile that builds its list at import (anna.py, etendard.py,
radartest.py, teleco2test.py: `hplayer.playlist.load(hplayer.files.currentList())`) did so before
the settings were ready, so set() dropped it and the replay used to clobber it: None on a fresh card
emptied it (Anna-01, 2026-11-06: LCD 0/0, next/play dead), a stale stored list replaced it.

The real HPlayer2 (autoBind), Settings, Playlist and FileManager; only the player is a stub (idle).
"""
import copy
import json

import pytest

from core.engine.hplayer import HPlayer2
from core.engine.settings import Settings

# Settings keeps its values on the class, and load() writes into that dict (test_settings.py leaves
# autoplay True there): every boot starts from the defaults as they stood at collection
DEFAULTS = copy.deepcopy(Settings._settings)


class IdlePlayer:
    def validExt(self, f):
        return f.endswith('.mp4')

    def isPlaying(self):
        return False


@pytest.fixture
def media(tmp_path):
    folder = tmp_path / 'media'
    folder.mkdir()
    files = []
    for name in ('01_intro.mp4', '02_loop.mp4', '03_end.mp4'):
        f = folder / name
        f.write_bytes(b'')
        files.append(str(f))
    return folder, files


@pytest.fixture
def boot(tmp_path, monkeypatch):
    """A fresh player on <tmp>/hplayer2.cfg, holding `stored` (absent = a fresh card)."""
    monkeypatch.setattr(Settings, '_settings', copy.deepcopy(DEFAULTS))
    cfg = tmp_path / 'hplayer2.cfg'

    def _boot(stored=None):
        if stored is not None:
            cfg.write_text(json.dumps(stored))
        hplayer = HPlayer2(mediaPath=[], config=str(cfg), datadir=str(tmp_path / 'data'))
        hplayer._players['player'] = IdlePlayer()   # no addPlayer(): its bindings need a real mpv
        return hplayer, cfg

    return _boot


def stored_playlist(cfg):
    return json.loads(cfg.read_text())['playlist']


def test_fresh_card_keeps_the_import_list_and_stores_it(boot, media):
    _, files = media
    hplayer, cfg = boot()
    hplayer.playlist.load(files)                    # the profile, at import
    hplayer.settings.load()                         # run(), just before app-run

    assert hplayer.playlist.export() == files
    assert hplayer.settings.get('playlist') == files
    assert stored_playlist(cfg) == files


def test_stored_none_does_not_empty_the_import_list(boot, media):
    _, files = media
    hplayer, cfg = boot({'playlist': None, 'volume': 80})
    hplayer.playlist.load(files)
    hplayer.settings.load()

    assert hplayer.playlist.export() == files
    assert hplayer.settings.get('volume') == 80     # the other keys still replay
    assert stored_playlist(cfg) == files


def test_stale_stored_list_does_not_replace_the_import_list(boot, media):
    folder, files = media
    gone = folder / '00_removed.mp4'
    gone.write_bytes(b'')
    hplayer, cfg = boot({'playlist': [str(gone), files[0]]})
    gone.unlink()                                   # rsync --delete (a USB sync) since last boot
    hplayer.playlist.load(files)
    hplayer.settings.load()

    assert hplayer.playlist.export() == files
    assert stored_playlist(cfg) == files


def test_loaded_and_updated_carry_the_kept_list(boot, media):
    _, files = media
    hplayer, _ = boot({'playlist': None})
    seen = {}
    hplayer.settings.on('loaded', lambda ev, s: seen.__setitem__('loaded', s['playlist']))
    hplayer.playlist.load(files)
    hplayer.settings.load()

    assert seen['loaded'] == files


def test_no_import_list_still_restores_the_stored_one(boot, media):
    _, files = media
    hplayer, _ = boot({'playlist': files[1:]})      # a profile that relies on the stored list
    hplayer.settings.load()

    assert hplayer.playlist.export() == files[1:]


def test_a_live_playlist_set_after_boot_still_loads(boot, media):
    _, files = media
    hplayer, cfg = boot({'playlist': None})
    hplayer.playlist.load(files)
    hplayer.settings.load()

    hplayer.settings.set('playlist', files[:1])     # http2 / an order, after app-run
    assert hplayer.playlist.export() == files[:1]
    assert stored_playlist(cfg) == files[:1]


def test_a_second_load_restores_the_stored_list(boot, media):
    _, files = media
    hplayer, cfg = boot({'playlist': None})
    hplayer.playlist.load(files)
    hplayer.settings.load()
    assert not hplayer.settings.loading()
    assert not hplayer.settings.setEarly('playlist')

    cfg.write_text(json.dumps({'playlist': files[2:]}))
    hplayer.settings.load()                         # nothing was set early this time
    assert hplayer.playlist.export() == files[2:]
