#!/usr/bin/env bash
# rig_nowde_seek_ab.sh — hplayer2#t-062 seek A/B on the player rig, run from dev37 (ssh bench-01/02).
#   bench-02 = Nowde MASTER (node B): plays the 10-min test clip; a "click" is the http2 seekbar's own
#     event (Engine.IO `seek`, absolute ms) sent from the box itself.
#   bench-01 = Nowde SLAVE under test (node A): run A on the old code (origin/master), run B on the fix.
#     (bench-01 is the slave because two `player-000` on the LAN kill its http2 thread: no seekbar.)
# NOTHING persists on either card: /data is overlaid by tmpfs; the code runs from a /tmp tree
# (`git archive`) as a transient unit `t062`; media and cfg live in /tmp/t062 (the profile copy's
# mediaPath points there); no checkout, no rw. Lasting: none — the node roles go back to the board
# default (0x7F) at restore, usbfix is re-armed if we inhibited it, the units found active restart.
# One ssh at a time (the hmini25 jump drops bursts). Steps, read between each:
#   pre | setup b2 master | setup b1 slave <sha> | status <b1|b2> [secs] | clicks <A|B> | collect <A|B>
#   | swap <sha> | restore b1 | restore b2
# Run A = setup b1 slave "$OLD"; run B = swap "$FIX". Expected: A chases/hunts, B = 1 exact seek a click.
set -euo pipefail
cd "$(dirname "$0")/.."
OLD=${OLD:-$(git rev-parse origin/master)}; FIX=${FIX:-$(git rev-parse HEAD)}
SSHO=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o UpdateHostKeys=no)
host() { case $1 in b1) echo bench-01;; b2) echo bench-02;; *) echo "$1";; esac; }
r() { local h; h=$(host "$1"); shift; sleep 1; ssh "${SSHO[@]}" "$h" bash -s -- "$@"; }   # script on stdin

PRE=$(cat <<'EOF'
echo "== $(hostname) up $(uptime -p)"
echo "code: $(git -C /opt/HPlayer2 rev-parse --short HEAD) ($(git -C /opt/HPlayer2 rev-parse --abbrev-ref HEAD))"
echo "units:"; systemctl list-units --all --plain --no-legend 'hplayer2@*' 't062*' | sed 's/^/  /'
echo "midi:"; amidi -l 2>&1 | sed 's/^/  /'
echo "/data: $(findmnt -no SOURCE,FSTYPE,OPTIONS /data)  /tmp: $(df -h /tmp | tail -1 | awk '{print $4}') free"
grep -qw overlay /proc/filesystems && echo "overlay: yes" || echo "overlay: NOT loaded"
echo "usbfix: timer $(systemctl is-active usbfix.timer 2>/dev/null) inhibit $([ -f /run/usbfix.inhibit ] && echo SET || echo none)"
echo "ffmpeg: $(command -v ffmpeg || echo none)"
ls -d /tmp/t062 2>/dev/null && echo "WARNING: /tmp/t062 already exists"; true
EOF
)

# $1 = master|slave. Expects /tmp/t062/hp2 (code) and /tmp/t062/media/03_t062.mp4.
SETUP=$(cat <<'EOF'
set -euo pipefail
T=/tmp/t062; ROLE=$1; [ "$ROLE" = master ] && RB=01 || RB=00
findmnt -no FSTYPE /data | grep -q overlay && { echo "already set up"; exit 1; }
[ -s $T/media/03_t062.mp4 ] || { echo "no clip in $T/media"; exit 1; }
grep -qw overlay /proc/filesystems || modprobe overlay
mkdir -p $T/lower $T/up $T/work
systemctl list-units --plain --no-legend --state=active,activating 'hplayer2@*' | awk '{print $1}' > $T/units.before
echo "stopping: $(tr '\n' ' ' < $T/units.before)"
while read -r u; do [ -n "$u" ] && systemctl stop "$u"; done < $T/units.before
mount --bind /data $T/lower && mount -o remount,bind,ro $T/lower
mount -t overlay t062 -o lowerdir=$T/lower,upperdir=$T/up,workdir=$T/work /data
P=$(amidi -l | awk '/Nowde/{print $2; exit}'); [ -n "$P" ] || { echo "no Nowde MIDI port"; exit 1; }
amidi -p "$P" -S "F0 7D 08 $RB F7"; echo "node $P role <- $RB"
if [ ! -f /run/usbfix.inhibit ]; then touch /run/usbfix.inhibit $T/inhibit.ours; echo "usbfix inhibited"; fi
echo "$ROLE" > $T/role
EOF
)

