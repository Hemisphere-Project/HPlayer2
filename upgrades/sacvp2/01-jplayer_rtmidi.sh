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

cd /opt/HPlayer2/ 
git stash
git pull 

cd /opt/RPi-Regie 
git stash
git pull 

apt update
apt upgrade -y
apt install python3-rtmidi -y
apt purge firmware-intel-graphics firmware-nvidia-graphics -y
curl -LsSf https://astral.sh/uv/install.sh | sh
apt autoremove --purge -y 
apt clean -y

cd /opt/HPlayer2/
rm -Rf .venv
uv sync
sed -i 's/^include-system-site-packages = .*/include-system-site-packages = true/' .venv/pyvenv.cfg


echo '07-jplayer_rtmidi' >> /boot/VERSION
echo "SUCCESS !" 
cat /etc/hostname
reboot