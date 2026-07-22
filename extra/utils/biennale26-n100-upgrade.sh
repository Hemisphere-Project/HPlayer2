#!/bin/bash
# biennale26-n100-upgrade.sh — converge a Biennale-2024 N100 mini (Beelink
# MINI S, Ubuntu 24.04) onto HPlayer2 master + `biennale` profile +
# Pi-tools 2026. x86 sibling of biennale26-upgrade.sh (the RPi in-place
# path). Runs ON the mini as root; idempotent — safe to re-run, and running
# it on an already-converged unit only converges the leftovers.
#
# Encodes the mini-06 pilot recipe (2026-07-21/22), traps included:
#  - /tmp at 775 breaks apt's GPG sandbox            -> chmod first
#  - Pi-tools BEFORE apt (rw/ro helpers cover /boot/efi on 2026 only)
#  - purge snapd BEFORE rorw regenerates fstab (bind-mount brick)
#  - grub-efi debconf still names the 2024 mastering SSD -> set real ESP
#  - stale 2024 czmq/zyre in /usr/local shadow the fresh builds
#  - wint-hotspot: fleet psk is device-local, never in the repo
#
# End state must be verified from the driver seat after the reboot:
# ro rootfs, 0 failed units, hplayer2@biennale playing, hotspot up.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

[ "$(uname -m)" = x86_64 ] || { echo "x86_64 only"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ -d /opt/HPlayer2 ] && [ -d /opt/Pi-tools ] || { echo "missing /opt repos"; exit 1; }

STAMP=$(date +%Y%m%d)
BK="/data/upgrade-backup-$STAMP"

step() { echo; echo "━━━ $* ━━━"; }

step "0. rw + /tmp perms + backup"
mount -o remount,rw / 2>/dev/null || true
mount -o remount,rw /boot/efi 2>/dev/null || true
chmod 1777 /tmp
mkdir -p "$BK"
cp -an /etc/fstab /boot/starter.txt "$BK/" 2>/dev/null || true
[ -f /etc/systemd/system/hplayer2@.service ] && cp -an /etc/systemd/system/hplayer2@.service "$BK/" 2>/dev/null || true
[ -d /boot/wifi ] && [ ! -d "$BK/wifi" ] && cp -ra /boot/wifi "$BK/wifi"
{ echo "hplayer2: $(git -C /opt/HPlayer2 rev-parse HEAD)";
  echo "pitools:  $(git -C /opt/Pi-tools rev-parse HEAD)"; } > "$BK/HEADS.txt"
grep -h "^psk=" /boot/wifi/wint-hotspot.nmconnection 2>/dev/null | head -1 > "$BK/wint-psk.txt" || true

step "1. Pi-tools -> 2026 tip (fixed helpers first)"
git -C /opt/Pi-tools fetch origin
git -C /opt/Pi-tools checkout 2026 2>/dev/null || true
git -C /opt/Pi-tools pull --ff-only

step "2. snapd purge (before rorw fstab regen)"
dpkg --purge snapd 2>/dev/null || true

step "3. grub-efi debconf: point at THIS machine's ESP"
ESP=$(find /dev/disk/by-id -lname "*sda1" ! -name "wwn-*" | head -1)
[ -n "$ESP" ] && echo "grub-efi-amd64 grub-efi/install_devices multiselect $ESP" | debconf-set-selections

step "4. apt upgrade + deps"
apt-get update
apt-get upgrade -y -o Dpkg::Options::=--force-confold
apt-get install -y libtool libtool-bin libzmq3-dev nodejs npm
dpkg --configure -a
sed -i "s/^# *en_US.UTF-8/en_US.UTF-8/" /etc/locale.gen && locale-gen >/dev/null && update-locale LANG=en_US.UTF-8

step "5. uv"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
ln -sf /root/.local/bin/uv /usr/local/bin/uv
[ -e /root/.local/bin/uvx ] && ln -sf /root/.local/bin/uvx /usr/local/bin/uvx

