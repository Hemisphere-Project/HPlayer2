#!/bin/bash
BASEPATH="$(dirname "$(readlink -f "$0")")"
"$BASEPATH/scripts/install_dependencies.sh"
"$BASEPATH/scripts/install_mpv.sh"

ln -sf "$BASEPATH/hplayer2@.service" /etc/systemd/system/
ln -sf "$BASEPATH/hplayer2" /usr/local/bin/
ln -sf "$BASEPATH/hplayer2-kill" /usr/local/bin/
ln -sf "$BASEPATH/bin/mpv" /usr/local/bin/

FILE=/boot/starter.txt
if test -f "$FILE"; then
echo "## [hplayer2] multimedia player [profile]
# hplayer2@looper
" >> /boot/starter.txt
fi
