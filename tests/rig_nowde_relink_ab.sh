#!/usr/bin/env bash
# t050-relink-ab.sh — hplayer2#t-050 relink A/B on the player rig, run from fw13 through hmini25.
#   bench-01 (192.168.2.2) = Nowde MASTER, node A — the 7.5 golden source: NOTHING may persist on its
#     card. /data is overlaid by tmpfs for the run and /data/media is a tmpfs holding the test clip;
#     the only lasting change is node A's NVS role, set back to the board default (0x7F) at restore.
#   bench-02 (192.168.2.3) = Nowde SLAVE under test, node B — same overlay; run A on its current code,
#     run B on the fix (99922e0); its checkout is put back at restore.
# The relink is usbfix's own cure: de-authorize the node's USB device, 2 s, re-authorize — the exact
# event W4 logged on 19/10. Steps, one at a time, read between each:
#   pre | setup-master | setup-slave | status <b1|b2> | relink <A|B> [n] | collect <A|B> | fix | restore-slave | restore-master
set -euo pipefail
B1=192.168.2.2; B2=192.168.2.3; FIX=99922e0
CLIP=${CLIP:-${TMPDIR:-/tmp}/t050/03_t050.mp4}   # 10 min test pattern; the 03_ prefix = Nowde index 3 on both
if [ ! -s "$CLIP" ]; then   # regenerated, never committed (no media in git)
  mkdir -p "$(dirname "$CLIP")"
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=640x360:rate=25 -t 600 -c:v libx264 \
    -preset veryfast -crf 35 -pix_fmt yuv420p -g 50 -movflags +faststart "$CLIP"
fi
SSHO=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -i "$HOME/.ssh/mgr-26" -J hmini25)
host() { case $1 in b1) echo $B1;; b2) echo $B2;; *) echo "$1";; esac; }
r() { local h; h=$(host "$1"); shift; ssh "${SSHO[@]}" root@"$h" bash -s -- "$@"; }   # remote script on stdin

