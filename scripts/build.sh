#!/bin/bash
blurp

distro=''
if [[ $(command -v apt) ]]; then
    distro='xbian'
    ./build_debian.sh

    # libass / ffmpeg / mpv dependencies
    sudo apt install libfreetype6-dev libfribidi-dev libfontconfig1-dev yasm libx264-dev git libtool build-essential pkg-config autoconf -y
    sudo apt install liblua5.1-0-dev libluajit-5.1-dev libvdpau-dev libva-dev libxv-dev libjpeg-dev libxkbcommon-dev  -y
    sudo apt install libxrandr-dev libgles2-mesa-dev libgles1-mesa-dev libv4l-dev libxss-dev libgl1-mesa-dev -y
    sudo apt install libcaca-dev libsdl2-dev libasound2-dev -y

    # hplayer2 dependencies
    sudo apt install python-pip python-termcolor python-liblo -y
    sudo pip install cherrypy netifaces -y

    # GPIO RPi
    if [[ $(uname -m) = armv* ]]; then
    	sudo apt-get install python-rpi.gpio -y
    fi


elif [[ $(command -v pacman) ]]; then
    distro='arch'

    # libass / ffmpeg / mpv dependencies
    pacman -S freetype2 fribidi fontconfig yasm libx264 git libtool base-devel pkg-config autoconf --noconfirm
    pacman -S lua luajit libvdpau libva libxv libjpeg libxkbcommon libxrandr mesa libv4l libxss libcaca sdl2 fbida --noconfirm
    pacman -S alsa-lib alsa-firmware ttf-roboto --noconfirm

    # hplayer2 dependencies
    pacman -S python python-pip cython liblo --noconfirm
    pip install pyliblo termcolor cherrypy netifaces -y

    # GPIO RPi
    if [[ $(uname -m) = armv* ]]; then
      pip install RPi.GPIO
    fi

else
    echo "Distribution not detected:"
    echo "this script needs APT packet manager to run."
    echo ""
    echo "Please install dependencies manually."
    exit 1
fi

# echo "Distribution: $distro"


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
cd ..
git clone https://github.com/mpv-player/mpv-build.git
cd mpv-build
#echo --enable-libmpv-shared > mpv_options

# RPi MMAL
if [[ $(uname -m) = armv* ]]; then
	echo --enable-mmal > ffmpeg_options
fi

# Build
./use-mpv-release
./use-ffmpeg-release
./update
./rebuild -j4
cd ..

# Copy bin
mkdir -p bin
cp mpv-build/mpv/build/mpv  bin/mpv

# Clean
# rm -fR mpv-build
