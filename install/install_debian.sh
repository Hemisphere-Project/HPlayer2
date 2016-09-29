#!/bin/bash
sudo apt update && sudo apt upgrade -y

# libass / ffmpeg / mpv dependencies
sudo apt install libfreetype6-dev libfribidi-dev libfontconfig1-dev
sudo apt install yasm libx264-dev  -y
sudo apt install git libtool build-essential pkg-config autoconf -y
sudo apt install liblua5.1-0-dev libluajit-5.1-dev -y
sudo apt install libvdpau-dev libva-dev libxv-dev libjpeg-dev libxkbcommon-dev libxinerama-dev -y
sudo apt install libxrandr-dev libgles2-mesa-dev libgles1-mesa-dev libv4l-dev libxss-dev libgl1-mesa-dev libgl2-mesa-dev -y

# hplayer2 dependencies


#libxcb-xfixes0-dev libsdl1.2-dev libenca-dev
#libxcb-render0-dev libwayland-dev libwayland-client0 libwayland-cursor0 libwayland-egl1-mesa
#fonts-dejavu-core libaacs-dev libass-dev libbluray-dev
#libbs2b-dev libcdio-cdda-dev libcdio-paranoia-dev libcaca-dev libasound2-dev
#libx11-dev -y

git clone https://github.com/mpv-player/mpv-build.git
cd mpv-build
echo --enable-libmpv-shared > mpv_options
echo --enable-mmal >> ffmpeg_options
./rebuild -j4
#sudo ./install
