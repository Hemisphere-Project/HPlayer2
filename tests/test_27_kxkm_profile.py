"""profiles/27-kxkm.py: a KXKM 7.5 card behaves like today's 6.x player (hplayer2#t-107).

Today's fleet runs profiles/sacvp.py from branch sacvp-kernel4-2025. 27-kxkm ports it onto
master and keeps 25-kxkm's 7.5 additions (/boot/hplayer2.conf, etendard, group.json, LPD8 pad).
The decisions under test: the show folder comes from the file name (/data/sync/27-kxkm), the
card waits for a cue at boot, the USB numeric keypad drives the Régie and the whole fleet, OSC
goes out on 3737, an M5 on USB serial, the fade overlay — and a missing fade library never stops
the player.

The real profile file runs on the real HPlayer2 (Settings, Playlist, FileManager, events). /data
is a tmp folder; players, sampler and interfaces are stubs that record what they were given.
"""
import builtins
import copy
import json
import pathlib
import runpy

import pytest

import core.engine.hplayer as engine
from core.engine import bootconf, network
from core.engine.settings import Settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles' / '27-kxkm.py'
DEFAULTS = copy.deepcopy(Settings._settings)


class StubPlayer:
    def __init__(self, ptype, overlay_error=None):
        self.ptype = ptype
        self.played = []
        self.overlays = []
        self.overlay_error = overlay_error

    def validExt(self, f):
        return f.endswith(('.mp4', '.wav'))

    def isPlaying(self):
        return bool(self.played)

    def play(self, media, *a, **k):
        self.played.append(media)

    def stop(self, *a, **k):
        pass

    def addOverlay(self, name):
        if self.overlay_error:
            raise self.overlay_error
        self.overlays.append(name)

    def setSize(self, *a):
        self.size = a

    def setIP(self, ip):
        self.ip = ip


class StubSampler:
    def __init__(self):
        self.players = [StubPlayer('jp'), StubPlayer('jp')]
        self.played = []

    def playerAt(self, i):
        return self.players[i]

    def play(self, media, oneloop=False, index=-1):
        self.played.append((media, oneloop, index))

    def stop(self, *a, **k):
        self.played.append('stop')


class StubNode:
    uuid = 'me'

    def __init__(self):
        self.sent = []

    def broadcast(self, event, args=None, delay_ms=0, **k):
        self.sent.append(('broadcast', event, args, delay_ms))


class StubInterface:
    def __init__(self, name, args):
        self.name = name
        self.args = args
        self.node = StubNode()
        self.sent = []
        self.seqs = []

    def send(self, path, *args):                    # osc
        self.sent.append((path, args))

    def playseq(self, scene, seq):                  # regie
        self.seqs.append((scene, seq))


class Hartnet:
    made = []

    def __init__(self, host, port):
        self.addr = (host, port)
        self.sent = []
        Hartnet.made.append(self)

    def send_message(self, path, value):
        self.sent.append((path, value))


@pytest.fixture
def card(tmp_path, monkeypatch):
    """Boot profiles/27-kxkm.py on a card named Whisky whose /data is <tmp>/data."""
    monkeypatch.setattr(Settings, '_settings', copy.deepcopy(DEFAULTS))
    monkeypatch.setattr(network, 'get_hostname', lambda: 'Whisky')
    monkeypatch.setenv(bootconf.ENV_PATH, str(tmp_path / 'boot' / 'hplayer2.conf'))
    pythonosc = pytest.importorskip('pythonosc.udp_client')
    Hartnet.made = []
    monkeypatch.setattr(pythonosc, 'SimpleUDPClient', Hartnet)
    data = tmp_path / 'data'
    show = data / 'sync' / '27-kxkm'
    show.mkdir(parents=True)
    real = engine.HPlayer2
    real_open = builtins.open

    def remap(p):
        return str(data / p[len('/data/'):]) if isinstance(p, str) and p.startswith('/data/') else p

    # the profile opens etendard.json / group.json by their absolute /data path
    monkeypatch.setattr(builtins, 'open', lambda f, *a, **k: real_open(remap(f), *a, **k))

    def _boot(conf=None, files=(), etendard=None, rpi=False, overlay_error=None):
        if conf is not None:
            (tmp_path / 'boot').mkdir(exist_ok=True)
            (tmp_path / 'boot' / 'hplayer2.conf').write_text(conf)
        for name in files:
            (show / name).parent.mkdir(parents=True, exist_ok=True)
            (show / name).write_bytes(b'')
        if etendard is not None:
            (show / 'etendard.json').write_text(json.dumps(etendard))
        made = {'players': {}, 'interfaces': {}}

        def factory(mediaPath=None, config=None):
            made['mediaPath'], made['config'] = mediaPath, config
            hp = real(mediaPath=[remap(p) for p in mediaPath], config=remap(config),
                      datadir=str(tmp_path / 'hp'))
            hp.isRPi = lambda: rpi

            def addPlayer(ptype, name):
                made['players'][name] = hp._players[name] = StubPlayer(ptype, overlay_error)
                return made['players'][name]

            def addInterface(name, *args):
                made['interfaces'][name] = StubInterface(name, args)
                return made['interfaces'][name]

            made['sampler'] = StubSampler()
            hp.addPlayer = addPlayer
            hp.addSampler = lambda *a: made['sampler']
            hp.addInterface = addInterface
            hp.interface = lambda name: made['interfaces'].get(name)

            def run():                                      # run(): settings.load(), then app-run
                hp.settings.load()
                hp.appRunning = True
                hp.emit('app-run')

            hp.run = run
            made['hplayer'] = hp
            return hp

        monkeypatch.setattr(engine, 'HPlayer2', factory)
        runpy.run_path(str(PROFILE))
        return made

    return _boot


