"""HDMI output-mode matching for the LEGACY Pi stack (`tvservice` + dispmanx).

A display can only lock onto the timing it is given, so choosing the mode is the
*source's* job — what every Blu-ray player, Apple TV and Kodi does at each media start.
The legacy Pi image instead fixes the mode at boot (`/boot/config.txt`, or the EDID's
preferred mode, ~always 60 Hz) and mpv fits the file onto that refresh: 25 fps becomes a
2-3-2-3 pull-down, 24 fps a 3:2. A TV hides it behind interpolation; a projector does not,
and it gets reported as "slight lag" (two solo players on a Panasonic PT-RZ970, 2026-09-10).

Everything down to `switch()` is pure and unit-tested; only `current_mode()`/`switch()`
shell out. `tvservice` absent (x86, or any KMS image) → every call is a no-op, exactly as
Pi-tools' `hdmi-rehandshake` exits 0 under KMS.

This does NOT replace `hdmi-rehandshake`, which re-negotiates the boot-time link; it runs
after it. Nor does it deprecate persisting one mode per card in `/boot/config.txt` — that
still covers a one-file player and is what ran on the 2026-09-10 fleet.
"""

import shutil
import subprocess

# The 1080p CEA modes this may select, and what each one actually runs at. Kept small on
# purpose: a mode number carries no resolution, so scanning "every CEA mode" could drop a
# 1080p player to 720p (mode 4) to chase a refresh rate.
CEA_HZ = {
    16: 60,         # 1920x1080 @ 60
    31: 50,         # 1920x1080 @ 50
    32: 24,         # 1920x1080 @ 24
    34: 30,         # 1920x1080 @ 30
}

# content fps -> the mode to ask for. 25 fps deliberately takes the 50 Hz mode (a clean
# 2:2, every frame shown twice) rather than a 25 Hz one: judder-free, and far more widely
# accepted. The EDID stays the authority — a mode is used only if `tvservice -m CEA`
# actually offers it.
FPS_TO_MODE = {
    24: 32,         # also 23.976 — see drift_seconds(), the link runs 24.000 exactly
    25: 31,
    30: 34,         # also 29.97
    50: 31,
    60: 16,
}

# How close a measured container-fps must sit to its NEAREST table entry to count as that
# rate. 0.5% admits the /1.001 NTSC pull-downs (23.976->24, 29.97->30, off by 0.1%) and
# rejects everything else, which is the point: an unrecognised rate must fall through to
# "keep the current mode", never get rounded onto a neighbour. Loosening this to a few
# percent would start driving e.g. a 23 fps file at 24 Hz.
FPS_TOLERANCE = 0.005


def _nominal(fps):
    """Snap a measured fps onto the nominal rate it represents, or None."""
    try:
        fps = float(fps)
    except (TypeError, ValueError):
        return None
    if fps <= 0:
        return None
    rate = min(FPS_TO_MODE, key=lambda r: abs(fps - r))
    return rate if abs(fps - rate) <= rate * FPS_TOLERANCE else None


def parse_modes(text):
    """Mode numbers offered by `tvservice -m CEA`.

    Lines look like:
               mode 16: 1920x1080 @ 60Hz 16:9, clock:148MHz progressive
      (prefer) mode 31: 1920x1080 @ 50Hz 16:9, clock:148MHz progressive

    The `(prefer)` marker sits BEFORE the keyword, so match on 'mode' anywhere in the
    leader — dropping that line would discard the display's preferred mode, the one most
    likely to be the right answer.
    """
    modes = []
    for line in (text or '').splitlines():
        parts = line.split()
        if 'mode' not in parts:
            continue
        try:
            modes.append(int(parts[parts.index('mode') + 1].rstrip(':')))
        except (IndexError, ValueError):
            continue
    return modes