PRE=$(cat <<'EOF'
echo "== $(hostname) up $(uptime -p)"
echo "conf: $(tr '\n' ' ' < /boot/hplayer2.conf 2>/dev/null)"
echo "code: $(git -C /opt/HPlayer2 rev-parse --short HEAD) ($(git -C /opt/HPlayer2 rev-parse --abbrev-ref HEAD))"
echo "units:"; systemctl list-units --all --plain --no-legend 'hplayer2@*' | sed 's/^/  /'
echo "last hplayer2 lines:"; journalctl -u 'hplayer2@*' -n 6 --no-pager -o short-precise 2>/dev/null | cut -c1-170 | sed 's/^/  /'
echo "media: $(ls /data/media 2>/dev/null | head -5 | tr '\n' ' ')"
echo "midi:"; amidi -l 2>&1 | sed 's/^/  /'
for d in /sys/bus/usb/devices/*/product; do grep -qs Nowde "$d" && echo "node sysfs: $(basename "$(dirname "$d")") = $(cat "$d")"; done
echo "/data: $(findmnt -no SOURCE,FSTYPE,OPTIONS /data)"; echo "journal: $(findmnt -no SOURCE /var/log/journal 2>/dev/null || echo not-a-mount)"
echo "/tmp: $(df -h /tmp | tail -1)"; free -m | sed -n 2p
grep -qw overlay /proc/filesystems && echo "overlay: yes" || echo "overlay: NOT loaded"
echo "usbfix: timer $(systemctl is-active usbfix.timer 2>/dev/null) inhibit $([ -f /run/usbfix.inhibit ] && echo SET || echo none)"
echo "rw/ro: $(command -v rw || echo none) $(command -v ro || echo none)"
ls -d /tmp/t050 2>/dev/null && echo "WARNING: /tmp/t050 already exists"
EOF
)

# $1 = role byte (01 master / 00 slave); clip already copied to /tmp/t050/
SETUP=$(cat <<'EOF'
set -euo pipefail
T=/tmp/t050; ROLE=$1
mountpoint -q /data/media && { echo "already set up"; exit 1; }
grep -qw overlay /proc/filesystems || modprobe overlay
mkdir -p $T/lower $T/up $T/work
systemctl list-units --plain --no-legend --state=active 'hplayer2@*' | awk '{print $1}' > $T/units.before
echo "stopping: $(tr '\n' ' ' < $T/units.before)"
while read -r u; do [ -n "$u" ] && systemctl stop "$u"; done < $T/units.before
mount --bind /data $T/lower && mount -o remount,bind,ro $T/lower
mount -t overlay t050 -o lowerdir=$T/lower,upperdir=$T/up,workdir=$T/work /data
mount -t tmpfs -o size=64m t050media /data/media
cp $T/03_t050.mp4 /data/media/
P=$(amidi -l | awk '/Nowde/{print $2; exit}'); [ -n "$P" ] || { echo "no Nowde MIDI port"; exit 1; }
amidi -p "$P" -S "F0 7D 08 $ROLE F7"; echo "node $P role <- $ROLE"
if [ "$ROLE" = 00 ] && [ ! -f /run/usbfix.inhibit ]; then touch /run/usbfix.inhibit $T/inhibit.ours; echo "usbfix inhibited"; fi
sleep 2
systemctl start hplayer2@biennale
echo "started hplayer2@biennale at $(date '+%F %T') on $(git -C /opt/HPlayer2 rev-parse --short HEAD)"
findmnt /data; findmnt /data/media
EOF
)

STATUS=$(cat <<'EOF'
journalctl -u hplayer2@biennale --since -${1:-60}s --no-pager -o short-precise \
 | grep -E 'HELLO v|role|CC#100|JUMP|timedelay|stopped|Video ended|restart|relink|disconnected|connect|guard|silen|master|slave|Traceback|Error' \
 | cut -c1-200 | tail -${2:-25}
EOF
)

# $1 = run label, $2 = count
RELINK=$(cat <<'EOF'
set -euo pipefail
D=""; for d in /sys/bus/usb/devices/*/product; do grep -qs Nowde "$d" && D=$(basename "$(dirname "$d")"); done
[ -n "$D" ] || { echo "no Nowde USB device"; exit 1; }
[ -f /run/usbfix.inhibit ] || { echo "usbfix not inhibited — refusing"; exit 1; }
for k in $(seq 1 "$2"); do
  logger -t t050 "relink $k run $1 START (usb $D)"
  echo 0 > /sys/bus/usb/devices/$D/authorized; sleep 2; echo 1 > /sys/bus/usb/devices/$D/authorized
  logger -t t050 "relink $k run $1 re-authorized"; echo "relink $k done $(date +%T)"; sleep 30
done
logger -t t050 "run $1 END"
EOF
)

