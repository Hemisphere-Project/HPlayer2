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

systemctl mask systemd-update-utmp-runlevel.service 
systemctl disable e2scrub_reap.service
sed -i 's/$/ fsck.mode=skip/' /boot/firmware/cmdline.txt
systemctl mask NetworkManager-wait-online.service

systemctl stop hplayer2@sacvp

cd /opt/RPi-Regie 
git stash
git pull 

cd /opt/Pi-tools
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
git stash
git pull
rm -Rf .venv
uv sync
sed -i 's/^include-system-site-packages = .*/include-system-site-packages = true/' .venv/pyvenv.cfg

cd /opt/hartnet.js
git stash
git pull
npm install

cd /root
npm uninstall -g pm2
rm -Rf /root/.pm2
PM2_HOME=/data/var/.pm2
mkdir -p $PM2_HOME
npm install -g pm2
pm2 startup systemd -u root --hp /data/var
echo 'export PM2_HOME=/data/var/.pm2' >> /root/.bashrc
source /root/.bashrc
mkdir -p /etc/systemd/system/pm2-root.service.d && \
echo -e "[Service]\nEnvironment=\"PM2_HOME=/data/var/.pm2\"" | sudo tee /etc/systemd/system/pm2-root.service.d/override.conf
systemctl daemon-reload
rm -Rf /root/.pm2
pm2 save --force

echo '01-uv' >> /boot/VERSION
echo "SUCCESS !" 
cat /etc/hostname
reboot