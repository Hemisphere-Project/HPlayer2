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


# ---------------------------------------------------------------------------
# mono/pan matrix builder (channel-aware since the always-on audio graph)
# ---------------------------------------------------------------------------

def test_pan_filter_stereo_untouched():
    # historical strings, byte-for-byte: fleet behavior must not move
    assert (mpv_module.build_pan_filter('mono', 2)
            == "lavfi=[pan=stereo|c0=.5*c0+.5*c1|c1=.5*c0+.5*c1]")
    assert (mpv_module.build_pan_filter([100, 100], 2)
            == "lavfi=[pan=stereo|c0=1.0*c0|c1=1.0*c1]")
    assert (mpv_module.build_pan_filter([50, 100], 2)
            == "lavfi=[pan=stereo|c0=0.5*c0|c1=1.0*c1]")


def test_pan_filter_unknown_channels_assume_stereo():
    assert (mpv_module.build_pan_filter('mono', None)
            == mpv_module.build_pan_filter('mono', 2))


def test_pan_filter_multichannel_mono():
    af = mpv_module.build_pan_filter('mono', 8)
    assert af.startswith("lavfi=[pan=8c|")
    # every output carries the same equal-weight mix of all 8 inputs
    outs = af[len("lavfi=[pan=8c|"):-1].split('|')
    assert len(outs) == 8
    assert all(o.split('=', 1)[1] == outs[0].split('=', 1)[1] for o in outs)
    assert "0.1250*c7" in outs[0]


def test_pan_filter_multichannel_unity_passthrough():
    assert mpv_module.build_pan_filter([100, 100], 8) == ""


def test_pan_filter_multichannel_balance_refused():
    assert mpv_module.build_pan_filter([50, 100], 6) is None
