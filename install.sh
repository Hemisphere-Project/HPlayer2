#!/bin/bash
BASEPATH="$(dirname "$(readlink -f "$0")")"

# detect xbian (apt based)
if [[ $(command -v apt) ]]; then
    echo "xBIAN detected. Running xBIAN install script."
    bash "$BASEPATH/scripts/install_xbian.sh" "$@"
    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        echo "xBIAN installation script failed with exit code $EXIT_CODE"
        exit $EXIT_CODE
    fi
else
    echo "Non-xBIAN system detected. Running macOS install script."
    bash "$BASEPATH/scripts/install_macos.sh" "$@"
    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        echo "macOS installation script failed with exit code $EXIT_CODE"
        exit $EXIT_CODE
    fi
fi

# "$BASEPATH/scripts/install_dependencies.sh"
#"$BASEPATH/scripts/install_mpv.sh"

ln -sf "$BASEPATH/hplayer2@.service" /etc/systemd/system/
ln -sf "$BASEPATH/hplayer2" /usr/local/bin/
ln -sf "$BASEPATH/hplayer2-kill" /usr/local/bin/

FILE=/boot/starter.txt
if test -f "$FILE"; then
echo "## [hplayer2] multimedia player [profile]
# hplayer2@looper
" >> /boot/starter.txt
fi