def test_the_show_folder_is_27_kxkm_and_settings_live_on_data(card):
    made = card()
    assert made['mediaPath'] == ['/data/usb', '/data/sync/27-kxkm', '/data/sync/solo/Whisky']
    assert made['config'] == '/data/hplayer2-27-kxkm.cfg'
    assert made['interfaces']['regie'].args == (9111, '/data/sync/27-kxkm')


def test_it_waits_for_a_cue_at_boot(card):
    made = card(files=['01_intro.mp4'])
    hp = made['hplayer']
    assert made['players']['video'].played == []            # 25-kxkm played item 0 here
    assert hp.settings.get('volume') == 100
    assert hp.settings.get('loop') == 1


def test_the_6x_interfaces_are_on(card):
    i = card()['interfaces']
    assert i['keyboard'].args == ()                          # USB numeric keypad
    assert i['osc'].args == (1222, 3737)                     # out 3737 on the broadcast address
    assert i['serial'].args == ('M5', 10)
    assert i['mqtt'].args == ('10.0.0.2',)
    assert i['http2'].args == (8080,)
    assert 'teleco' in i
    assert i['midictrl'].args == ('LPD8', 10)               # 25-kxkm's pad stays


def test_the_keypad_plays_the_regie_sequence(card):
    made = card()
    hp, regie = made['hplayer'], made['interfaces']['regie']
    hp.emit('keyboard.KEY_KP3-down')
    assert regie.seqs == [(hp.files.currentIndex(), 2)]


def test_dot_held_selects_a_scene_without_playing(card):
    made = card()
    hp, regie = made['hplayer'], made['interfaces']['regie']
    hp.emit('keyboard.KEY_KPDOT-down')
    hp.emit('keyboard.KEY_KP2-down')
    hp.emit('keyboard.KEY_KPDOT-up')
    assert regie.seqs == []


def test_enter_and_plus_minus_reach_the_whole_fleet_at_once(card):
    made = card()
    hp, node = made['hplayer'], made['interfaces']['zyre'].node
    hp.emit('keyboard.KEY_KPENTER-down')
    hp.emit('keyboard.KEY_KPPLUS-down')
    hp.emit('keyboard.KEY_KPMINUS-hold')
    assert node.sent == [('broadcast', 'stop', [], 0),       # master's broadcast dropped these
                         ('broadcast', 'volume', [101], 0),
                         ('broadcast', 'volume', [99], 0)]


def test_the_mesh_binds_the_conf_iface_or_zyres_own_choice(card):
    assert card()['interfaces']['zyre'].args == (None,)


def test_a_conf_iface_pins_the_mesh(card):
    assert card(conf='[sync]\niface = eth0\n')['interfaces']['zyre'].args == ('eth0',)


def test_the_fade_overlay_is_on_a_pi(card):
    assert card(rpi=True)['players']['video'].overlays == ['rpifade']


def test_a_missing_fade_library_does_not_stop_the_player(card):
    made = card(rpi=True, overlay_error=OSError('libdrm.so: cannot open shared object file'))
    assert made['players']['video'].overlays == []
    assert made['hplayer'].settings.get('volume') == 100      # booted to app-run all the same


def test_the_lpd8_lights_go_to_the_local_hartnet_not_the_show_osc(card):
    made = card(files=['ZZ_AUDIOLOOP/a.wav'])
    hp = made['hplayer']
    hp.emit('midictrl.noteon', {'note': 40})
    assert made['sampler'].played[-1][1:] == (True, 0)       # loop 1 on sampler 0
    assert made['sampler'].played[-1][0].endswith('ZZ_AUDIOLOOP/a.wav')
    (hartnet,) = Hartnet.made
    assert hartnet.addr == ('127.0.0.1', 9000)
    assert hartnet.sent == [('/hartnet/play', [1])]
    assert made['interfaces']['osc'].sent == []


def test_an_etendard_runs_artnet_on_wint_and_ignores_the_pad(card):
    made = card(etendard={'Whisky': {'size': [16, 32], 'snake': True, 'vflip': False,
                                      'hflip': False, 'ip': '10.0.9.200'}})
    video = made['players']['video']
    assert video.ptype == 'videonet' and video.ip == '10.0.9.200'
    assert made['interfaces']['zyre'].args == ('wint',)
    made['hplayer'].emit('midictrl.noteon', {'note': 40})    # no sampler: 25-kxkm raised NameError
