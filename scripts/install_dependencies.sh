#!/bin/bash

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi

cd "$(dirname "$(readlink -f "$0")")"

##
## Install plateform spcific dependencies
##
DISTRO=''

## xBIAN (DEBIAN / RASPBIAN / UBUNTU)
if [[ $(command -v apt) ]]; then
    DISTRO='xbian'

    # libass / ffmpeg / mpv dependencies
    apt install libfreetype6-dev libfribidi-dev libfontconfig1-dev yasm libx264-dev git libtool build-essential checkinstall pkg-config autoconf -y
    apt install liblua5.1-0-dev libluajit-5.1-dev libvdpau-dev libva-dev libxv-dev libjpeg-dev libxkbcommon-dev  -y
    apt install libxrandr-dev libgles2-mesa-dev libgles1-mesa-dev libv4l-dev libxss-dev libgl1-mesa-dev -y
    apt install libcaca-dev libsdl2-dev libasound2-dev -y

    # hplayer2 dependencies
    apt install python3 python3-pip -y
    apt install python3-liblo python3-netifaces python3-termcolor python3-evdev python3-flask-socketio python3-eventlet -y
    apt install python3-watchdog python3-pillow python3-setuptools python3-zeroconf -y
    apt install ttf-dejavu-core python3-pyserial libjack-dev libtool autotools-dev automake -y
    /usr/bin/yes | pip3 install --upgrade python-socketio

    # RPi
    if [[ $(uname -m) = armv* ]]; then
    	apt-get install i2c-tools -y
    fi

## ARCH Linux
elif [[ $(command -v pacman) ]]; then
    DISTRO='arch'

    # libass / ffmpeg / mpv dependencies
    pacman -S freetype2 fribidi fontconfig yasm git autoconf pkg-config libtool --noconfirm --needed
    pacman -S lua luajit libvdpau libva libxv libjpeg libxkbcommon libxrandr libv4l libxss libcaca sdl2 --noconfirm --needed
    pacman -S base-devel libx264 mesa fbida libbluray --noconfirm --needed
    pacman -S alsa-lib alsa-firmware ttf-roboto --noconfirm --needed

    # hplayer2 dependencies
    pacman -S pkg-config python3 python3-dev python3-pip cython liblo --noconfirm --needed
    pacman -S python3-pyliblo python3-netifaces python3-termcolor python3-evdev python3-flask-socketio  --noconfirm --needed
    pacman -S python3-watchdog python3-pillow python3-setuptools python3-zeroconf python3-socketio --noconfirm --needed
    pacman -S ttf-dejavu python3-pyserial --noconfirm --needed

    # RPi
    if [[ $(uname -m) = armv* ]]; then
      pacman -S python3-queuelib i2c-tools --noconfirm --needed
    fi

## Plateform not detected ...
else
    echo "Distribution not detected:"
    echo "this script needs APT or PACMAN to run."
    echo ""
    echo "Please install dependencies manually."
    exit 1
fi

#####
# COMMON PARTS
####

# PIP
/usr/bin/yes | pip3 install --upgrade wheel
/usr/bin/yes | pip3 install --upgrade pymitter
/usr/bin/yes | pip3 install --upgrade mido
/usr/bin/yes | pip3 install --upgrade python3-rtmidi
/usr/bin/yes | pip3 install --upgrade paho-mqtt


# RPi
if [[ $(uname -m) = armv* ]]; then
    /usr/bin/yes | pip3 install --upgrade RPi.GPIO

    git clone https://github.com/adafruit/Adafruit_Python_CharLCD.git
    cd Adafruit_Python_CharLCD
    python3 setup.py install
    cd .. && rm -Rf Adafruit_Python_CharLCD
fi

# ZYRE
cd /tmp
git clone git://github.com/zeromq/libzmq.git && cd libzmq
./autogen.sh && ./configure && make check -j4
make install && ldconfig

cd /tmp
git clone git://github.com/zeromq/czmq.git && cd czmq
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libczmq.so.4 /usr/lib/
cd bindings/python/ && python3 setup.py build && python3 setup.py install

cd /tmp
git clone git://github.com/zeromq/zyre.git && cd zyre
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libzyre.so.2 /usr/lib/
cd bindings/python/ && python3 setup.py build && python3 setup.py install



exit 0
