#!/bin/bash
BASEPATH="$(dirname "$(readlink -f "$0")")"
"$BASEPATH/scripts/build.sh"

ln -sf "$BASEPATH/hplayer2@.service" /etc/systemd/system/
ln -sf "$BASEPATH/hplayer2" /usr/local/bin/

FILE=/boot/starter.txt
if test -f "$FILE"; then
echo "## [hplayer2] multimedia player [profile]
# hplayer2@looper
" >> /boot/starter.txt
fi