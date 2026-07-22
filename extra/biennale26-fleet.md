# Biennale 26 — fleet upgrade ledger

One row per **CPU serial** (`grep Serial /proc/cpuinfo`) — hostnames and
stickers can lie or change, silicon doesn't. Records which cards are converged,
however they got there — **golden-image reflash** (the mission method, 2026-07-15)
or the in-place `/biennale-pi-upgrade` skill. Commit each update with a
`Refs-37: biennale-lyon-2026#t-012` trailer so the hub's parc relevé fills up.

Target: **65× RPi 3B+** (35 existing reflashed on access + 30 new flashed) —
the 8× N100 are a separate x86 track. `#` = the sticker number (ask the human
when the hostname isn't `player-NN`). `was` = state found before the change
(commit, or `—` for a fresh flash) — parc-inventory data, never overwrite it.
`instance`/`RTC` = state after. For a golden reflash, note `reflash <image>`
in the notes column.

| # | hostname | serial | was | now | instance | RTC | notes | date |
|---|----------|--------|-----|-----|----------|-----|-------|------|
| 35 | player-35 | 00000000ce8fc39a | 07ec1594 | 1fd4693 | hplayer2@biennale | DS3231 ✓ | desk pilot: radar+schedule validated, upload-fix pilot, reboot-proven; re-run via own wint AP → tip (DMX + fleet tooling), 3.8 pre-flight green | 2026-07-15 |

## N100 x86 track (8× Beelink MINI S, biennale 2024)

Separate x86-64 track — no golden dd possible, convergence is in-place
(plan: `extra/biennale26-n100-upgrade-plan.md`). Serial = DMI
`system-serial-number` (`dmidecode`). All 8 surveyed 2026-07-21 on the bench
LAN: Ubuntu 24.04.1 (kernel 6.8), `/opt/HPlayer2` + pipenv + python 3.12.3,
mpv 0.37 distro, Pi-tools `main@6586796` in `/opt/Pi-tools`, ro rootfs,
453G `/data`, profile via `/boot/starter.txt`. As found: mini-02/07 carried
the 2025 eof/looping fix (`biennale24@b617c8a`), the other 6 sat 2 commits
behind on `master@268818c` — phase 0 of the convergence plan aligned all 8
on `b617c8a` the same day (reboot-verified: ro rootfs, service active,
http2 answering).

| # | hostname | serial | was | now | instance | RTC | notes | date |
|---|----------|--------|-----|-----|----------|-----|-------|------|
| m1 | mini-01 | BN1004JG00421 | 268818c | b617c8a | hplayer2@biennale24 | x86 ✓ | phase-0 align to 2025 eof fix, reboot-verified ro+active+http2 | 2026-07-21 |
| m2 | mini-02 | BN1004JG00401 | b617c8a | b617c8a | hplayer2@biennale24 | x86 ✓ | 2025 eof-fix reference | 2026-07-21 |
| m3 | mini-03 | BN1004JG00427 | 268818c | b617c8a | hplayer2@biennale24 | x86 ✓ | phase-0 align to 2025 eof fix, reboot-verified ro+active+http2 | 2026-07-21 |
| m4 | mini-04 | BN1004JG00254 | 268818c | b617c8a | hplayer2@biennale24 | x86 ✓ | phase-0 align to 2025 eof fix, reboot-verified ro+active+http2 | 2026-07-21 |
| m5 | mini-05 | BN1004HE10613 | 268818c | b617c8a | hplayer2@biennale24 | x86 ✓ | phase-0 align to 2025 eof fix, reboot-verified ro+active+http2 | 2026-07-21 |
| m6 | mini-06 | BN1004JG00399 | 268818c | 4e340f5 | hplayer2@biennale | x86 ✓ | PILOT fully validated: master+uv, Pi-tools 2026 (audiohub x86 ✓ 3 outs by ear, Node webconf, silent plymouth boot), play/loop matrix SOLO ✓, WALL slave lock ✓ ~1 frame vs golden, vaapi ✓, 0 failed units; snapd-bind wedge fixed | 2026-07-22 |
| m7 | mini-07 | BN1004HE10742 | b617c8a | b617c8a | hplayer2@biennale24 | x86 ✓ | 2025 eof-fix reference | 2026-07-21 |
| m8 | mini-08 | BN1004JG00428 | 268818c | b617c8a | hplayer2@biennale24 | x86 ✓ | phase-0 align to 2025 eof fix, reboot-verified ro+active+http2 | 2026-07-21 |
