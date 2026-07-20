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
