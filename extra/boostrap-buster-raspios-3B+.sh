#!/bin/bash

#
#   :: Rasta 8 :: arm 32bits :: xbian :: 10/02/2025 ::
#

### Burn image from raspbery pi official website (32bit current version)
### https://www.raspberrypi.com/software/operating-systems/

### Boot with a keyboard and a screen
### login: pi
### password: pi

### Start raspi-config
###
# sudo raspi-config

### 3. Interface Options
### I1 SSH  => Enable

### 5. Localisation 
### L2 Timezone => Paris
### L3 Keyboard => France
### L4 WLAN Country => AU (Australia !)

### 6. Advanced Options
### A2 Network Interface Names => Enable predictable names
### A6 Wayland => Select X11

### Finnish => Reboot

### SSH from remote
# ssh pi@<ip>
sudo su root 
# cd /opt && apt update && apt install -y git && git clone https://github.com/Hemisphere-Project/Pi-tools.git && cd Pi-tools/boostrap && ./bootstrap-raspbian-32bits.sh

### Update
###
apt update
apt upgrade -y

### Change passwords
###
echo "root:rootpi" | chpasswd
echo "pi:pi" | chpasswd


### enable SSH root login
###
sed -i "s/PermitRootLogin.*/PermitRootLogin yes/g" /etc/ssh/sshd_config
sed -i "s/#PermitRootLogin/PermitRootLogin/g" /etc/ssh/sshd_config
sed -i "s/UsePAM yes/UsePAM no/g" /etc/ssh/sshd_config

### generate root ssh keys
###
cd /root
cat /dev/zero | ssh-keygen -q -N ""      # => no password

### prevent ssh hang
###
echo "IPQoS 0x00" >> /etc/ssh/ssh_config
echo "IPQoS 0x00" >> /etc/ssh/sshd_config

### restart ssh
###
systemctl restart sshd
# [from remote machine] ssh-copy-id root@<IP-ADDRESS>


### python & tools
###
apt -y install git wget tmux imagemagick htop python3 pipx pipenv libsensors5 build-essential lsof
#pipx install poetry
#pipx ensurepath
#source ~/.bashrc
#poetry completions bash >> ~/.bash_completion
#poetry config virtualenvs.in-project true
# apt -y install python3 python3-pip python3-setuptools python3-wheel python3-rpi.gpio
curl -LsSf https://astral.sh/uv/install.sh | sh   # UV install

## nodejs 
apt install nodejs npm -y
npm i -g n
# n lts
n 18
hash -r
npm install -g npm
npm install -g pm2 nodemon
npm update -g

### mosquitto server
###
#apt -y install mosquitto 
#systemctl disable mosquitto

### avahi / mdns
###
apt -y install avahi-daemon libnss-mdns  
sed -i 's/use-ipv6=yes/use-ipv6=no/g' /etc/avahi/avahi-daemon.conf
systemctl enable avahi-daemon
systemctl start avahi-daemon

### randomness
###
apt -y install haveged 
systemctl enable haveged
systemctl start haveged

### switch from netplan/networkd to NetworkManager/dnsmasq
###
apt -y install dnsmasq 
systemctl stop systemd-networkd
systemctl disable systemd-networkd
systemctl disable NetworkManager-wait-online.service

hostnamectl set-hostname rasta-00

apt -y install network-manager
systemctl disable dhcpcd
systemctl stop dhcpcd
systemctl disable wpa_supplicant
systemctl stop wpa_supplicant
systemctl disable networking
systemctl stop networking
systemctl enable NetworkManager
systemctl start NetworkManager

echo "[main]
plugins=keyfile
dns=none

[connection]
wifi.powersave = 2

[keyfile]
unmanaged-devices=interface-name:p2p-dev-*
" > /etc/NetworkManager/NetworkManager.conf

mkdir -p /etc/dnsmasq.d/
systemctl enable dnsmasq
systemctl start dnsmasq

## Resolve.conf (overwrite)
###
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf > /dev/null

### rename internal wifi interface to wint
echo 'SUBSYSTEM=="net", ACTION=="add", ENV{ID_NET_DRIVER}=="brcmfmac", NAME="wint"' > /etc/udev/rules.d/81-persistent-net.rules
udevadm control --reload
udevadm trigger

