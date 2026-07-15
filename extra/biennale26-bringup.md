# Biennale 26 — player bring-up & test procedure (RPi 3B+, branch `biennale`)

Applies to 2024-parc players (read-only rootfs, `rw`/`ro` helpers, code in
`/opt/HPlayer2`, media in `/data/media`, http2 on :80). Order matters:
**inventory before touching, regression before feature, solo before trio.**

The upgrade path was proven by hand on player-35 (2026-07-15, phases 0/A/B +
cold reboot all green) and is frozen into the one-command script:

    extra/utils/biennale26-upgrade.sh <player-ip> [--profile biennale] [--rtc]

Default = fleet-bascule case (branch switch only, profile untouched).
`--profile biennale` for dispositif C players, `--rtc` when a DS3231 is wired.

## Test media

```bash
# wall clip: burned-in frame counter — sync error readable on camera
ffmpeg -f lavfi -i color=c=black:s=1280x720:r=25:d=60 \
  -vf "drawtext=text='%{frame_num}':fontsize=160:fontcolor=white:x=(w-tw)/2:y=(h-th)/2" \
  -g 12 wall.mp4
```

Naming is functional: `ambient.mp4` / `wall.mp4` match `PLAY_PATTERN
[^1-9_]*.*` (default loop); `1_piece.mp4` matches `RADAR_PATTERN [1-9]_*.*`
(radar play-out, invisible to the loop).

## Phase 0 — inventory + upgrade path (per player, one at a time)

1. Ethernet + HDMI + power. Find it: `avahi-browse -art | grep -i hplayer`
   or the router's DHCP table. SSH in.
2. **Record before touching** (feeds the parc relevé):
   `hostname`, `git -C /opt/HPlayer2 log -1 --format=%h`,
   `systemctl list-unit-files 'hplayer2@*' | grep enabled`,
   `mpv --version | head -1`,
   `python3 -c "import watchdog; print(watchdog.__version__)"`,
   `ls /dev/rtc*`.
3. Switch code — run `extra/utils/biennale26-upgrade.sh <ip> [...]` from the
   laptop. Image facts the script encodes (learned on player-35):
   - **clock first**: fake-hwclock + no NTP leaves the clock stale, and a
     stale clock breaks github TLS ("repository not found" symptoms);
   - `rw`/`ro` remount **/ and /boot**; the boot instance is chosen by
     **`/boot/starter.txt`** (a `starter.service` reads it — NOT
     `systemctl enable`); `setnet` imports `/boot/wifi/*.nmconnection` into
     NetworkManager, so marker files must hold valid connection content;
   - **system python 3.8, no pipenv** (the `hplayer2` wrapper falls back);
     `hostname` doesn't exist (use `uname -n`); deps for the new interfaces
     (pyserial, netifaces) are already on the image;
   - timezone ships as UTC → the script sets **Europe/Paris** (schedule
     times are player-local wall-clock).

   ⚠ If step 2 showed a commit ≠ `07ec1594`, the checkout also crosses
   shared-code commits (not the guaranteed-additive case) — watch the journal
   and record whatever breaks: that is exactly the max-supported-commit data.
   ⚠ Needs the player to reach github; on an offline site, push from the
   laptop instead (`git remote add player ssh://root@<ip>/opt/HPlayer2`).
4. **Parc regression first**: before step 3's enable/disable, restart the
   existing `hplayer2@biennale24` on the new branch — must be byte-identical
   (this is what the 43-machine bascule does). 5 min, per image.
5. After the switch: `journalctl -u hplayer2@biennale -f` → mode banner
   (`SYNC_MASTER!` / `WALL mode` / neither = solo), no import traceback.
6. scp `ambient.mp4` → `/data/media`, **restart the service** (don't trust
   the reread loop on old images), confirm solo loop + http2 UI on :80.

## Phase A — radar trigger (player 1, solo)

Media: ONLY `1_piece.mp4` (faithful dispositif C) → expected idle state is
silence. With the Atom desk rig, first set in `/data/hplayer2-biennale.cfg`:
`"radar-filter": "M5 Serial|0403:6001"` (production C3 needs nothing).

| # | Action | Expect |
|---|--------|--------|
| 1 | plug radar, journal | serial connect; silence holds |
| 2 | walk in | `radar.enter` after ~300 ms → piece plays ONCE → silence |
| 3 | stay through play-out | no retrigger (leave edge required) |
| 4 | leave 2 s, re-enter | ~1.5 s to `radar.leave`, enter → replays |
| 5 | re-enter during playback | nothing (`isPlaying` guard) |
| 6 | shrink `radar-range` via http2 | no trigger at former distance; widen → triggers; survives restart |
| 7 | unplug/replug radar USB | reconnects, presence re-arms |
| 8 | `schedule-enable` on, no RTC | RTC warning, radar STILL triggers (fail-open) |

## Phase B — schedule / RTC (player 1, solo)

