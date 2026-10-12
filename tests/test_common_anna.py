import importlib
import sys
from unittest.mock import MagicMock

import pytest

import core.engine.hplayer as hplayermod
import profiles._common_anna as common
from profiles._common_anna import StatusLCD

LONG = '/data/media/03_la_grande_traversee.mp4'     # 22 chars once stripped: scrolls


class FakeLCD:
    def __init__(self):
        self.color = None

    def set_color(self, r, g, b):
        self.color = (r, g, b)


class FakeKeypad:
    CHAR_WIFI, CHAR_PEERS, CHAR_VOL, CHAR_PLAY, CHAR_STOP, CHAR_LOVE = 'WPV>#L'

    def __init__(self):
        self.lcd = FakeLCD()
        self.emitted = []

    def emit(self, event, *args):
        self.emitted.append(event)

    def draw(self, lines):
        pass


class Stage:
    """What the LCD reads: the player, the playlist, the volume, the wifi."""
    def __init__(self):
        self.media = None
        self.position = 0.0
        self.essid = 'parc'
        self.rssi = 80

        self.player = MagicMock()
        self.player.status.side_effect = lambda: {'media': self.media}
        self.player.position.side_effect = lambda: self.position

        self.hplayer = MagicMock()
        self.hplayer.playlist.index.return_value = 0
        self.hplayer.playlist.size.return_value = 3
        self.hplayer.settings.get.return_value = 50
        self.hplayer.addPlayer.return_value = self.player

        self.keypad = FakeKeypad()
        self.zyre = MagicMock()
        self.zyre.activeCount.return_value = 3
        self.interfaces = {'keypad': self.keypad, 'zyre': self.zyre}
        self.hplayer.addInterface.side_effect = lambda name, *a: self.interfaces.get(name, MagicMock())

        self.handlers = {}
        def on(event, *fn):
            if fn:
                self.handlers[event] = fn[0]
                return None
            def deco(f):
                self.handlers[event] = f
                return f
            return deco
        self.hplayer.on.side_effect = on
        self.hplayer.files.on.side_effect = on

    def fire(self, event):
        return self.handlers[event](event)


class NowTimer:
    def __init__(self, delay, fn):
        self.fn = fn

    def start(self):
        self.fn()


@pytest.fixture
def stage(monkeypatch):
    s = Stage()
    monkeypatch.setattr(common.network, 'get_essid', lambda iface: s.essid)
    monkeypatch.setattr(common.network, 'get_rssi', lambda iface: s.rssi)
    monkeypatch.setattr(common, 'Timer', NowTimer)
    return s


def load_profile(name, stage, monkeypatch):
    """Import profiles/<name>.py against the stage — HPlayer2 faked, run() returns at once."""
    monkeypatch.setattr(hplayermod, 'HPlayer2', lambda *a, **kw: stage.hplayer)
    monkeypatch.setattr('time.sleep', lambda s: None)
    monkeypatch.delitem(sys.modules, 'profiles.' + name, raising=False)
    return importlib.import_module('profiles.' + name)


# StatusLCD
#
def test_stopped_shows_position_volume_wifi(stage):
    lcd = StatusLCD(stage.hplayer, stage.player, stage.keypad)
    assert lcd.update() == ['#1/3'.ljust(16), 'V50   W80%   ']
    assert stage.keypad.lcd.color == (100, 100, 100)


def test_playing_scrolls_the_media_name(stage):
    lcd = StatusLCD(stage.hplayer, stage.player, stage.keypad)
    stage.media = LONG
    assert lcd.update()[0] == '>1/3 03_la_grand'
    stage.position = 3.0                            # 3.0 * 3.08 - 1.5 * 3.08 → 4 chars in
    assert lcd.update()[0] == '>1/3 a_grande_tr'
    assert stage.keypad.lcd.color == (0, 100, 0)


def test_no_wifi_flashes_blue_once_per_blink_cycle(stage):
    lcd = StatusLCD(stage.hplayer, stage.player, stage.keypad)
    stage.essid = None
    colors = []
    for _ in range(common.blinkSpeed):
        lines = lcd.update()
        colors.append(stage.keypad.lcd.color)
    assert lines[1] == 'V50   W---% '
    assert colors[:-1] == [(100, 100, 100)] * (common.blinkSpeed - 1)
    assert colors[-1] == (0, 0, 100)


def test_held_select_restarts(stage):
    lcd = StatusLCD(stage.hplayer, stage.player, stage.keypad)
    lcd.holdCounter = 11
    assert lcd.update() == ['.:: HPlayer2 ::.', '   restarting   ']
    assert stage.keypad.emitted == ['hardreset']
    assert lcd.update() == ['.:: HPlayer2 ::.', '   restarting   ']
    assert stage.keypad.emitted == ['hardreset']    # once
    assert stage.keypad.lcd.color == (100, 0, 0)


def test_overlay_preempts_and_suffix_extends_line_1(stage):
    screen = None
    lcd = StatusLCD(stage.hplayer, stage.player, stage.keypad,
                    overlay=lambda: screen, suffix=lambda: 'P3  ')
    assert lcd.update()[1] == 'V50   W80%   P3  '
    screen = ['overlay', '']
    assert lcd.update() == ['overlay', '']


# The two profiles on it
#
@pytest.mark.parametrize('name, line1', [
    ('anna', 'V50   W80%   P3  '),                 # + Zyre peers
    ('25-annatv', 'V50   W80%   '),
])
def test_profile_draws_the_shared_status(name, line1, stage, monkeypatch):
    profile = load_profile(name, stage, monkeypatch)
    assert isinstance(profile.lcd, StatusLCD)
    assert stage.keypad.update == profile.lcd.update
    assert stage.keypad.update() == ['#1/3'.ljust(16), line1]
    stage.hplayer.run.assert_called_once()


def test_anna_keylock_alert_preempts_the_status(stage, monkeypatch):
    anna = load_profile('anna', stage, monkeypatch)
    anna.canToggle = False
    stage.fire('keypad.left')                       # locked at boot → alert
    assert stage.keypad.update() == ['... Locked ! ...', ' ' * 16]
    for _ in range(9):
        stage.keypad.update()
    assert stage.keypad.update()[1] == 'V50   W80%   P3  '
    assert anna.canToggle


def test_anna_select_hold_restarts_when_unlocked(stage, monkeypatch):
    anna = load_profile('anna', stage, monkeypatch)
    anna.keylock = False
    for _ in range(11):
        stage.fire('keypad.select-hold')
    assert anna.lcd.holdCounter == 11
    assert stage.keypad.update() == ['.:: HPlayer2 ::.', '   restarting   ']
    assert stage.keypad.emitted == ['hardreset']
