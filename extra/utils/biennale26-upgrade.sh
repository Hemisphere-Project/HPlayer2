#!/bin/bash
# biennale26-upgrade.sh — one-command HPlayer2 fleet upgrade to branch `biennale`.
# Proven end-to-end on player-35 (2026-07-15). Run FROM a laptop on the player's LAN:
#
#     extra/utils/biennale26-upgrade.sh <player-ip> [--profile biennale] [--rtc]
#
# Default is the fleet-bascule case: switch the BRANCH only, keep the enabled
# profile (biennale24.py is frozen on the branch — behavior byte-identical).
#   --profile <name>   also switch the hplayer2@ instance in /boot/starter.txt
#                      (dispositif C outdoor players: --profile biennale)
#   --rtc              attach + set a DS3231 on i2c-1 (radar/outdoor players)
#
# Image facts this script relies on (2024 Arch ARM image):
#   - `rw`/`ro` helpers remount / AND /boot ; services boot via /boot/starter.txt
#   - system python3 (3.8, no pipenv), deps already present for the new interfaces
#   - fake-hwclock + no NTP: the clock is stale -> github TLS fails until set
# The player keeps playing its current show until the final service restart.

set -e
IP="$1"; shift || { echo "usage: $0 <player-ip> [--profile <name>] [--rtc]"; exit 1; }
PROFILE=""; RTC=0
while [ $# -gt 0 ]; do case "$1" in
  --profile) PROFILE="$2"; shift 2;;
  --rtc)     RTC=1; shift;;
  *) echo "unknown arg: $1"; exit 1;;
esac; done

# clock is injected from THIS machine (players have no trustworthy time source)
NOW=$(date -u '+%Y-%m-%d %H:%M:%S')

ssh "root@$IP" bash -s <<EOF
set -e
echo "== \$(uname -n): was \$(git -C /opt/HPlayer2 log -1 --format=%h) on \$(git -C /opt/HPlayer2 branch --show-current)"

# 1. clock first — TLS to github fails on a stale clock
date -u -s '$NOW' >/dev/null

rw
timedatectl set-timezone Europe/Paris

# 2. RTC (optional) — BEFORE the fetch so the written time is fresh.
#    ⚠ a virgin DS3231 reads 2000-01-01 and Arch's udev hctosys rule resets the
#    system clock the instant the device registers -> re-set date, then systohc.
if [ "$RTC" = "1" ]; then
  modprobe rtc-ds1307
  echo ds3231 0x68 > /sys/class/i2c-adapter/i2c-1/new_device 2>/dev/null || true
  sleep 1
  date -u -s '$NOW' >/dev/null
  hwclock --systohc --utc        # fs is rw: also persists UTC mode in /etc/adjtime
  grep -q 'dtoverlay=i2c-rtc' /boot/config.txt || echo 'dtoverlay=i2c-rtc,ds3231' >> /boot/config.txt
  echo "== rtc set: \$(hwclock -r | cut -c1-19) local"
fi

# 3. code switch (service still running its old code from RAM — live-safe)
git -C /opt/HPlayer2 fetch origin
git -C /opt/HPlayer2 checkout -B biennale origin/biennale
echo "== now \$(git -C /opt/HPlayer2 log -1 --format=%h)"
mkdir -p /data/var/tmp

# 4. pre-flight the new code with the image's own python BEFORE touching the service
cd /opt/HPlayer2
python3 -m py_compile core/interfaces/wallclock.py core/interfaces/schedule.py \
  core/interfaces/radar.py core/interfaces/serialbase.py \
  core/engine/drifter.py profiles/biennale.py
echo "== pre-flight OK"

# 5. instance switch (optional) — starter.txt drives boot on this image
CUR=\$(grep -o '^hplayer2@[a-zA-Z0-9_-]*' /boot/starter.txt | head -1)
if [ -n "$PROFILE" ] && [ "\$CUR" != "hplayer2@$PROFILE" ]; then
  cp /boot/starter.txt "/boot/starter.txt.bak-\$(date +%Y%m%d)"
  sed -i "s/^\$CUR\\\$/hplayer2@$PROFILE/" /boot/starter.txt
  echo "== starter.txt: \$CUR -> hplayer2@$PROFILE"
fi

ro

# 6. restart on the new code
if [ -n "$PROFILE" ]; then
  systemctl stop "\$CUR" 2>/dev/null || true
  systemctl start "hplayer2@$PROFILE"
  UNIT="hplayer2@$PROFILE"
else
  systemctl restart "\$CUR"
  UNIT="\$CUR"
fi
sleep 10
systemctl is-active "\$UNIT"
journalctl -u "\$UNIT" --since '-10s' --no-pager | grep -iE 'traceback|error in app' \
  && echo "== ⚠ check the journal above" || echo "== \$UNIT clean"
EOF

echo "== done. verify: http://$IP (explicit http://) and journalctl -u hplayer2@... -f"
