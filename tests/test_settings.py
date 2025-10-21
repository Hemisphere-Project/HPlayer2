import json
from pathlib import Path

from core.engine.settings import Settings


class DummyHPlayer:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple]] = []

    def autoBind(self, module) -> None:  # noqa: N802 (matching real API casing)
        return None

    def emit(self, event: str, *args) -> None:
        self.events.append((event, args))


def test_settings_load_and_persist(tmp_path: Path) -> None:
    cfg_path = tmp_path / "hplayer2.json"
    cfg_path.write_text(json.dumps({"volume": 50, "autoplay": True}))

    hplayer = DummyHPlayer()
    settings = Settings(hplayer, persistent=str(cfg_path))
    settings.load()

    assert settings.get("volume") == 50
    assert settings.get("autoplay") is True

    settings.set("volume", 40)
    assert settings.get("volume") == 40

    saved = json.loads(cfg_path.read_text())
    assert saved["volume"] == 40
    assert hplayer.events[-1][0] == "settings.updated"