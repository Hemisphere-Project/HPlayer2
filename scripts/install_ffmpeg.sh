#!/bin/bash

# https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=ffmpeg-mmal
# https://pimylifeup.com/compiling-ffmpeg-raspberry-pi/

pacman -S alsa-lib bzip2 fontconfig fribidi gmp gnutls gsm jack lame libass.so libavc1394 libbluray.so --noconfirm --needed
pacman -S libdav1d.so libdrm libfreetype.so libiec61883 libmodplug libomxil-bellagio libpulse libraw1394 libsoxr --noconfirm --needed
pacman -S libssh libtheora libva.so libva-drm.so libva-x11.so libvdpau libvidstab.so libvorbisenc.so libvorbis.so --noconfirm --needed
pacman -S libvpx.so libwebp libx11 libx264.so libx265.so libxcb libxext libxml2 libxv libxvidcore.so opencore-amr --noconfirm --needed
pacman -S openjpeg2 opus raspberrypi-firmware sdl2 speex v4l-utils xz zlib --noconfirm --needed
pacman -S libfdk-aac kvazaar aom zimg ladspa snappy --noconfirm --needed

git clone --depth 1 https://github.com/FFmpeg/FFmpeg.git FFmpeg
cd FFmpeg
./configure \
    --extra-cflags="-I/usr/local/include" \
    --extra-ldflags="-L/usr/local/lib" \
    --extra-libs="-lpthread -lm" \
    --arch=armel \
    --enable-fontconfig \
    --enable-gmp \
    --enable-gpl \
    --enable-libaom \
    --enable-ladspa \
    --enable-libass \
    --enable-libbluray \
    --enable-libdav1d \
    --enable-libdrm \
    --enable-libfdk-aac \
    --enable-libfreetype \
    --enable-libfribidi \
    --enable-libgsm \
    --enable-libiec61883 \
    --enable-libjack \
    --enable-libkvazaar \
    --enable-libmp3lame \
    --enable-libopencore-amrnb \
    --enable-libopencore-amrwb \
    --enable-libopenjpeg \
    --enable-libopus \
    --enable-libpulse \
    --enable-libsnappy \
    --enable-libsoxr \
    --enable-libspeex \
    --enable-libssh \
    --enable-libtheora \
    --enable-libv4l2 \
    --enable-libvidstab \
    --enable-libvorbis \
    --enable-libvpx \
    --enable-libzimg \
    --enable-libwebp \
    --enable-libx264 \
    --enable-libx265 \
    --enable-libxcb \
    --enable-libxml2 \
    --enable-libxvid \
    --enable-mmal \
    --enable-nonfree \
    --enable-omx \
    --enable-omx-rpi \
    --enable-shared \
    --enable-version3 \
    --target-os=linux \
    --enable-pthreads \
    --enable-openssl \
    --enable-hardcoded-tables
    
make -j$(nproc)
make install
cd ..

echo '/usr/local/lib' > /etc/ld.so.conf.d/99local.conf
ldconfig


## MPV
git clone https://github.com/mpv-player/mpv.git
cd mpv
set -e
export LC_ALL=C
export LIBRARY_PATH=/opt/vc/lib
export PKG_CONFIG_PATH=/opt/vc/lib/pkgconfig/:/usr/lib/pkgconfig/:/usr/local/lib/pkgconfig/

./bootstrap.py
./waf configure --enable-rpi --enable-rpi-mmal

cd ..