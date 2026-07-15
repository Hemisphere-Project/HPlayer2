#!/bin/bash
# biennale26-upgrade.sh — idempotent HPlayer2 fleet upgrade to branch `biennale`.
# Proven end-to-end on player-35 (2026-07-15). Run FROM a laptop on the player's LAN:
#
#     extra/utils/biennale26-upgrade.sh <player-ip> [--status] [--profile <name>]
#
#   --status          detect & print the player's state, change nothing
#   --profile <name>  override the target hplayer2@ instance. DEFAULT is
#                     `biennale` — biennale24 is deprecated (Thomas,
#                     2026-07-15): every player switches to the unified
#                     profile. Audio calibration (volume/audioout/audiomode/
#                     pan/flip) is carried over from the old biennale24 cfg.
#
# Detect-then-apply: every step checks before it acts, so partially-upgraded
# players are fine and re-runs are no-ops. RTC is AUTO-probed: a DS3231 found
# on i2c-1 (0x68) gets configured; no chip = skipped with a note.
#
# Image facts this script relies on (2024 Arch ARM image):
#   - `rw`/`ro` helpers remount / AND /boot ; services boot via /boot/starter.txt
#   - system python3 (3.8, no pipenv); deps for the new interfaces are present
#   - fake-hwclock + no NTP: clock is stale -> github TLS fails until set
#   - ⚠ hplayer2-kill (ExecStartPre) kill -9's ANY process whose cmdline greps
#     hplayer2/HPlayer2/mpv. All remote code goes through `bash -s` heredocs
#     (invisible to ps); the restart still lives in its own throwaway session
#     tolerant to exit 137, in case the reaper catches the ssh keepalive.
# The player keeps playing its current show until the final restart.

set -e
IP="$1"; shift || { echo "usage: $0 <player-ip> [--status] [--profile <name>]"; exit 1; }
PROFILE="biennale"; STATUS=0
while [ $# -gt 0 ]; do case "$1" in
  --profile) PROFILE="$2"; shift 2;;
  --status)  STATUS=1; shift;;
  *) echo "unknown arg: $1"; exit 1;;
esac; done

NOW=$(date -u '+%Y-%m-%d %H:%M:%S')

# ── detect ────────────────────────────────────────────────────────────────────
STATE=$(ssh "root@$IP" bash -s <<'EOF'
echo "host=$(uname -n)"
echo "serial=$(grep Serial /proc/cpuinfo | awk '{print $3}')"
echo "commit=$(git -C /opt/HPlayer2 log -1 --format=%h)"
echo "branch=$(git -C /opt/HPlayer2 branch --show-current)"
echo "instance=$(grep -o '^hplayer2@[a-z0-9_.-]*' /boot/starter.txt | head -1)"
echo "tz=$(timedatectl show -p Timezone --value 2>/dev/null)"
echo "clock_year=$(date +%Y)"
echo "rtc_dev=$([ -e /dev/rtc0 ] && echo yes || echo no)"
echo "rtc_chip=$(i2cdetect -y 1 2>/dev/null | grep -qE ' (68|UU) ' && echo yes || echo no)"
echo "rtc_overlay=$(grep -q 'dtoverlay=i2c-rtc' /boot/config.txt && echo yes || echo no)"
echo "adjtime=$([ -f /etc/adjtime ] && echo yes || echo no)"
echo "spool=$([ -d /data/var/tmp ] && echo yes || echo no)"
echo "uploadraw=$(grep -q uploadraw /opt/HPlayer2/core/interfaces/http2.py && echo yes || echo no)"
echo "dirty=$(git -C /opt/HPlayer2 status --porcelain | grep -cv '^??' || true)"
EOF
)
echo "$STATE"
eval "$STATE"

[ "$STATUS" = "1" ] && exit 0
[ "$dirty" != "0" ] && { echo "⚠ working tree has local changes — inspect before upgrading"; exit 1; }

# ── apply (idempotent) ────────────────────────────────────────────────────────
ssh "root@$IP" bash -s <<EOF
set -e
date -u -s '$NOW' >/dev/null            # TLS to github fails on a stale clock
rw
[ "\$(timedatectl show -p Timezone --value)" = "Europe/Paris" ] || timedatectl set-timezone Europe/Paris

