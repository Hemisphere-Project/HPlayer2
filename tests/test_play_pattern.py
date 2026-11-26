"""The biennale boot loop is every media but the 1_..9_ one-shots, and a pattern names what it drops
(hplayer2#t-058).

Files reads a playlist pattern as a regex (`*` -> `.*`). The old "[^1-9_]*.*" was written as a glob,
so its leading class dropped EVERY name starting with 1-9 or `_`: building sarachang-74 for MAC Lyon
(2026-09-13), the artist's `4MONTHS_1080p25.mp4` never played from boot, and the log said only
"Play list empty". The 2026-11-10 review: the loop is « every file except the N_ one-shots », and each
file a pattern drops is logged.

The real FileManager lists a tmp media folder; the patterns are read from profiles/biennale.py itself.
"""
import ast
import pathlib

import pytest

import core.engine.hplayer as engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles' / 'biennale.py'

LOOP = ['4MONTHS_1080p25.mp4', 'ambient.mp4', '01_cue.mp4', '10_ten.mp4', '_intro.mp4']
ONE_SHOTS = ['1_piece.mp4', '9_last.mp4']
NOT_MEDIA = ['.hidden.mp4', 'readme.txt']


def profile_constant(name):
    for node in ast.parse(PROFILE.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise LookupError(name)


PLAY_PATTERN = profile_constant('PLAY_PATTERN')
RADAR_PATTERN = profile_constant('RADAR_PATTERN')


class StubPlayer:
    def validExt(self, f):
        return f.endswith('.mp4')


@pytest.fixture
def card(tmp_path):
    """A player whose media folder holds the given names; returns (files, media dir)."""
    def _card(names):
        media = tmp_path / 'media'
        media.mkdir()
        for n in names:
            (media / n).write_bytes(b'')
        hp = engine.HPlayer2(mediaPath=[str(media)], config=str(tmp_path / 'hp.cfg'),
                             datadir=str(tmp_path / 'hp'))
        hp._players['player'] = StubPlayer()
        return hp.files, media
    return _card


def test_the_loop_is_every_media_but_the_one_shots(card):
    files, media = card(LOOP + ONE_SHOTS + NOT_MEDIA)

    loop = files.listFiles(PLAY_PATTERN)
    radar = files.listFiles(RADAR_PATTERN)

    assert loop == sorted(str(media / n) for n in LOOP)     # 4MONTHS_… plays from boot
    assert radar == sorted(str(media / n) for n in ONE_SHOTS)
    assert not set(loop) & set(radar)                         # the two sets split the card


def test_a_radar_only_card_still_has_an_empty_loop(card):
    # outdoor players carry only [1-9]_ pieces: silent until someone enters range
    files, _ = card(ONE_SHOTS)

    assert files.listFiles(PLAY_PATTERN) == []


def test_a_pattern_names_every_media_it_left_out(card, capsys):
    files, _ = card(LOOP + ONE_SHOTS + NOT_MEDIA)
    capsys.readouterr()

    files.listFiles(PLAY_PATTERN)
    said = [l for l in capsys.readouterr().out.splitlines() if 'left out' in l]

    assert len(said) == 1
    assert said[0].endswith("left out 2 media in %s: ['1_piece.mp4', '9_last.mp4']" % files.root_paths[0])


def test_a_pattern_that_drops_nothing_says_nothing(card, capsys):
    files, _ = card(LOOP)
    capsys.readouterr()

    files.listFiles(PLAY_PATTERN)

    assert 'left out' not in capsys.readouterr().out
