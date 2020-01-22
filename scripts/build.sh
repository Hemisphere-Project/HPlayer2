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
    apt install libfreetype6-dev libfribidi-dev libfontconfig1-dev yasm libx264-dev git libtool build-essential pkg-config autoconf -y
    apt install liblua5.1-0-dev libluajit-5.1-dev libvdpau-dev libva-dev libxv-dev libjpeg-dev libxkbcommon-dev  -y
    apt install libxrandr-dev libgles2-mesa-dev libgles1-mesa-dev libv4l-dev libxss-dev libgl1-mesa-dev -y
    apt install libcaca-dev libsdl2-dev libasound2-dev -y

    # hplayer2 dependencies
    apt install python3-liblo python3-netifaces python3-termcolor python3-evdev python3-flask-socketio python3-eventlet -y
    apt install python3-watchdog python3-pillow -y
    apt install python3-pip
    /usr/bin/yes | pip3 install python-socketio

    # GPIO RPi
    if [[ $(uname -m) = armv* ]]; then
    	apt-get install python-rpi.gpio i2c-tools -y
    	git clone https://github.com/adafruit/Adafruit_Python_CharLCD.git
    	cd Adafruit_Python_CharLCD
    	python3 setup.py install
    	cd ..
	    rm -Rf Adafruit_Python_CharLCD
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
    pacman -S python3 cython liblo --noconfirm --needed
    pacman -S python-pyliblo python-netifaces python-termcolor python-evdev python-flask-socketio  --noconfirm --needed
    pacman -S python-socketio python-watchdog python-pillow --noconfirm --needed

    # GPIO RPi
    if [[ $(uname -m) = armv* ]]; then
      pacman -S python-pip python-queuelib i2c-tools --noconfirm --needed
      /usr/bin/yes | pip3 install RPi.GPIO
      git clone https://github.com/adafruit/Adafruit_Python_CharLCD.git
	  cd Adafruit_Python_CharLCD
	  python3 setup.py install
	  cd ..
	  rm -Rf Adafruit_Python_CharLCD
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
/usr/bin/yes | pip3 install --upgrade setuptools
/usr/bin/yes | pip3 install --upgrade zeroconf

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


#######
# MPV
#######

ARCHI=`uname -m`

cd "$(dirname "$(readlink -f "$0")")"

if test -f "../bin/prebuilds/mpv-$DISTRO-$ARCHI"; then
    echo "mpv build FOUND !"
    echo "copying bin/prebuilds/mpv-$DISTRO-$ARCHI"
    cp "../bin/prebuilds/mpv-$DISTRO-$ARCHI" ../bin/mpv
else
    echo "mpv build NOT FOUND :("
    echo "Building MPV for your system..."

    ## FIX
    # pkgconfig for bcm_host
    if [[ $(uname -m) = armv* ]]; then
    export LIBRARY_PATH=/opt/vc/lib
    export PKG_CONFIG_PATH=/opt/vc/lib/pkgconfig/
    fi

    # Get MPV Build tools
    cd "$(dirname "$0")"
    rm -rf mpv-build
    git clone https://github.com/mpv-player/mpv-build.git
    cd mpv-build
    #echo --enable-libmpv-shared > mpv_options

    # RPi: enable MMAL
    if [[ $(uname -m) = armv* ]]; then
        echo --enable-mmal > ffmpeg_options
        # echo --enable-libv4l2 > ffmpeg_options
        # echo --disable-vaapi > mpv_options
        # echo --enable-rpi > mpv_options
    fi

    # Build
    ./use-mpv-release
    ./use-ffmpeg-release

    # fixed rebuild
    set -e
    export LC_ALL=C
    ./update
    ./clean
    cd mpv 
    git checkout refs/tags/"v0.29.1"    # 0.30.0 release is broken on RPi
    cd ..

    if [[ $(uname -m) = armv* ]]; then
        ./build -j4
    else
        ./build -j8
    fi
    cd ..

    # Copy bin
    mkdir -p ../bin
    cp mpv-build/mpv/build/mpv  ../bin/mpv


    # Clean
    rm -fR mpv-build

fi

exit 0