# $1 = run label
COLLECT=$(cat <<'EOF'
S=$(journalctl -t t050 --no-pager -o short-unix | grep "relink 1 run $1 START" | tail -1 | awk '{print $1}'); S="@${S%%.*}"
[ "$S" != "@" ] || { echo "no run $1 markers"; exit 1; }
{ journalctl -t t050 --since "$S" --no-pager -o short-precise; journalctl -u hplayer2@biennale --since "$S" --no-pager -o short-precise; } \
 | sort -s -k1,3 | grep -E 't050|HELLO v|role|CC#100|after a relink|JUMP|stopped|Video ended|restart|disconnected|relinking|connected to|guard|silen|Traceback' | cut -c1-210 > /tmp/t050/run-$1.log
cat /tmp/t050/run-$1.log
echo "== per relink, run $1: JUMP / player stopped / Video ended / keep-playing"
awk '/t050.*relink [0-9]+ run .* START/{for(i=1;i<=NF;i++) if($i=="relink") k=$(i+1)}
     /t050.*END/{k=""}
     k!="" && /JUMP \(fix/{j[k]++} k!="" && /\[player\].*stopped|player.*stopped$/{s[k]++}
     k!="" && /Video ended/{v[k]++} k!="" && /keep playing/{p[k]++} k!=""{seen[k]=1}
     END{for(x in seen) printf "relink %s: JUMP %d · stopped %d · Video-ended %d · keep-playing %d\n", x, j[x], s[x], v[x], p[x]}' /tmp/t050/run-$1.log | sort
EOF
)

FIXSTEP=$(cat <<'EOF'
set -euo pipefail
RW() { if command -v rw >/dev/null; then rw; else mount -o remount,rw /; fi; }
RO() { if command -v ro >/dev/null; then ro; else mount -o remount,ro /; fi; }
cd /opt/HPlayer2; git rev-parse --abbrev-ref HEAD > /tmp/t050/ref.before; git rev-parse HEAD >> /tmp/t050/ref.before
RW
git fetch -q origin 37loop/hplayer2-t-050 && git checkout -q --detach "$1"
RO || echo "WARNING: / stays rw (busy) — remount ro at restore"
systemctl restart hplayer2@biennale
echo "bench-02 now on $(git rev-parse --short HEAD), restarted $(date +%T)"
EOF
)

RESTORE=$(cat <<'EOF'
set -uo pipefail
RW() { if command -v rw >/dev/null; then rw; else mount -o remount,rw /; fi; }
RO() { if command -v ro >/dev/null; then ro; else mount -o remount,ro /; fi; }
T=/tmp/t050
systemctl stop hplayer2@biennale
if [ -f $T/ref.before ]; then
  ref=$(sed -n 1p $T/ref.before); sha=$(sed -n 2p $T/ref.before)
  RW
  if [ "$ref" = HEAD ]; then git -C /opt/HPlayer2 checkout -q --detach "$sha"; else git -C /opt/HPlayer2 checkout -q "$ref"; fi
  RO
fi
P=$(amidi -l | awk '/Nowde/{print $2; exit}'); [ -n "$P" ] && amidi -p "$P" -S 'F0 7D 08 7F F7' && echo "node $P role <- board default"
[ -f $T/inhibit.ours ] && rm -f /run/usbfix.inhibit && echo "usbfix re-armed"
umount /data/media; umount /data || umount -l /data; umount $T/lower || umount -l $T/lower
while read -r u; do [ -n "$u" ] && systemctl start "$u"; done < $T/units.before
echo "restored: code $(git -C /opt/HPlayer2 rev-parse --short HEAD), units $(tr '\n' ' ' < $T/units.before), /data $(findmnt -no FSTYPE /data)"
cp $T/run-*.log /root/ 2>/dev/null || true
rm -rf $T/up $T/work $T/03_t050.mp4
EOF
)

case ${1:-} in
  pre)            for h in $B1 $B2; do r "$h" <<<"$PRE"; done ;;
  setup-master)   ssh "${SSHO[@]}" root@$B1 mkdir -p /tmp/t050; scp -q "${SSHO[@]}" "$CLIP" root@$B1:/tmp/t050/; r $B1 01 <<<"$SETUP" ;;
  setup-slave)    ssh "${SSHO[@]}" root@$B2 mkdir -p /tmp/t050; scp -q "${SSHO[@]}" "$CLIP" root@$B2:/tmp/t050/; r $B2 00 <<<"$SETUP" ;;
  status)         r "$2" "${3:-60}" "${4:-25}" <<<"$STATUS" ;;
  relink)         r $B2 "$2" "${3:-3}" <<<"$RELINK" ;;
  collect)        r $B2 "$2" <<<"$COLLECT" ;;
  fix)            r $B2 "$FIX" <<<"$FIXSTEP" ;;
  restore-slave)  r $B2 <<<"$RESTORE" ;;
  restore-master) r $B1 <<<"$RESTORE" ;;
  *) sed -n 2,12p "$0"; exit 2 ;;
esac
