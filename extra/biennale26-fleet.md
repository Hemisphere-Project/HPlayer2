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
http2 answering). **2026-07-22: all 8 converged** to master + `biennale` +
Pi-tools `2026` (pilot mini-06, batch the rest via
`extra/utils/biennale26-n100-upgrade.sh`). **Fleet snapshot (2026-07-22
evening): the `biennale` BRANCH is fast-forwarded to `a8b3792` and all 9
bench machines (golden + 8 minis) sit ON it** — the branch is the frozen
fleet state while `master` keeps moving; BIOS baseline ADLNV105 uniform
on the 8 minis (no newer ADLNV firmware exists — do not cross-flash the
S12-named MINISF/MS2V updates). Pending: Pi-tools `2026-2` (Thomas's
cooking branch) merges into `2026` when ready, then fleet-applies.

| # | hostname | serial | was | now | instance | RTC | notes | date |
|---|----------|--------|-----|-----|----------|-----|-------|------|
| m1 | mini-01 | BN1004JG00421 | 268818c | 5e6ad0e | hplayer2@biennale | x86 ✓ | batch-converged (biennale26-n100-upgrade.sh): master+uv+Pi-tools 2026, silent boot, driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
| m2 | mini-02 | BN1004JG00401 | b617c8a | 5e6ad0e | hplayer2@biennale | x86 ✓ | batch-converged (biennale26-n100-upgrade.sh): master+uv+Pi-tools 2026, silent boot, driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
| m3 | mini-03 | BN1004JG00427 | 268818c | 5e6ad0e | hplayer2@biennale | x86 ✓ | batch-converged (biennale26-n100-upgrade.sh): master+uv+Pi-tools 2026, silent boot, driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
| m4 | mini-04 | BN1004JG00254 | 268818c | 5e6ad0e | hplayer2@biennale | x86 ✓ | batch-converged (biennale26-n100-upgrade.sh): master+uv+Pi-tools 2026, silent boot, driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
| m5 | mini-05 | BN1004HE10613 | 268818c | 5e6ad0e | hplayer2@biennale | x86 ✓ | batch-converged (biennale26-n100-upgrade.sh): master+uv+Pi-tools 2026, silent boot, driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
| m6 | mini-06 | BN1004JG00399 | 268818c | 4e340f5 | hplayer2@biennale | x86 ✓ | PILOT fully validated: master+uv, Pi-tools 2026 (audiohub x86 ✓ 3 outs by ear, Node webconf, silent plymouth boot), play/loop matrix SOLO ✓, WALL slave lock ✓ ~1 frame vs golden, vaapi ✓, 0 failed units; snapd-bind wedge fixed | 2026-07-22 |
| m7 | mini-07 | BN1004HE10742 | b617c8a | 6fd91a0 | hplayer2@biennale | x86 ✓ | batch-converged last (2024 reference until the end); 1st run killed by unattended-upgrades dpkg lock (script now tames it), rerun clean; driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
| m8 | mini-08 | BN1004JG00428 | 268818c | 5e6ad0e | hplayer2@biennale | x86 ✓ | batch-converged (biennale26-n100-upgrade.sh): master+uv+Pi-tools 2026, silent boot, driver-seat verified ro+0failed+player+webconf+hub+hotspot | 2026-07-22 |
