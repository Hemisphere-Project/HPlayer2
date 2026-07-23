# mpv seek/speed benchmark → drifter v2 (smart jump)

Biennale de Lyon 2026 · 2026-07-23 · `bench-mpv.py` against
**mini-01** (Beelink N100, Ubuntu noble, mpv 0.37, `--hwdec=vaapi --vo=gpu-next`)
and **player-000** (RPi golden 7.1, Buster, mpv 0.33, `--hwdec=mmal --vo=rpi`),
127 records per host (`bench-mini.jsonl`, `bench-golden.jsonl`).

## Why

Sync joins were chaotic: jumps landed seconds from target, the servo hunted,
walls took a long time to converge — and behaviour differed wildly between
media files. Before redesigning the drifter, we measured the actuator it
drives: how mpv actually seeks and changes speed, per platform, per media.

## Strategy

Drive the exact production mpv invocation over its IPC socket and measure:

- **seek matrix**: ±2 / ±10 / ±40 s absolute seeks × `keyframes` vs `exact`
  mode; latency to `playback-restart` + landing error vs target;
- **speed matrix**: commanded 0.5–8×, achieved rate over 3 s + frame drops;
- **media set**: timecode-burned 1080p30/120 s files with controlled GOP —
  `tc_g30` (1 s), `tc_g60` (2 s), `tc_g60_noise` (2 s, noisy content),
  `tc_g240` (8 s), `tc_gone` (single keyframe) — plus the venue's
  `0_mire.mp4` (8.3 s GOP, 360 kbps).

Run: put media in `/data/bench-media/`, then on the device
`python3 bench-mpv.py <production mpv argv>` and collect the `BENCH:` lines.

## Observations

### 1. Landing error is mode-driven; the media sets the price

| media | keyframes med \|err\| | worst | exact med \|err\| | worst |
|---|---|---|---|---|
| GOP 1 s | 1.15 s | 1.15 s | 0.22 s | 0.22 s |
| GOP 2 s | 2.15 s | 2.15 s | 0.22 s | 0.22 s |
| GOP 8 s | 4.15 s | 8.15 s | 0.22 s | 0.23 s |
| 0_mire (8.3 s) | 3.82 s | 5.49 s | 0.23 s | 0.23 s |
| single KF | 12.15 s | **42.15 s** | 0.23 s | 0.23 s |

`keyframes` mode (HPlayer2's historic hardcoded seek flag — it even
overrides `--hr-seek=yes`) snaps to the GOP grid: the landing error IS the
keyframe interval. **Exact seeks land ~0.22 s early, constant, on both
platforms.** Identical numbers on vaapi and mmal.

Note: the 0.22 s is the bench-harness view (measured 0.15 s after
`playback-restart`); live on the wall the vaapi landing measured via the
wallclock servo is closer to the raw target (−0.33 s ahead with a 0.35 s
aim). Per-device landing bias differs from bench bias — which is exactly
why the drifter *learns* it instead of hardcoding it.

### 2. Exact-seek cost: free on vaapi, ~half the GOP on mmal

| media | vaapi med | worst | mmal med | worst |
|---|---|---|---|---|
| GOP 1 s | 0.02 s | 0.02 s | 0.38 s | 0.57 s |
| GOP 2 s | 0.05 s | 0.05 s | 0.88 s | 1.08 s |
| GOP 8 s | 0.09 s | 0.22 s | 1.81 s | 3.89 s |
| 0_mire (8.3 s) | 0.20 s | 0.21 s | 3.98 s | 4.00 s |
| single KF | 0.46 s | 1.72 s | 7.90 s | **28.88 s** |

Exact seeking decodes from the previous keyframe to the target. The N100
does this at >100× realtime; the RPi at ~2× realtime, so the cost is about
half the GOP. The cost is *predictable per file* — hence learnable.

### 3. Speed: mmal saturates at 2×

| commanded | vaapi achieved | mmal achieved |
|---|---|---|
| 0.5× | 0.54 | 0.54 |
| 1.2× | 1.18 | 1.18 |
| 2.0× | 1.92 | 1.92 |
| 4.0× | 3.71 | **2.01** |
| 8.0× | 7.31 | **2.02** |

