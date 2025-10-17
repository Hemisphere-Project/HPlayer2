from core.engine.playlist import Playlist


class DummySettings:
    def get(self, key):
        defaults = {"loop": 0}
        return defaults.get(key)

    def set(self, key, value):
        pass


class DummyFiles:
    def listFiles(self, playlist):
        return []

    def validExt(self, filename):
        return True


class DummyHPlayer:
    def __init__(self):
        self.events = []
        self.settings = DummySettings()
        self.files = DummyFiles()

    def autoBind(self, module):  # noqa: N802
        return None

    def emit(self, event, *args):
        self.events.append((event, args))


def test_playlist_index_navigation():
    hplayer = DummyHPlayer()
    playlist = Playlist(hplayer)
    playlist._playlist = ["track-a", "track-b", "track-c"]  # noqa: SLF001
    playlist._index = 1  # noqa: SLF001

    assert playlist.nextIndex() == 2
    assert playlist.prevIndex() == 0

    playlist._index = 2  # noqa: SLF001
    assert playlist.nextIndex() == 0
    assert playlist.prevIndex() == 1
