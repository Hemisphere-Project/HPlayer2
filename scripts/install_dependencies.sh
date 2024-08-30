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

    # GStreamer
    apt install libdrm libmpg123 gstreamer1.0-plugins-ugly libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-pulseaudio gstreamer1.0-x gstreamer1.0-plugins-bad gstreamer1.0-alsa gstreamer1.0-plugins-base gstreamer1.0-plugins-good -y

    # hplayer2 dependencies
    apt install python3 rsync pipenv python-is-python3 -y
    apt install libtool autotools-dev automake pkg-config m4 autoconf -y

    # RPi
    if [[ $(uname -m) = armv* ]]; then
    	apt-get install i2c-tools -y
    fi

## ARCH Linux
elif [[ $(command -v pacman) ]]; then
    DISTRO='arch'

    # GStreamer
    pacman -S gst-python libdrm mpg123 gst-plugins-ugly gst-libav gst-plugins-base-libs gstreamer gst-plugins-bad gst-plugins-base gst-plugins-good --noconfirm --needed
    
    # hplayer2 dependencies
    pacman -S pkg-config python cython liblo libxcrypt ttf-dejavu rsync python-pipenv mesa --noconfirm --needed

    # Python (with overwrites)
    pacman -S python-flask-socketio --overwrite *flask_socketio/* --overwrite *lask_SocketIO* --overwrite *socketio* --overwrite *bidict* --overwrite *engineio* --overwrite *flask* --overwrite *blinker* --overwrite *click* --overwrite *jinja2* --overwrite *itsdangerous* --overwrite *werkzeug* --overwrite *markupsafe* --overwrite *six* --noconfirm --needed    
    pacman -S python-netifaces --overwrite *netifaces* --noconfirm --needed
    pacman -S python-wheel --noconfirm --needed
    
    
    # RPi
    if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
      pacman -S i2c-tools --noconfirm --needed
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



# ZYRE
cd /tmp
git clone https://github.com/zeromq/libzmq.git --depth=1 && cd libzmq
./autogen.sh && ./configure && make check -j4
make install && ldconfig

cd "$(dirname "$(readlink -f "$0")")"
git clone https://github.com/zeromq/czmq.git --depth=1 && cd czmq
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libczmq.so.4 /usr/lib/

# cd bindings/python/ && python setup.py build && python setup.py install
cd "$(dirname "$(readlink -f "$0")")"
git clone https://github.com/zeromq/zyre.git --depth=1 && cd zyre
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libzyre.so.2 /usr/lib/
# cd bindings/python/ && python setup.py build && python setup.py install



# PIP
cd "$(dirname "$(readlink -f "$0")")/.."
# pipenv install -r scripts/requirements.txt
# pipenv install -e "$(dirname "$(readlink -f "$0")")/czmq/bindings/python"
# pipenv install -e "$(dirname "$(readlink -f "$0")")/zyre/bindings/python"
pipenv install

# RPi
if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
    cd "$(dirname "$(readlink -f "$0")")/.."
    pipenv install RPi.GPIO
    pipenv install queuelib
    pipenv install Adafruit-CharLCD
fi

exit 0