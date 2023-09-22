
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

# disable warnings OSD
sed -i '/^disable_splash=1/a avoid_warnings=1    # Hide Lightning Bolt (low voltage) and Temperature warnings' /boot/config.txt

# systemctl stop hplayer2@sacvp
cd /opt/HPlayer2
git stash
git pull

echo '04-lightning' >> /boot/VERSION
echo "SUCCESS !" 
cat /etc/hostname
reboot
