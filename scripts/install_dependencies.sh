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
    apt install python3 python3-pip
    apt install python3-termcolor python3-evdev python3-eventlet -y
    apt install python3-watchdog python3-pillow python3-setuptools -y
    apt install ttf-dejavu-core python3-pyserial libjack-dev libtool autotools-dev automake liblo7 -y

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
    pacman -S pkg-config python python-pip cython liblo libxcrypt python-termcolor python-evdev python-eventlet \
        python-watchdog python-pillow python-setuptools ttf-dejavu python-pyserial --noconfirm --needed

    # RPi
    if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
      pacman -S python-queuelib i2c-tools --noconfirm --needed
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
pip3 install -r requirements.txt

# RPi
if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
    /usr/bin/yes | pip install --upgrade RPi.GPIO

    git clone https://github.com/adafruit/Adafruit_Python_CharLCD.git
    cd Adafruit_Python_CharLCD
    python setup.py install
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
cd bindings/python/ && python setup.py build && python setup.py install

cd /tmp
git clone git://github.com/zeromq/zyre.git && cd zyre
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libzyre.so.2 /usr/lib/
cd bindings/python/ && python setup.py build && python setup.py install



exit 0