# RTC: configure iff a chip answers on the bus (0x68, or UU when driver-bound)
if i2cdetect -y 1 2>/dev/null | grep -qE ' (68|UU) '; then
  if [ ! -e /dev/rtc0 ]; then
    modprobe rtc-ds1307
    echo ds3231 0x68 > /sys/class/i2c-adapter/i2c-1/new_device 2>/dev/null || true
    sleep 1
    # ⚠ a virgin DS3231 reads 2000-01-01 and udev hctosys just reset the system
    # clock the instant the device registered -> re-set date before systohc
    date -u -s '$NOW' >/dev/null
  fi
  hwclock --systohc --utc               # fs is rw: persists UTC mode in /etc/adjtime
  grep -q 'dtoverlay=i2c-rtc' /boot/config.txt || echo 'dtoverlay=i2c-rtc,ds3231' >> /boot/config.txt
  echo "== rtc: \$(hwclock -r | cut -c1-19) local"
else
  echo "== rtc: no chip on i2c-1, skipped"
fi

git -C /opt/HPlayer2 fetch origin
git -C /opt/HPlayer2 checkout -B biennale origin/biennale 2>&1 | tail -1
echo "== code: \$(git -C /opt/HPlayer2 log -1 --format=%h)"
mkdir -p /data/var/tmp

# pre-flight the new code with the image's own python BEFORE touching the service
cd /opt/HPlayer2
python3 -m py_compile core/interfaces/wallclock.py core/interfaces/schedule.py \
  core/interfaces/radar.py core/interfaces/serialbase.py core/interfaces/http2.py \
  core/engine/drifter.py profiles/biennale.py
echo "== pre-flight OK"

CUR=\$(grep -o '^hplayer2@[a-z0-9_.-]*' /boot/starter.txt | head -1)
if [ -n "$PROFILE" ] && [ "\$CUR" != "hplayer2@$PROFILE" ]; then
  cp /boot/starter.txt "/boot/starter.txt.bak-\$(date +%Y%m%d)"
  sed -i "s|^\$CUR\\\$|hplayer2@$PROFILE|" /boot/starter.txt
  echo "== starter.txt: \$CUR -> hplayer2@$PROFILE"
fi

# profile switch starts a fresh cfg: carry the per-player audio calibration
# over from the deprecated biennale24 cfg (never the playlist/loop, which the
# profile manages)
if [ "$PROFILE" = "biennale" ] && [ -f /data/hplayer2-biennale24.cfg ] && [ ! -f /data/hplayer2-biennale.cfg ]; then
  python3 - <<'PY'
import json
old = json.load(open('/data/hplayer2-biennale24.cfg'))
keep = {k: old[k] for k in ('volume', 'audioout', 'audiomode', 'pan', 'flip') if k in old}
json.dump(keep, open('/data/hplayer2-biennale.cfg', 'w'), indent=1)
print('== cfg carry-over:', keep)
PY
fi
ro
EOF

# ── restart in its own throwaway session (exit 137 from the reaper = benign) ──
TARGET="${PROFILE:-${instance#hplayer2@}}"
TARGET="${TARGET:-biennale24}"
ssh "root@$IP" bash -s <<EOF || true
systemctl stop ${instance:-hplayer2@biennale24} 2>/dev/null
systemctl start hplayer2@$TARGET
EOF
sleep 12

# ── verify in a fresh session ────────────────────────────────────────────────
ssh "root@$IP" bash -s <<EOF
systemctl is-active hplayer2@$TARGET
journalctl -u hplayer2@$TARGET --since '-12s' --no-pager 2>/dev/null | grep -icE 'traceback' | sed 's/^/tracebacks: /' || true
echo "SUMMARY host=$host serial=$serial number=? was=$commit now=\$(git -C /opt/HPlayer2 log -1 --format=%h) instance=hplayer2@$TARGET rtc=\$([ -e /dev/rtc0 ] && echo yes || echo no) tz=\$(timedatectl show -p Timezone --value) date=\$(date '+%Y-%m-%d')"
EOF
echo "== done. web UI: http://$IP (explicit http://)"
