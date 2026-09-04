from core.engine.hplayer import HPlayer2
from core.engine.settings import SURFACE_DEFAULTS, clean_surface


def test_clean_surface_coerces_and_falls_back():
    s = clean_surface({'enable': 'true', 'width': '256', 'rotate': '90', 'fit': 'BOGUS', 'halfheight': 1})
    assert s['enable'] is True and s['width'] == 256 and s['rotate'] == 90.0
    assert s['fit'] == 'cover' and s['halfheight'] is True
    assert clean_surface(None) == SURFACE_DEFAULTS


def test_surface_event_merges_partial_updates():
    hplayer = HPlayer2(mediaPath=[])
    hplayer.settings._ready = True              # no file, no players: just arm set()
    hplayer.emit('surface', {'width': 256, 'height': 512, 'enable': True})
    hplayer.emit('surface', {'halfheight': True})
    s = hplayer.settings.get('surface')
    assert s['width'] == 256 and s['height'] == 512 and s['halfheight'] is True and s['enable'] is True
    hplayer.emit('surface', '{"rotate": 45}')   # JSON string form (http / osc)
    assert hplayer.settings.get('surface')['rotate'] == 45.0
    hplayer.emit('unsurface')
    assert hplayer.settings.get('surface')['enable'] is False


def test_surface_card_follows_player_capability():
    import core.interfaces.http2 as http2mod
    hplayer = HPlayer2(mediaPath=[])

    class NoSurfacePlayer:
        def hasSurface(self): return False

    class LedPlayer:
        def hasSurface(self): return True

    iface = http2mod.Http2Interface.__new__(http2mod.Http2Interface)
    iface.hplayer = hplayer
    iface.conf = {'surface': None}
    hplayer._players = {'a': NoSurfacePlayer()}
    assert iface.config()['surface'] is False          # a Pi-style player: no card
    hplayer._players = {'a': NoSurfacePlayer(), 'b': LedPlayer()}
    assert iface.config()['surface'] is True           # mpv/x86 present: card shown
    iface.conf = {'surface': False}
    assert iface.config()['surface'] is False          # a profile may force it off
