import core.players as playerlib
from core.engine.hplayer import HPlayer2


def test_add_player_handles_runtime_error(monkeypatch):
    hplayer = HPlayer2(basepath=[], settingspath=None)

    class FailingPlayer:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("backend missing")

    monkeypatch.setattr(playerlib, "getPlayer", lambda name: FailingPlayer)

    result = hplayer.addPlayer("mpv", "player")
    assert result is None
    assert "player" not in hplayer._players
