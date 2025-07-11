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
git fetch 
git checkout sacvp-kernel4-2025 
git pull 

cd /opt/RPi-Regie 
git stash
git pull 

echo '06-kernel4-branch' >> /boot/VERSION
echo "SUCCESS !" 
cat /etc/hostname
reboot