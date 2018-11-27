#!/bin/bash
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi

##
## Install plateform spcific dependencies
##
distro=''

## xBIAN (DEBIAN / RASPBIAN / UBUNTU)
if [[ $(command -v apt) ]]; then
    distro='xbian'

    # libass / ffmpeg / mpv dependencies
    apt install libfreetype6-dev libfribidi-dev libfontconfig1-dev yasm libx264-dev git libtool build-essential pkg-config autoconf -y
    apt install liblua5.1-0-dev libluajit-5.1-dev libvdpau-dev libva-dev libxv-dev libjpeg-dev libxkbcommon-dev  -y
    apt install libxrandr-dev libgles2-mesa-dev libgles1-mesa-dev libv4l-dev libxss-dev libgl1-mesa-dev -y
    apt install libcaca-dev libsdl2-dev libasound2-dev -y

    # hplayer2 dependencies
    apt install python3-pip python3-liblo -y
    /usr/bin/yes | pip3 install netifaces termcolor evdev socketio flask-socketio eventlet

    # GPIO RPi
    if [[ $(uname -m) = armv* ]]; then
    	apt-get install python-rpi.gpio -y
    	git clone https://github.com/adafruit/Adafruit_Python_CharLCD.git
    	cd Adafruit_Python_CharLCD
    	python3 setup.py install
    	cd ..
	    rm -Rf Adafruit_Python_CharLCD
    fi

## ARCH Linux
elif [[ $(command -v pacman) ]]; then
    distro='arch'

    # libass / ffmpeg / mpv dependencies
    pacman -S freetype2 fribidi fontconfig yasm git --noconfirm --needed
    pacman -S autoconf pkg-config libtool --noconfirm --needed
    pacman -S lua luajit libvdpau libva libxv libjpeg libxkbcommon libxrandr libv4l libxss libcaca sdl2 --noconfirm --needed
    pacman -S base-devel --noconfirm --needed    ## error ?
    pacman -S libx264 --noconfirm --needed       ## error ?
    pacman -S mesa --noconfirm --needed          ## error ?
    pacman -S fbida --noconfirm --needed         ## error ?
    pacman -S alsa-lib alsa-firmware ttf-roboto --noconfirm --needed

    # hplayer2 dependencies
    pacman -S python3 cython liblo --noconfirm --needed
    pacman -S python-pyliblo python-netifaces python-termcolor python-evdev python-flask-socketio  --noconfirm --needed

    # GPIO RPi
    if [[ $(uname -m) = armv* ]]; then
      pacman -S python-pip python-queuelib  --noconfirm --needed
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
    echo "this script needs APT packet manager to run."
    echo ""
    echo "Please install dependencies manually."
    exit 1
fi



#######
# COMPILE MPV
#######

echo "Building MPV for your system..."

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

# RPi MMAL
if [[ $(uname -m) = armv* ]]; then
	echo --enable-mmal > ffmpeg_options
	echo --disable-vaapi > mpv_options
fi

# Build
./use-mpv-release
./use-ffmpeg-release
./update
./rebuild -j4
cd ..

# Copy bin
mkdir -p ../bin
cp mpv-build/mpv/build/mpv  ../bin/mpv

# Clean
read -r -p "Clean mpv-build directory? [Y/n] " -n 1 response
echo
case "$response" in
    [nN])
        exit 0
        ;;
    *)
        rm -fR mpv-build
        ;;
esac
exit 0
