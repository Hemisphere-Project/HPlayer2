#!/bin/bash
pacman -Syuw
rm /etc/ssl/certs/ca-certificates.crt
pacman -Su

# libass / ffmpeg / mpv dependencies
pacman -S freetype2 fribidi fontconfig yasm libx264 libtool base-devel pkg-config autoconf --noconfirm
pacman -S lua luajit libvdpau libva libxv libjpeg libxkbcommon libxrandr mesa libv4l libxss libcaca sdl2 alsa-lib

# hplayer2 dependencies
pacman -S python2 python2-pip cython2 liblo
pip2 install pyliblo termcolor cherrypy netifaces
cd /usr/bin
ln -sf python2 python
cd "$(dirname "$0")"

# pkgconfig for bcm_host
if [[ $(uname -m) = armv* ]]; then
	export LIBRARY_PATH=/opt/vc/lib
	export PKG_CONFIG_PATH=/opt/vc/lib/pkgconfig/
fi

# GPIO RPi
if [[ $(uname -m) = armv* ]]; then
	sudo apt-get install python-rpi.gpio -y
fi

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



