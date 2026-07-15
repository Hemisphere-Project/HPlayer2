# Biennale 26 — player bring-up & test procedure (RPi 3B+, branch `biennale`)

Applies to 2024-parc players (read-only rootfs, `rw`/`ro` helpers, code in
`/opt/HPlayer2`, media in `/data/media`, http2 on :80). Order matters:
**inventory before touching, regression before feature, solo before trio.**

The per-player upgrade below is run BY HAND on the first player, corrections
noted, then on the two others — once stable it gets frozen into a one-command
script (`extra/utils/biennale26-upgrade.sh`) to apply to fleet players as we
encounter them.

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
3. Switch code — this block is the future upgrade script, refine it as reality
   pushes back:

   ```bash
   ssh root@<ip> '
     set -e
     echo "== $(hostname): was $(git -C /opt/HPlayer2 log -1 --format=%h) =="
     rw
     git -C /opt/HPlayer2 fetch origin
     git -C /opt/HPlayer2 checkout -B biennale origin/biennale
     mkdir -p /data/var/tmp
     systemctl disable hplayer2@biennale24
     systemctl enable  hplayer2@biennale
     ro
     systemctl restart hplayer2@biennale
     echo "== now $(git -C /opt/HPlayer2 log -1 --format=%h) =="
   '
   ```

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

Fail-open is proven by A8. Gating needs a real `/dev/rtc*` (DS3231 →
`dtoverlay=i2c-rtc,ds3231` in `/boot/config.txt`, reboot):
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

## Known gotchas (old 2024 images)

- Media added while running may go unnoticed (watchdog pin) → always restart
  after scp/upload.
- The modern-mpv `KeyError: 'data'` does NOT apply here (images pin old mpv).
- Browser forces `https://` on the player IP: that's the browser's HTTPS-First
  mode (not HSTS — it doesn't apply to IPs). Bookmark the players with an
  explicit `http://` scheme, and/or add exceptions (Firefox: HTTPS-Only →
  Manage Exceptions; Chrome: disable "Always use secure connections").
  Players stay plain-http on purpose — a self-signed cert would only trade a
  silent upgrade for a scary warning.
