#!/bin/bash
# nowde-pi-check — is this player ready to talk to a Nowde node?
#
# Run once on each RPi (root, like the hplayer2@ service): checks the shipped .venv has
# the MIDI stack, that the ALSA sequencer is reachable, what Nowde devices are plugged
# (MIDI port + CDC serial), and that no other HPlayer2 interface grabbed the CDC port.
# Exit code = number of failed checks. Read-only, changes nothing.
#
#   sudo /opt/HPlayer2/extra/utils/nowde-pi-check.sh

DIR="${HPLAYER2_DIR:-/opt/HPlayer2}"
fail=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
ko()   { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=$((fail+1)); }
info() { printf '  --   %s\n' "$*"; }

echo "== HPlayer2 checkout"
if [ -d "$DIR" ]; then
  ok "$DIR ($(git -C "$DIR" rev-parse --short HEAD 2>/dev/null || echo 'no git') on $(git -C "$DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?'))"
else
  ko "$DIR missing"; exit 1
fi
[ -f "$DIR/core/interfaces/nowde.py" ] && grep -q "build_media_sync" "$DIR/core/interfaces/nowde.py" \
  && ok "nowde.py has the master leg" || ko "nowde.py is the pre-v2 slave-only version (need master@52cd319 or later)"
grep -q "addInterface('nowde'" "$DIR/profiles/biennale.py" 2>/dev/null \
  && ok "profiles/biennale.py loads the nowde interface" || ko "profiles/biennale.py does not load nowde"

echo "== Python MIDI stack in the shipped .venv"
PY="$DIR/.venv/bin/python"
if [ -x "$PY" ]; then
  for mod in mido rtmidi timecode; do
    v=$("$PY" -c "import $mod; print(getattr($mod, '__version__', 'ok'))" 2>&1) \
      && ok "$mod $v" || ko "$mod: $v"
  done
else
  ko "$PY missing (uv sync never ran here)"
fi

echo "== ALSA sequencer"
if [ -c /dev/snd/seq ]; then
  ok "/dev/snd/seq present ($(stat -c '%U:%G %a' /dev/snd/seq))"
  id -nG | tr ' ' '\n' | grep -qx audio && ok "$(id -un) is in group audio" || info "$(id -un) not in audio (fine as root)"
else
  ko "/dev/snd/seq missing (snd-seq module not loaded?)"
fi
grep -q "SupplementaryGroups=.*audio" "$DIR/hplayer2@.service" 2>/dev/null \
  && ok "service unit has SupplementaryGroups audio" || info "service unit: no audio group (runs as root anyway)"

echo "== Nowde devices on USB"
found=0
for d in /sys/bus/usb/devices/*; do
  [ -f "$d/idVendor" ] || continue
  vid=$(cat "$d/idVendor"); pid=$(cat "$d/idProduct")
  if [ "$vid" = "303a" ] && [ "$pid" = "8000" ]; then
    found=$((found+1))
    prod=$(cat "$d/product" 2>/dev/null); ser=$(cat "$d/serial" 2>/dev/null)
    ok "USB $vid:$pid '$prod' serial=$ser at $(basename "$d")"
    for tty in "$d"/*/tty/tty* "$d"/*/tty*; do
      [ -e "$tty" ] || continue
      t=/dev/$(basename "$tty")
      holders=$(fuser "$t" 2>/dev/null)
      if [ -n "$holders" ]; then
        ko "  CDC $t is held by pid(s) $holders ($(ps -o comm= -p ${holders%% *} 2>/dev/null)) — another interface grabbed it?"
      else
        ok "  CDC $t free (debug log: screen $t 115200)"
      fi
    done
  fi
done
[ "$found" -eq 0 ] && info "no Nowde (303a:8000) plugged in right now"
if [ "$vid$pid" = "303a1001" ] 2>/dev/null; then :; fi
lsusb 2>/dev/null | grep -i "303a:1001" >/dev/null && info "an Espressif 303a:1001 device is also present (DevKit / radar / teleco2 class id)"

echo "== MIDI ports seen by mido"
if [ -x "$PY" ]; then
  "$PY" - <<'PYEOF' 2>&1 | sed 's/^/  /'
import re
try:
    import mido
    ins = mido.get_input_names(); outs = mido.get_output_names()
    nowde = [n for n in ins if re.search(r'^Nowde', n)]
    print("inputs :", ins or "none")
    print("outputs:", outs or "none")
    print("nowde  :", nowde or "none matching ^Nowde")
    if nowde and not [n for n in outs if re.search(r'^Nowde', n)]:
        print("FAIL   : Nowde input without a matching output (master leg needs both)")
except Exception as e:
    print("FAIL   :", e)
PYEOF
  "$PY" -c "import mido,re; import sys; sys.exit(0 if [n for n in mido.get_input_names() if re.search(r'^Nowde', n)] else 2)" 2>/dev/null
  case $? in 0) ok "a Nowde MIDI input is visible";; 2) info "no Nowde MIDI input (nothing plugged, or the node runs in USB-JTAG mode)";; *) ko "mido could not list ports";; esac
fi

echo "== Service"
inst=$(systemctl list-units 'hplayer2@*' --no-legend 2>/dev/null | awk '{print $1}' | head -1)
[ -n "$inst" ] && ok "$inst $(systemctl is-active "$inst")" || info "no hplayer2@ instance running"
[ -n "$inst" ] && journalctl -u "$inst" --no-pager -n 400 2>/dev/null | grep -i "\[NOWDE" | tail -5 | sed 's/^/  log: /'

echo
[ "$fail" -eq 0 ] && echo "READY — $fail failed check(s)" || echo "NOT READY — $fail failed check(s)"
exit $fail
