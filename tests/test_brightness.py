from core.engine.hplayer import HPlayer2


def test_brightness_sliders_follow_player_capability():
    import core.interfaces.http2 as http2mod
    hplayer = HPlayer2(mediaPath=[])

    class HdmiPlayer:                                   # mpv & co: the events are logged and dropped
        def hasSurface(self): return False
        def hasBrightness(self): return False

    class VideonetPlayer:                               # the numpy matrix pass applies them
        def hasSurface(self): return False
        def hasBrightness(self): return True

    iface = http2mod.Http2Interface.__new__(http2mod.Http2Interface)
    iface.hplayer = hplayer
    iface.conf = {'brightness': None}
    hplayer._players = {'a': HdmiPlayer()}
    assert iface.config()['brightness'] is False        # no backend drives them: no sliders
    hplayer._players = {'a': HdmiPlayer(), 'b': VideonetPlayer()}
    assert iface.config()['brightness'] is True         # videonet present: sliders back
    iface.conf = {'brightness': False}
    assert iface.config()['brightness'] is False        # a profile may force them off
    iface.conf = {'brightness': True}
    hplayer._players = {'a': HdmiPlayer()}
    assert iface.config()['brightness'] is True         # ...or on, against the capability


def test_backends_that_no_op_report_no_brightness():
    # videonet's own True is not asserted here: the module imports stupidArtnet and cv2
    # at load time and neither is a declared dependency, so it cannot be collected.
    from core.players.base import BasePlayer
    from core.players.mpv import MpvPlayer
    assert BasePlayer.hasBrightness(object()) is False
    assert MpvPlayer.hasBrightness(object()) is False