Fail-open is proven by A8. Gating needs a real `/dev/rtc*` — the upgrade
script's `--rtc` flag does all of this; by hand: `modprobe rtc-ds1307` +
`echo ds3231 0x68 > /sys/class/i2c-adapter/i2c-1/new_device` attaches it
live (no reboot), `dtoverlay=i2c-rtc,ds3231` in `/boot/config.txt` persists
it. **⚠ Virgin-RTC trap (hit on player-35)**: a fresh DS3231 reads
2000-01-01 and Arch's udev hctosys rule resets the SYSTEM clock the moment
the device registers — always re-set the date, then `hwclock --systohc --utc`
(with the fs rw so `/etc/adjtime` persists the UTC mode). Then:
- ambient back in place; window closing in 2 min → player stops at close,
  resumes at open.
- radar during closed window → NO trigger.
- power-cycle without ethernet → `hwclock -r` still sane.

## Phase C — zyre + drifter wall (all 3)

Roles via `/boot/wifi` markers — profile checks EXISTENCE, but the image may
import them into NetworkManager: use a valid DHCP-ethernet nmconnection as
content, and verify eth0 comes back after reboot on player 1 before doing 2–3.
- player 1: `/boot/wifi/eth0-sync-AP.nmconnection` (master)
- players 2–3: `/boot/wifi/eth0-sync-STA.nmconnection` (slaves)
Media: identical `wall.mp4` on all 3, ambient removed.

1. Cold start, master first: 10 s zyre grace, broadcast play, all 3 running.
2. Lock quality: film the 3 screens in slow-mo (240 fps) — counters within
   ±1 frame (desk harness held ~20 ms). Re-check after 10 min across several
   loop wraps: wraps must be seamless (mpv loop=inf, no black, no seek).
3. Late-boot self-start: reboot slave 3 → journal `wallclock: master is
   playing, self-starting` → converges with no master action.
4. Desync recovery: restart a slave service → single clean seek, no storm.
5. Freewheel: unplug slave ethernet 15 s → smooth, replug → reconverges.
   Then unplug the MASTER → slaves freewheel → replug → re-lock, no jump.
6. Master reboot: slaves freewheel throughout, master self-plays on return,
   re-locks. Watch for double-play.
7. http2 on master: play/stop rebound through zyre; volume broadcast (WALL).
8. Soak 1 h+ → still sub-frame.

Record the numbers from 2/4/5 — these are the sync "mesures hardware".

## Phase D — http2 upload over wifi (the on-site update path)

The branch uploads via spool-then-copy, redirected to `/data/var/tmp` by the
profile (the 1-write streaming rewrite lives on master, arrives with the
merge — re-measure then). Media differ per player and reach several GB;
wifi is the on-site lever, so measure for real:

1. `ls -ld /data/var/tmp` (profile now creates it — verify once).
2. Upload a ~500 MB file via the web UI over **ethernet**: wall-clock time →
   MB/s. Then join wlan0 to the LAN (`nmcli dev wifi connect <ssid>`),
   browse to the wifi IP, same file → MB/s.
3. Baseline the same transfers with `scp` on both links — separates http2
   overhead from radio reality.
4. Watch the journal during upload: does `files.filelist-updated` fire when
   the file lands (old-image watchdog pin may eat it → restart to see media)?
5. Re-upload the SAME filename → on this branch it silently overwrites
   (known); don't use it as a retry strategy on precious media.

## Fleet rollout

Per-player upgrades are driven by the `/biennale-pi-upgrade` skill
(`.claude/skills/biennale-pi-upgrade/`) wrapping the script above, and
recorded in `extra/biennale26-fleet.md` — one row per CPU serial, `was`
column = parc-inventory data. Exotic hostnames: ask for the sticker number.

## Known gotchas (old 2024 images)

- `hplayer2-kill` (ExecStartPre) kill -9's ANY process whose cmdline greps
  hplayer2/HPlayer2/mpv — an ssh session spanning a service restart dies
  with exit 137 (looks like a failure, usually isn't). Keep remote code in
  `bash -s` heredocs (invisible to ps) and verify in a fresh session.
- `git checkout <tree-ish> -- <file>` also STAGES the file; a later
  `git checkout -- <file>` restores the staged version and `git pull`
  refuses quietly. On players prefer `git fetch` + `git reset --hard`.
- Media added while running may go unnoticed (watchdog pin) → always restart
  after scp/upload.
- The modern-mpv `KeyError: 'data'` does NOT apply here (images pin old mpv).
- Browser forces `https://` on the player IP: that's the browser's HTTPS-First
  mode (not HSTS — it doesn't apply to IPs). Bookmark the players with an
  explicit `http://` scheme, and/or add exceptions (Firefox: HTTPS-Only →
  Manage Exceptions; Chrome: disable "Always use secure connections").
  Players stay plain-http on purpose — a self-signed cert would only trade a
  silent upgrade for a scary warning.
