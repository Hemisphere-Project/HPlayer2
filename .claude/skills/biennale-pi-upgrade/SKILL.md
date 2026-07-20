---
name: biennale-pi-upgrade
description: Upgrade a Biennale pool RPi 3B+ to the biennale branch (code, TZ, RTC, optional profile switch), verify it, and record it in the fleet ledger. Use when a pool player is plugged on the LAN and Thomas says to upgrade it, gives an IP, or asks for the fleet status. Handles partially-upgraded players (idempotent) and exotic hostnames (asks for the sticker number).
---

# /biennale-pi-upgrade — in-place upgrade one player, keep the fleet ledger true

Wraps `extra/utils/biennale26-upgrade.sh` (detect-then-apply, idempotent,
proven on player-35 2026-07-15). The ledger `extra/biennale26-fleet.md` is the
single source of truth of which cards are done (keyed on CPU serial).

**Scope note (decided 2026-07-15):** the mission's mass convergence method is
a **golden-image reflash** (clone the validated player-35 SD), NOT this
in-place upgrade. So this skill is now the **prep / test / one-off** path:
bring player-35 (or a test unit) to the exact state that gets cloned, iterate
during dev, or fix a single reachable card — not the way the 65 RPi 3B+
converge. Still record whatever it touches in the ledger.

## Inputs

An IP (required — ask if not given). SSH as `root` with the usual parc
password (never write it into this repo — it's public; Thomas provides it,
or it's in the session's private memory); if `sshpass` is absent use the
`SSH_ASKPASS` + `setsid` trick. **Default switches the profile to
`biennale`** — biennale24 is deprecated (Thomas, 2026-07-15); the script
carries the per-player audio calibration (volume/audioout/audiomode/pan/
flip) from the old biennale24 cfg into the fresh biennale cfg. `--profile`
remains only as an override for exotic cases.

## Procedure

1. **Status first**: `extra/utils/biennale26-upgrade.sh <ip> --status`.
   Read the state block. Refuse to proceed (and report) if `dirty != 0`.
2. **Identify the player**:
   - hostname matches `player-NN` → that's the number.
   - anything else (exotic name) → **ask Thomas for the sticker number**
     (AskUserQuestion; it's written on the player). Record hostname AND
     number in the ledger; never guess.
   - if the serial already has a ledger row and everything is green in
     status → report "already upgraded on <date>", update nothing, stop.
3. **Anomalies to surface BEFORE applying** (don't block, inform):
   - `commit` ≠ `07ec1594` → off-pin: the checkout crosses shared-code
     commits; watch the journal closely and note the old commit in the
     ledger — that's max-supported-commit data for the engagement.
   - `instance` neither `hplayer2@biennale24` nor `hplayer2@biennale` →
     exotic profile: ask before touching anything.
   - `rtc_chip=no` on a player that should have one (dispositif C) → say so.
4. **Apply**: run the script (with `--profile` only as decided above).
   Exit 137 anywhere near the restart = the `hplayer2-kill` reaper, benign:
   re-run `--status` in a fresh session to verify instead of trusting the
   exit code.
5. **Verify**: `active`, `tracebacks: 0`, `now` = current `origin/biennale`
   tip. If the player should show/play something, confirm in the journal.
6. **Ledger**: add or update the row in `extra/biennale26-fleet.md`
   (one row per serial; on re-runs update `now`/`date`/notes, **never
   overwrite `was`** — it's parc-inventory data). Commit it:

   ```
   fleet: player-NN upgraded (<serial>)

   Refs-37: biennale-lyon-2026#t-012
   ```

   and push `biennale`. On rejection: `git pull --rebase origin biennale`,
   re-push.
7. **Report**: number, before → after, actions taken/skipped, anomalies.

## Image facts (2024 Arch ARM — the script encodes these, don't fight them)

- clock is stale (fake-hwclock, no NTP) → github TLS fails until the date is
  set; the script injects the laptop's clock first.
- boot instance = `/boot/starter.txt` via `starter.service`, NOT
  `systemctl enable`; `rw`/`ro` remount / **and** /boot.
- system python 3.8, no pipenv, no `hostname` binary (use `uname -n`).
- ⚠ `hplayer2-kill` kill -9's any process whose cmdline greps
  hplayer2/HPlayer2/mpv — keep remote code in `bash -s` heredocs (invisible
  to ps), never in ssh argument strings that span a restart.
- virgin DS3231 + udev hctosys resets the system clock to 2000 on register —
  the script re-sets the date before `hwclock --systohc --utc`.

## NEVER

- Leave a player on the deprecated `biennale24` instance (the default
  switch to `biennale` is Thomas's 2026-07-15 ruling); only an *exotic*
  instance (neither biennale24 nor biennale) pauses for a question.
- Rename a host, delete media, or touch `/boot/wifi` markers (wall roles are
  phase C, done deliberately, not by this skill).
- Create more than one ledger row per serial, or overwrite a row's `was`.
- Force-push, or push anything but the `biennale` branch.