step "6. HPlayer2 -> master tip"
cd /opt/HPlayer2
git submodule deinit -f scripts/czmq scripts/zyre 2>/dev/null || true
git fetch origin
git checkout master 2>/dev/null || true
git pull --ff-only
rm -rf scripts/czmq scripts/zyre .git/modules
python3 scripts/bootstrap_native_deps.py --prefix /usr/local
export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:${PKG_CONFIG_PATH:-}
uv sync
uv run python -c "import czmq, zyre" || { echo "FATAL: zyre bindings broken"; exit 1; }
echo "zyre bindings OK"

step "7. settings carry-over"
[ -f /data/hplayer2-biennale24.cfg ] && cp -n /data/hplayer2-biennale24.cfg /data/hplayer2-biennale.cfg || true

step "8. Pi-tools modules (rorw, network, webconf, audiohub, splash)"
mkdir -p /data/var/NetworkManager /data/var/dnsmasq
cp -a /data/var/lib/NetworkManager/. /data/var/NetworkManager/ 2>/dev/null || true
cp -a /data/var/lib/dnsmasq/. /data/var/dnsmasq/ 2>/dev/null || true
bash /opt/Pi-tools/rorw/install.sh
bash /opt/Pi-tools/network-tools/install.sh
# device identity back into the deployed hotspot profile
PSK=$(cut -d= -f2- "$BK/wint-psk.txt" 2>/dev/null || true)
[ -n "$PSK" ] && sed -i "s|^psk=.*|psk=$PSK|" /boot/wifi/wint-hotspot.nmconnection
sed -i "s/^ssid=rasta-00$/ssid=$(hostname)/" /boot/wifi/wint-hotspot.nmconnection
chmod -R go-rwx /boot/wifi
bash /opt/Pi-tools/webconf/install.sh
bash /opt/Pi-tools/audiohub/install.sh
bash /opt/Pi-tools/splash/install.sh     # x86: silent plymouth boot

step "9. unit + starter + services"
ln -sf /opt/HPlayer2/hplayer2@.service /etc/systemd/system/hplayer2@.service
systemctl daemon-reload
sed -i "s/^hplayer2@biennale24$/hplayer2@biennale/" /boot/starter.txt
systemctl disable --now mosquitto rtpmidid getty@tty1 grub-common grub-initrd-fallback NetworkManager-wait-online 2>/dev/null || true
systemctl mask dpkg-db-backup.service dpkg-db-backup.timer logrotate.service logrotate.timer 2>/dev/null || true
rm -f /usr/local/bin/{zpinger,zmakecert,enforce-ipv4,enforce-ping,rtpmidi,raveloxmidi}

step "10. apparmor on ro rootfs"
grep -q "^cache-loc /tmp/apparmor" /etc/apparmor/parser.conf 2>/dev/null || \
    printf "write-cache\ncache-loc /tmp/apparmor\n" >> /etc/apparmor/parser.conf
echo "d /tmp/apparmor 0755 root root -" > /etc/tmpfiles.d/apparmor-cache.conf
systemd-tmpfiles --create /etc/tmpfiles.d/apparmor-cache.conf 2>/dev/null || true

step "11. cleanup (pipenv era + leftovers)"
rm -rf /root/.local/share/virtualenvs
apt-get remove -y pipenv 2>/dev/null || true
rm -f /swap.img
apt-get autoremove -y 2>/dev/null || true

step "12. summary"
echo "hplayer2: $(git -C /opt/HPlayer2 log -1 --format='%h %s')"
echo "pitools:  $(git -C /opt/Pi-tools log -1 --format='%h %s')"
echo "starter:  $(grep -E '^hplayer2@' /boot/starter.txt)"
echo "backup:   $BK"
echo
echo "Rebooting in 5s (fstab restores ro; verify from the driver seat)…"
sleep 5
systemctl reboot
