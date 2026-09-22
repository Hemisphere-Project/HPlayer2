from core.engine import hdmi


# ---------------------------------------------------------------------------
# tvservice output parsing
# ---------------------------------------------------------------------------

TVSERVICE_M_CEA = """Group CEA has 8 modes:
           mode 4: 1280x720 @ 60Hz 16:9, clock:74MHz progressive
           mode 16: 1920x1080 @ 60Hz 16:9, clock:148MHz progressive
  (prefer) mode 31: 1920x1080 @ 50Hz 16:9, clock:148MHz progressive
           mode 32: 1920x1080 @ 24Hz 16:9, clock:74MHz progressive
"""


def test_parse_modes_reads_the_mode_numbers():
    assert hdmi.parse_modes(TVSERVICE_M_CEA) == [4, 16, 31, 32]


def test_parse_modes_survives_junk():
    assert hdmi.parse_modes('') == []
    assert hdmi.parse_modes(None) == []
    assert hdmi.parse_modes('no displays found\nmode oops: garbage') == []


def test_current_mode_parses_the_state_line(monkeypatch):
    monkeypatch.setattr(hdmi, '_tvservice', lambda *a: (
        'state 0x12000a [HDMI CEA (16) RGB lim 16:9], 1920x1080 @ 60.00Hz, progressive'))
    assert hdmi.current_mode() == 16


def test_current_mode_is_none_off_cea(monkeypatch):
    # the RastaOS 7.3 golden ships hdmi_group=2 (DMT) — not a CEA mode at all
    monkeypatch.setattr(hdmi, '_tvservice', lambda *a: (
        'state 0xa [HDMI DMT (82) RGB full 16:9], 1920x1080 @ 60.00Hz, progressive'))
    assert hdmi.current_mode() is None
    monkeypatch.setattr(hdmi, '_tvservice', lambda *a: None)      # tvservice absent
    assert hdmi.current_mode() is None


# ---------------------------------------------------------------------------
# mode selection — the table, the multiple fallback, and keeping the current mode
# ---------------------------------------------------------------------------

ALL = [4, 16, 31, 32, 34]


def test_pick_mode_exact_match_per_rate():
    assert hdmi.pick_mode(25, ALL)[0] == 31
    assert hdmi.pick_mode(24, ALL)[0] == 32
    assert hdmi.pick_mode(30, ALL)[0] == 34
    assert hdmi.pick_mode(50, ALL)[0] == 31
    assert hdmi.pick_mode(60, ALL)[0] == 16


def test_pick_mode_snaps_the_ntsc_pulldowns():
    # the two rates that are not integers: they must reach the SAME mode as their nominal
    assert hdmi.pick_mode(23.976, ALL)[0] == 32
    assert hdmi.pick_mode(29.97, ALL)[0] == 34


def test_pick_mode_never_confuses_24_and_25():
    # the whole point: a 25 fps file driven at 24 Hz is worse than leaving it alone.
    # 0.5% tolerance must not bridge the 4% gap between the two rates.
    assert hdmi.pick_mode(25, [32])[0] is None          # only the 24 Hz mode offered
    assert hdmi.pick_mode(24, [31])[0] is None          # only the 50 Hz mode offered
    assert hdmi.pick_mode(23.976, [31])[0] is None


def test_pick_mode_falls_back_to_an_integer_multiple():
    # 25 fps on a 50 Hz link is a clean 2:2 — no pull-down
    mode, why = hdmi.pick_mode(25, [16, 31])
    assert mode == 31 and '2:2' in why
    # 30 fps on 60 Hz, likewise
    assert hdmi.pick_mode(30, [16])[0] == 16
    # 24 fps has NO integer multiple in the CEA table (48 Hz is not one), so it must
    # keep the current mode rather than land on 50
    assert hdmi.pick_mode(24, [16, 31])[0] is None


def test_pick_mode_keeps_current_when_nothing_fits():
    mode, why = hdmi.pick_mode(25, [])
    assert mode is None and 'keeping the current one' in why


def test_pick_mode_rejects_rubbish_fps():
    for bad in (None, 0, -1, 'abc', 12.5, 100):
        assert hdmi.pick_mode(bad, ALL)[0] is None


def test_pick_mode_rejects_a_near_miss_rather_than_rounding_it():
    # the tolerance admits the /1.001 pull-downs and nothing else: an unrecognised rate
    # must fall through to "keep the current mode", never round onto a neighbour.
    assert hdmi.pick_mode(23, ALL)[0] is None       # 4% off 24 — not an NTSC variant
    assert hdmi.pick_mode(26, ALL)[0] is None
    assert hdmi.pick_mode(48, ALL)[0] is None
    # the boundary itself: 0.5% of 24 is 0.12
    assert hdmi.pick_mode(24 - 0.10, ALL)[0] == 32
    assert hdmi.pick_mode(24 - 0.20, ALL)[0] is None


# ---------------------------------------------------------------------------
# the 23.976 residual (why the log must not call CEA 32 an exact match)
# ---------------------------------------------------------------------------

def test_drift_seconds_is_none_on_an_exact_rate():
    assert hdmi.drift_seconds(25) is None
    assert hdmi.drift_seconds(24) is None


def test_drift_seconds_reports_the_ntsc_film_tick():
    # 24 - 24/1.001 -> one frame every ~41.7 s on a 24.000 Hz link
    drift = hdmi.drift_seconds(24 / 1.001)
    assert drift is not None and 41 < drift < 42


def test_drift_seconds_ignores_rubbish():
    assert hdmi.drift_seconds('abc') is None
    assert hdmi.drift_seconds(0) is None


# ---------------------------------------------------------------------------
# no tvservice (x86 / any KMS image) = inert, exactly like hdmi-rehandshake under KMS
# ---------------------------------------------------------------------------

def test_inert_without_tvservice(monkeypatch):
    monkeypatch.setattr(hdmi.shutil, 'which', lambda _: None)
    assert hdmi.offered_modes() == []
    assert hdmi.current_mode() is None
    assert hdmi.switch(31) is False
