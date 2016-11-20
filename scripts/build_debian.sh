#!/bin/bash
sudo apt update

##############
# DEPENDENCIES
##############

# libass / ffmpeg / mpv dependencies
sudo apt install libfreetype6-dev libfribidi-dev libfontconfig1-dev -y
sudo apt install yasm libx264-dev  -y
sudo apt install git libtool build-essential pkg-config autoconf -y
sudo apt install liblua5.1-0-dev libluajit-5.1-dev -y
sudo apt install libvdpau-dev libva-dev libxv-dev libjpeg-dev libxkbcommon-dev libxinerama-dev -y
sudo apt install libxrandr-dev libgles2-mesa-dev libgles1-mesa-dev libv4l-dev libxss-dev libgl1-mesa-dev -y
sudo apt install libcaca-dev libsdl2-dev libasound2-dev -y

# hplayer2 dependencies
sudo apt install python-termcolor python-liblo python-cherrypy -y

#######
# BUILD
#######

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
./rebuild -j4
cd ..

# Copy bin
mkdir -p bin
cp mpv-build/mpv/build/mpv  bin/mpv

# Clean
rm -fR mpv-build