Both track faithfully through the servo's working range (0.5–2×). Beyond
that the RPi decoder is the wall. Sprint-to-catch-up is pointless there.

No hangs were observed in any of the 254 records (the historic "hangs"
were keyframe-mode jumps landing half a minute away, then the servo
fighting a hopeless diff).

## What the drifter does with this (`core/engine/drifter.py`, danceMode)

Each mechanism is one benchmark fact, applied:

- **Jumps are exact seeks** aimed at `clock + learned latency`
  (`seekTo(..., exact=True)`; keyframe snapping was the join chaos).
- **The latency is learned**: the landing error — median of the first 3
  moving ticks, because mpv's first post-restart `time-pos` is an
  optimistic outlier — feeds an EMA (`_seekLatEst`, default 0.35 s,
  clamped 0.05–30 s). On mmal the second jump already aims with the
  measured decode cost; **no re-jump while a measurement is pending**,
  or the chain would re-aim with a stale estimate and never converge.
- **The servo diff is a 5-tick median** (`_diffWindow`): wifi delivery
  jitter swings the raw per-packet diff ±30 ms, which stalled dead-zone
  entry and caused spurious exits. 250 ms control lag, invisible at servo
  time constants. Cleared on jump/arm so the landing sample stays fresh.
- **RF gaps don't blind the servo** (`core/interfaces/wallclock.py`):
  packets carry `(pos, at)`, so the clock estimate is pure extrapolation —
  the slave keeps servoing from the last good packet up to `extrapolate`
  (4 s) before freewheeling.
- **Ramps cap at 2.0×** (mmal ceiling) and the fine speed bands keep
  **3 decimals end-to-end** — 2-decimal rounding used to park sub-0.07 s
  residuals at speed 1.0 forever.
- `arm()` keeps a <2 s-old pending measurement: profiles re-arm on mpv's
  `playing` echo right after the join's own seek.

## Validation

Simulation (FakePlayer with platform seek costs):

| scenario | lock | jumps | learned est |
|---|---|---|---|
| vaapi, sane GOP | 1.4 s | 1 | 0.33 s |
| mmal on 0_mire (4 s cost) | 18.5 s | 2 | 3.88 s |
| mmal single-KF (8 s cost) | 34.1 s | 3 | 8.03 s |

The mmal times are the physical floor — convergence is decode-bound, a
chain of exact seeks each measured and re-aimed.

Live on the 3-screen wifi wall (golden master + mini-01 + mini-06,
TL-WN823N dongles, hidden AP synclink-1):

- mini-01 join: **sub-frame lock 10.5 s after service start**, one
  dead-zone entry, zero bounces (was 30 s+ with 4 bounces);
- mini-01 + mini-06 simultaneous rejoin: both locked in **8 s**;
- full wall cold cycle: all locked ~20 s from cold.

## Content encoding guideline (venue)

Join speed on the RPi is GOP-driven (≈ half the keyframe interval per
jump). For wall/sync content:

- **keyframe interval ≤ 2 s, 1 s preferred**: `-g 30` at 30 fps;
- `0_mire.mp4` (8.3 s GOP, 360 kbps) is the worst sync media we measured —
  fine as a standalone test card, poor as a wall-sync reference;
- recipe:
  `ffmpeg -i in.mp4 -c:v libx264 -preset slow -crf 18 -g 30 -keyint_min 30 -sc_threshold 0 -pix_fmt yuv420p -movflags +faststart out.mp4`

## Related commits

- `7666e7d` drifter v2 (smart-jump, median filter, wallclock extrapolation,
  exact-seek support in mpv.py/base.py)
- `4a1463d` + `0d2ece4` shutdown watchdog — stops were paying systemd's
  90 s SIGKILL (zyre rebuilding into shutdown, zeroconf goodbye hang)
- `4c0a27c` `hplayer2-kill` no longer kill -9s itself (unit ended
  `failed (signal)` on every stop)
