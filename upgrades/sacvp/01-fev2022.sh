
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

pacman -Sy
pip install --upgrade pip

cd /opt/HPlayer2
git checkout master
git stash
git pull

sed -i 's/^hplayer2@.*/hplayer2@sacvp/g' /boot/starter.txt

/usr/bin/yes | pip uninstall python-socketio
/usr/bin/yes | pip uninstall python-engineio
/usr/bin/yes | pip install --upgrade flask-socketio
cd /opt/RPi-Regie
git checkout master
git stash
git pull

cd /opt/rasta-modules/3615-disco
git checkout master
git stash
git pull

cd /opt/rasta-modules/audioselect
git checkout master
git stash
git pull

cd /opt/rasta-modules/hostrename
git checkout master
git stash
git pull

cd /opt/rasta-modules/network-tools
git checkout master
git stash
git pull

cd /opt/rasta-modules/rorw
git checkout master
git stash
git pull

cd /opt/rasta-modules/starter
git checkout master
git stash
git pull

pacman -S syncthing --noconfirm
rm -f /data/var/drive-id
rm -f /data/var/sync-id
cd /opt/rasta-modules/synczinc
git checkout master
git stash
git pull

cd /opt/rasta-modules/usbautomount
git checkout master
git stash
git pull

cd /opt/rasta-modules/webfiles
git checkout master
git stash
git pull

cd /opt/rasta-modules
git clone https://framagit.org/KXKM/rpi-modules/extendfs.git
cd extendfs
./install.sh
sed -i 's/# extendfs/extendfs/' /boot/starter.txt

cd /opt/rasta-modules
git clone https://framagit.org/KXKM/rpi-modules/webconf.git
cd webconf
./install.sh
sed -i 's/# webconf/webconf/' /boot/starter.txt

sed -i 's/# mosquitto/# mosquitto\n/' /boot/starter.txt

systemctl daemon-reload 


chmod -R 700 /var/lib/NetworkManager/
chmod -R 700 /etc/NetworkManager/system-connections


echo 'RastaOS-6.1-sacvp.img' > /boot/VERSION
echo '01-fev2022' >> /boot/VERSION

pacman -S networkmanager libnm libutil-linux --noconfirm # nm 1.22.8-1 > 1.34.0-1

echo "SUCCESS !" 
#reboot

