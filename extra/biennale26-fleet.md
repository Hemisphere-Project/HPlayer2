# Biennale 26 — fleet upgrade ledger

One row per **CPU serial** (`grep Serial /proc/cpuinfo`) — hostnames and
stickers can lie or change, silicon doesn't. Updated by the
`/biennale-pi-upgrade` skill (or by hand) after each player upgrade;
committed with a `Refs-37: biennale-lyon-2026#t-012` trailer so the hub's
parc relevé fills up as players are encountered.

Target: 35× RPi 3B+ (the 8× N100 are out of scope for this script).
`#` = the sticker number on the player (ask the human when the hostname
isn't `player-NN`). `was` = commit found on the SD before the upgrade —
this is parc-inventory data, never overwrite it on re-runs.

| # | hostname | serial | was | now | instance | RTC | notes | date |
|---|----------|--------|-----|-----|----------|-----|-------|------|
| 35 | player-35 | 00000000ce8fc39a | 07ec1594 | 1fd4693 | hplayer2@biennale | DS3231 ✓ | desk pilot: radar+schedule validated, upload-fix pilot, reboot-proven; re-run via own wint AP → tip (DMX + fleet tooling), 3.8 pre-flight green | 2026-07-15 |
