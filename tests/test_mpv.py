import os
from pathlib import Path

import core.players.mpv as mpv_module
from core.players.mpv import MpvPlayer


class DummyHPlayer:
    def __init__(self) -> None:
        self.events = []

    def autoBind(self, module) -> None:  # noqa: N802
        return None

    def emit(self, event: str, *args) -> None:
        self.events.append((event, args))


def test_resolve_mpv_binary_from_env(tmp_path, monkeypatch):
    hplayer = DummyHPlayer()
    player = MpvPlayer(hplayer, "test")

    env_bin = tmp_path / "mpv-bin"
    env_bin.write_text("")

    monkeypatch.setenv("HPLAYER_MPV_BIN", str(env_bin))
    assert player._resolve_mpv_binary() == str(env_bin)


def test_resolve_mpv_binary_uses_prebuild(tmp_path, monkeypatch):
    hplayer = DummyHPlayer()
    player = MpvPlayer(hplayer, "test")

    prebuild = tmp_path / "mpv-prebuild"
    prebuild.write_text("")

    monkeypatch.delenv("HPLAYER_MPV_BIN", raising=False)
    monkeypatch.setattr(mpv_module, "which", lambda _: None)

    original_exists = mpv_module.os.path.exists
    monkeypatch.setattr(
        mpv_module.os.path,
        "exists",
        lambda path: False if path == "/usr/local/bin/rkmpv" else original_exists(path),
    )

    monkeypatch.setattr(MpvPlayer, "_candidate_prebuilds", lambda self: [prebuild])

    assert player._resolve_mpv_binary() == str(prebuild)


def test_resolve_mpv_binary_failure(tmp_path, monkeypatch):
    hplayer = DummyHPlayer()
    player = MpvPlayer(hplayer, "test")

    monkeypatch.delenv("HPLAYER_MPV_BIN", raising=False)
    monkeypatch.setattr(mpv_module, "which", lambda _: None)
    monkeypatch.setattr(mpv_module.os.path, "exists", lambda path: False)
    monkeypatch.setattr(MpvPlayer, "_candidate_prebuilds", lambda self: [])

    try:
        player._resolve_mpv_binary()
    except RuntimeError as exc:  # pragma: no cover - intentional failure
        assert "mpv binary not found" in str(exc)
    else:  # pragma: no cover
        assert False, "Expected RuntimeError when mpv binary is missing"
