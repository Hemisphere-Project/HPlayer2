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

cd /opt/HPlayer2
git stash
git pull

# Internal wifi as WINT
echo 'ACTION=="add", SUBSYSTEM=="net", DRIVERS=="brcmfmac", NAME="wint"' > /etc/udev/rules.d/72-static-name.rules

# Switch from rasta-modules to Pi-tools
# cd /opt
# git clone https://github.com/Hemisphere-Project/Pi-tools

# # Starter
# mv /boot/starter.txt /boot/starter.txt.bak
# cd /opt/Pi-tools/starter
# ./install.sh

# cd /opt/Pi-tools/hostrename
# ./install.sh

# cd /opt/Pi-tools/network-tools
# ./install.sh



# RPi-Update !
cd /root
sudo curl -L --output /usr/bin/rpi-update https://raw.githubusercontent.com/Hexxeh/rpi-update/master/rpi-update && sudo chmod +x /usr/bin/rpi-update
rpi-update


echo '05-kernel' >> /boot/VERSION
echo "SUCCESS !" 
cat /etc/hostname
reboot