# (re)start the player from /tmp/t062/hp2 as the transient unit t062; $1 = label for the log
START=$(cat <<'EOF'
set -euo pipefail
T=/tmp/t062
systemctl stop t062 2>/dev/null || true; systemctl reset-failed t062 2>/dev/null || true
P=$T/hp2/profiles/t062.py; cp $T/hp2/profiles/biennale.py $P
sed -i -e "s#^mediaPath = .*#mediaPath = ['$T/media']#" -e "s#'/data/hplayer2-biennale.cfg'#'$T/hp2.cfg'#" \
       -e 's#return (s is None) or s.isOpen()#return True  # t062: schedule forced open#' $P
grep -q "^mediaPath = \['$T/media'\]" $P && grep -q "$T/hp2.cfg" $P && grep -q 't062: schedule' $P \
  || { echo "profile seds did not all apply"; exit 1; }
systemd-run --unit=t062 --property=WorkingDirectory=$T/hp2 --setenv=LD_LIBRARY_PATH=/usr/local/lib \
  --setenv=HOME=/root --setenv=TMPDIR=/run --setenv=PYTHONUNBUFFERED=1 \
  /opt/HPlayer2/.venv/bin/python3 $T/hp2/launcher.py t062
logger -t t062 "start $(cat $T/role) on $(cat $T/hp2/SHA) ($1)"
echo "t062 started $(date +%T) as $(cat $T/role) on $(cat $T/hp2/SHA)"
EOF
)

STATUS=$(cat <<'EOF'
journalctl -u t062 --since -${1:-60}s --no-pager -o short-precise | sed 's/\x1b\[[0-9;]*m//g' \
 | grep -E 'HELLO|role|CC#100|JUMP|clock stepped|timedelay|stopped|Video ended|master|slave|Traceback|Error' \
 | cut -c1-200 | tail -${2:-25}
EOF
)

# on the master: $1 = offset in s from the current position → the seekbar's event
SEEK=$(cat <<'EOF'
python3 - "$1" <<'PY'
import json, socket, sys, urllib.request
s = socket.socket(socket.AF_UNIX); s.connect('/tmp/hplayer-player'); s.settimeout(3)
def prop(name):
    s.sendall(json.dumps({'command': ['get_property', name]}).encode() + b'\n'); buf = b''
    while True:
        buf += s.recv(4096)
        for line in buf.split(b'\n'):
            try: m = json.loads(line)
            except ValueError: continue
            if 'error' in m: return m.get('data')
pos, dur = prop('time-pos'), prop('duration')
if pos is None or not dur: sys.exit('master not playing (time-pos %r, duration %r)' % (pos, dur))
target = min(max(5.0, pos + float(sys.argv[1])), dur - 30)
base = 'http://127.0.0.1/socket.io/?EIO=4&transport=polling'
hs = urllib.request.urlopen(base, timeout=5).read().decode()
url = base + '&sid=' + json.loads(hs[hs.index('{'):])['sid']
post = lambda b: urllib.request.urlopen(urllib.request.Request(url, data=b.encode(), method='POST'), timeout=5).read()
post('40'); urllib.request.urlopen(url, timeout=5).read()
post('42' + json.dumps(['event', {'event': 'seek', 'data': int(target * 1000)}]))
print('master %.1fs -> seek %.1fs (%+.0fs) of %.0fs' % (pos, target, target - pos, dur))
PY
EOF
)

MARK='logger -t t062 "$1"'