def pick_mode(fps, offered):
    """(mode, why) for a container fps against the modes the EDID offers.

    Falls back, in order: the exact rate -> the nearest integer multiple of it (a 25 fps
    file on a 50 Hz link is a clean 2:2, no pull-down) -> (None, why) = keep the current
    mode. Never invents a mode the display did not advertise.
    """
    offered = list(offered or [])
    rate = _nominal(fps)
    if rate is None:
        return None, 'fps %s matches no known rate' % (fps,)

    def described(mode):
        hz = CEA_HZ[mode]
        factor = hz // rate
        return mode, 'CEA %d = %d Hz, %d:%d on %d fps' % (mode, hz, factor, factor, rate)

    preferred = FPS_TO_MODE[rate]
    if preferred in offered:
        return described(preferred)

    # the display does not have it: take the lowest offered mode whose refresh is a WHOLE
    # multiple of the content rate — still judder-free, just repeating each frame more.
    # Whole multiples only: 24 fps has no 48 Hz CEA mode, and 50 Hz is not one of its
    # multiples, so a 24 fps file keeps the current mode rather than pull-down again.
    fits = sorted(m for m in offered if m in CEA_HZ and CEA_HZ[m] % rate == 0)
    if fits:
        return described(min(fits, key=lambda m: CEA_HZ[m]))

    return None, 'no CEA mode offered for %d fps (have %s) — keeping the current one' % (
        rate, ','.join(str(m) for m in offered) or 'none')


def drift_seconds(fps):
    """Seconds between dropped/repeated frames once the file is on its matched mode, or
    None when the match is exact.

    The table sends 23.976 and 24 both to CEA 32, which is 24.000 Hz: an NTSC-film file
    diverges one frame every ~41.7 s — on a loop, a visible tick. The firmware may or may
    not offer the /1.001 variant; `tvservice -m CEA` is what settles it on the projector.
    So: report the residual rather than call CEA 32 an exact match.
    """
    rate = _nominal(fps)
    if rate is None:
        return None
    try:
        fps = float(fps)
    except (TypeError, ValueError):
        return None
    delta = abs(rate - fps)
    if delta < 1e-9:
        return None
    return 1.0 / delta


def _tvservice(*args):
    """`tvservice` stdout, or None when the binary is absent or fails (KMS, x86)."""
    binary = shutil.which('tvservice')
    if not binary:
        return None
    try:
        return subprocess.run([binary] + list(args), capture_output=True,
                              universal_newlines=True, timeout=10).stdout
    except (subprocess.SubprocessError, OSError):
        return None


def offered_modes():
    """CEA mode numbers this display advertises. Empty when tvservice is unavailable."""
    return parse_modes(_tvservice('-m', 'CEA'))


def current_mode():
    """The CEA mode number the link is running now, or None.

    `tvservice -s` reports e.g.:
        state 0x12000a [HDMI CEA (16) RGB lim 16:9], 1920x1080 @ 60.00Hz, progressive
    """
    out = _tvservice('-s') or ''
    if 'CEA' not in out:
        return None            # DMT (the RastaOS 7.3 golden's default) or no signal
    try:
        return int(out.split('CEA', 1)[1].split('(', 1)[1].split(')', 1)[0])
    except (IndexError, ValueError):
        return None


def switch(mode, group='CEA', signal='HDMI'):
    """Drive the link onto `mode`. True when tvservice accepted it.

    The `fbset` depth dance is Pi-tools' `hdmi-rehandshake` verbatim: `tvservice -e` powers
    the output off and on, which leaves the framebuffer needing a poke. NOTE it has only
    ever run as a boot-time oneshot, *before* the player starts — whether a live mpv
    re-attaches to the fresh link is hardware, and is what ② settles on a projector.
    """
    if _tvservice('-e', '%s %d %s' % (group, mode, signal)) is None:
        return False
    for depth in ('8', '32'):
        fbset = shutil.which('fbset')
        if not fbset:
            break
        try:
            subprocess.run([fbset, '-depth', depth], capture_output=True, timeout=10)
        except (subprocess.SubprocessError, OSError):
            pass
    return True