### disable ipv6
###
echo '# Disable IPv6
net.ipv6.conf.all.disable_ipv6 = 1' > /etc/sysctl.d/40-ipv6.conf

### network interface name persistence
### 
sed -i 's/rootwait/rootwait net.ifnames=0/g' /boot/cmdline.txt

### blackboot
###
systemctl disable getty@tty1
sed -i '$ s/tty1/tty3/' /boot/cmdline.txt
sed -i '$ s/fsck.repair=yes/fsck.repair=no/' /boot/cmdline.txt
sed -i 's/rootwait/rootwait logo.nologo consoleblank=0 quiet loglevel=0 vt.global_cursor_default=0/g' /boot/cmdline.txt
echo "setterm -cursor on" >> /root/.bashrc

### touch fix (iiyama)
sed -i '$ s/rootwait/rootwait usbhid.mousepoll=0/' /boot/cmdline.txt

### i2c
###
# echo "i2c-dev" >> /etc/modules-load.d/raspberrypi.conf

### oh-my-bash
###
bash -c "$(wget https://raw.githubusercontent.com/ohmybash/oh-my-bash/master/tools/install.sh -O -)"

### version
###
echo "7.0  --  bootstraped from https://github.com/Hemisphere-Project/Pi-tools/blob/main/bootstrap/bootstrap-raspbian-legacy.sh" > /boot/VERSION

# Clean up
rm /var/lib/man-db/auto-update
systemctl mask apt-daily-upgrade
systemctl mask apt-daily
systemctl disable apt-daily-upgrade.timer
systemctl disable apt-daily.timer
apt remove --purge modemmanager -y
apt autoremove --purge -y

systemctl mask --system alsa-restore.service --now

## write config.txt
## (check if there is no new config.txt settings that you should keep)
##
cp /boot/config.txt /boot/config.txt.origin
rm /boot/config.txt

echo "
#
# Hardware overlays
#
dtparam=audio=on        
dtparam=i2c_arm=on
#dtparam=i2s=on
#dtparam=spi=on

#
# Global settings
#
arm_boost=1
force_turbo=1
camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1

#
# FastBoot
#
boot_delay=0
#dtoverlay=sdtweak,overclock_50=100  # Overclock the SD Card from 50 to 100MHz / This can only be done with at least a UHS Class 1 card, might be unstable
disable_splash=1

#
# GPU
#
# Enable DRM VC4 V3D driver
# dtoverlay=vc4-kms-v3d
# max_framebuffers=2
# disable_fw_kms_setup=1
disable_overscan=1

[pi3]
gpu_mem=200
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=82

[pi4]
#gpu_mem=400
#video=HDMI-A-1:1920x1080M@30

[all]
#dwc_otg.speed=1 #legacy USB1.1

[pi3+]
#overclock
#arm_freq=1500
#core_freq=500
#gpu_freq=500
#over_voltage=6
#sdram_freq=500

" > /boot/config.txt

## Pi-tools
cd /opt
git clone https://github.com/Hemisphere-Project/Pi-tools.git

# Deploy modules
cd /opt/Pi-tools
modules=(
    starter        # OK
    splash         # OK 
    hostrename     # OK
    rorw           # OK ( -> UUID in /boot/cmdline.txt broken)
    extendfs       # OK
    network-tools  # OK
    3615-disco     # not installed
    audioselect    # OK
    bluetooth-pi   # not installed
    webconf        # ERROR
    usbautomount   # OK
    filebrother    # OK
    synczinc      # not installed
    # rtpmidi
    # camera-server
)
for i in "${modules[@]}"; do
    cd "$i"
    ./install.sh
    cd /opt/Pi-tools
done

# HPlayer2
cd /opt
git clone https://github.com/Hemisphere-Project/HPlayer2.git
cd HPlayer2
./install.sh

# Regie
cd /opt
git clone https://github.com/KomplexKapharnaum/RPi-Regie.git
cd RPi-Regie

# Hartnet
cd /opt
git clone https://github.com/Hemisphere-Project/hartnet.js
cd hartnet.js
npm install

