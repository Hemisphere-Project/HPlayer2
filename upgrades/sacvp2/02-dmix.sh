#!/bin/bash

# exit when any command fails
set -e

  # keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
  # echo an error message before exiting
trap 'echo "\"${last_command}\" command filed with exit code $?."' EXIT

rw 
chmod -R 777 /tmp
date -s "$(curl -s --head http://google.com | grep ^Date: | sed 's/Date: //g')"

cd /opt/RPi-Regie
git stash
git pull

cd /opt/Pi-tools
git stash
git pull

cd /opt/HPlayer2/
git stash
git pull

cd /opt/hartnet.js
git stash
git pull

cd /opt/Pi-Tools/audioselect
rm -Rf /etc/asound.conf
cp -f ./asound.conf-pi2 /etc/asound.conf

echo '02-dmix' >> /boot/VERSION
echo "SUCCESS !" 
cat /etc/hostname
reboot