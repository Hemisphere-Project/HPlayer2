"""Teleco media page: the scroll walks the FILTERED list it shows and plays (sacvp 8140c23).

With a filter set (settings 'filter'), the page lists and A plays
`currentList(filtered=True)[offset + index]`; master's scrollUp computed its wrap on the
UNFILTERED list, so the first ▲ from the top put the cursor on hidden names and A played
another clip, or none. The scroll methods run unbound on a stub: no serial, no thread.
"""
import pytest

pytest.importorskip("serial")

from core.interfaces.teleco import TelecoInterface     # noqa: E402

# names chosen so no filter below also matches the folder: currentList(filtered=True) without
# `relative` filters the FULL path, so a filter that hits '/data/media/' keeps every clip
ALL = ['intro.mp4', 'fx1.mp4', 'nuit1.mp4', 'fx2.mp4', 'nuit2.mp4', 'nuit3.mp4', 'fx3.mp4']


class Files:
    def __init__(self, flt):
        self.flt = flt

    def currentList(self, relative=False, filtered=False):
        liste = list(ALL) if relative else ['/data/media/' + f for f in ALL]
        if filtered:
            return [f for f in liste if self.flt.lower() in f.lower()]
        return liste


class Page:
    scrollUp = TelecoInterface.scrollUp
    scrollDown = TelecoInterface.scrollDown

    def __init__(self, flt):
        self.hplayer = type('H', (), {})()
        self.hplayer.files = Files(flt)
        self.microIndex = 0
        self.microOffset = 0
        self.microList = self.hplayer.files.currentList(True, filtered=True)[:4]

    def cursor(self):
        return self.microList[self.microIndex]

    def played(self):       # what button A plays on the media page
        return self.hplayer.files.currentList(filtered=True)[self.microOffset + self.microIndex]


@pytest.mark.parametrize('flt', ['FX', '', 'nuit'])
def test_cursor_and_play_agree_all_the_way_round(flt):
    page = Page(flt)
    shown = page.hplayer.files.currentList(True, filtered=True)
    for move in [page.scrollUp] * 9 + [page.scrollDown] * 9:
        move()
        assert page.cursor() in shown
        assert page.played().endswith('/' + page.cursor())


def test_up_from_the_top_wraps_to_the_last_filtered_clip():
    page = Page('fx')
    page.scrollUp()
    assert page.cursor() == 'fx3.mp4' and page.played() == '/data/media/fx3.mp4'