# on the slave: $1 = run label → per click: seeks, chase speed lines, last |timedelay|
COLLECT=$(cat <<'EOF'
S=$(journalctl -t t062 --no-pager -o short-unix | grep "click 1 run $1 START" | tail -1 | awk '{print $1}'); S="@${S%%.*}"
[ "$S" != "@" ] || { echo "no run $1 markers"; exit 1; }
{ journalctl -t t062 --since "$S" --no-pager -o short-precise; journalctl -u t062 --since "$S" --no-pager -o short-precise; } \
 | sed 's/\x1b\[[0-9;]*m//g' | sort -s -k1,3 \
 | grep -E 't062|clock stepped|JUMP|timedelay|CC#100|stopped|Video ended|Traceback' | cut -c1-210 > /tmp/t062/run-$1.log
grep -vE 'timedelay' /tmp/t062/run-$1.log
echo "== per click, run $1: exact seeks · keyframe JUMPs · clock-step · chase ticks (|d|>0.1) · last |timedelay|"
awk '/t062.*click [0-9]+ run .* START/{for(i=1;i<=NF;i++) if($i=="click") k=$(i+1)}
     /t062.*run .* END/{k=""}
     k!="" && /JUMP exact/{e[k]++} k!="" && /JUMP \(fix/{j[k]++} k!="" && /clock stepped/{c[k]++}
     k!="" && match($0,/timedelay=-?[0-9.]+/){d=substr($0,RSTART+10,RLENGTH-10)+0; if(d<0)d=-d; if(d>0.1)t[k]++; last[k]=d}
     k!=""{seen[k]=1}
     END{for(x in seen) printf "click %s: exact %d · keyframe %d · step %d · chase-ticks %d · last %.2fs\n", x, e[x], j[x], c[x], t[x], last[x]}' \
  /tmp/t062/run-$1.log | sort
EOF
)

RESTORE=$(cat <<'EOF'
set -uo pipefail
T=/tmp/t062
systemctl stop t062 2>/dev/null; systemctl reset-failed t062 2>/dev/null
P=$(amidi -l | awk '/Nowde/{print $2; exit}'); [ -n "$P" ] && amidi -p "$P" -S 'F0 7D 08 7F F7' && echo "node $P role <- board default"
[ -f $T/inhibit.ours ] && rm -f /run/usbfix.inhibit && echo "usbfix re-armed"
if findmnt -no FSTYPE /data | grep -q overlay; then umount /data || umount -l /data; umount $T/lower || umount -l $T/lower; fi
[ -f $T/units.before ] && while read -r u; do [ -n "$u" ] && systemctl start "$u"; done < $T/units.before
cp $T/run-*.log /root/ 2>/dev/null || true
echo "restored: units $(tr '\n' ' ' < $T/units.before 2>/dev/null), /data $(findmnt -no FSTYPE /data), root $(findmnt -no OPTIONS / | cut -d, -f1)"
rm -rf $T
EOF
)

push_code() {   # $1 = host key, $2 = sha → /tmp/t062/hp2 on the box (old tree replaced)
  local h; h=$(host "$1"); sleep 1
  git archive --format=tar "$2" core launcher.py profiles | ssh "${SSHO[@]}" "$h" \
    "rm -rf /tmp/t062/hp2 && mkdir -p /tmp/t062/hp2 && tar -x -C /tmp/t062/hp2 && echo $2 > /tmp/t062/hp2/SHA"
}
push_clip() {   # the 10-min clip, made on the box (no media in git, no ffmpeg on dev37)
  r "$1" <<'EOF'
mkdir -p /tmp/t062/media; C=/tmp/t062/media/03_t062.mp4
[ -s $C ] || ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=480x270:rate=25 -t 600 \
  -c:v libx264 -preset ultrafast -crf 38 -pix_fmt yuv420p -g 50 -movflags +faststart $C
ls -l $C
EOF
}

case ${1:-} in
  pre)     for h in b1 b2; do r "$h" <<<"$PRE"; done ;;
  setup)   push_clip "$2"; [ "$3" = master ] && sha=$OLD || sha=${4:?sha}; push_code "$2" "$sha"
           r "$2" "$3" <<<"$SETUP"; r "$2" "setup" <<<"$START" ;;
  swap)    push_code b1 "${2:?sha}"; r b1 "swap" <<<"$START" ;;
  status)  r "$2" "${3:-60}" "${4:-25}" <<<"$STATUS" ;;
  clicks)  k=0; for off in 60 -90 8 40; do k=$((k+1))
             r b1 "click $k run $2 START (${off}s)" <<<"$MARK"; r b2 "$off" <<<"$SEEK"; sleep 25; done
           r b1 "run $2 END" <<<"$MARK" ;;
  collect) r b1 "$2" <<<"$COLLECT" ;;
  restore) r "$2" <<<"$RESTORE" ;;
  *) sed -n 2,14p "$0"; exit 2 ;;
esac
