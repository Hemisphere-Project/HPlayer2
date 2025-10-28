#!/bin/bash

# Install mpv with MMAL support on Raspberry Pi


check_legacy_broadcom_stack() {
  # Check for loaded kernel modules
  if lsmod | grep -q 'vc4'; then
    echo "vc4 driver loaded: Non-legacy (FKMS/DRM/KMS) stack detected."
    return 1
  fi

  if lsmod | grep -q 'bcm2835_isp'; then
    echo "bcm2835_isp module loaded."
  else
    echo "bcm2835_isp module NOT loaded."
  fi

  if lsmod | grep -q 'bcm2835_codec'; then
    echo "bcm2835_codec module loaded."
  else
    echo "bcm2835_codec module NOT loaded."
  fi

  # Check /boot/config.txt overlays
  if grep -qE '^dtoverlay=vc4-fkms-v3d' /boot/config.txt || grep -qE '^dtoverlay=vc4-kms-v3d' /boot/config.txt; then
    echo "DTO overlay vc4-fkms-v3d or vc4-kms-v3d present: Non-legacy stack."
    return 1
  fi

  # Check kernel command line for vc4
  if grep -q 'vc4' /proc/cmdline; then
    echo "Kernel command line contains 'vc4': Non-legacy stack."
    return 1
  fi

  # Check presence of MMAL libraries and /opt/vc
  if [ ! -d /opt/vc ]; then
    echo "/opt/vc directory missing: likely not legacy stack."
    return 1
  fi

  if ls /opt/vc/lib/libmmal_core.so &> /dev/null; then
    echo "Legacy Broadcom VideoCore (MMAL) stack detected."
    return 0
  else
    echo "libmmal_core.so missing: likely not legacy stack."
    return 1
  fi
}

if ! check_legacy_broadcom_stack; then
  echo "ERROR: Non-legacy video stack detected. This script requires legacy Broadcom VideoCore stack."
  exit 1
fi

echo "Legacy Broadcom stack confirmed. Proceeding with mpv build..."

#######

# Install dependencies
sudo apt install -y git build-essential meson ninja-build pkg-config python3 \
  libdrm-dev libva-dev libvdpau-dev yasm libraspberrypi-dev libasound2-dev \
  libudev-dev libinput-dev libx11-dev libxext-dev libxcb1-dev libxcb-dri3-dev \
  pulseaudio libpulse-dev libfreetype6-dev libjpeg-dev libegl1-mesa-dev \
  python3-dev libass-dev lua5.1 liblua5.1-dev librubberband-dev libsixel-dev libcaca-dev \
  libass-dev


# Clone ffmpeg source code
cd /opt
if [ -d ffmpeg-4.4 ]; then
  cd ffmpeg-4.4
  git pull
else
  git clone --branch n4.4 https://git.ffmpeg.org/ffmpeg.git ffmpeg-4.4
  cd ffmpeg-4.4
fi

# Configure and build ffmpeg
export LDFLAGS="-latomic"
./configure \
  --prefix=/usr/local \
  --enable-gpl \
  --enable-nonfree \
  --enable-shared \
  --enable-mmal \
  --enable-omx \
  --enable-omx-rpi \
  --disable-debug

make -j$(nproc)
sudo make install
sudo ldconfig

grep -qxF 'export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH' ~/.bashrc || \
echo 'export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# Clone mpv source code
cd /opt
git clone --branch v0.33.0 https://github.com/mpv-player/mpv.git mpv-0.33
cd mpv-0.33

# Configure and build mpv
./bootstrap.py
export PKG_CONFIG_PATH=/opt/vc/lib/pkgconfig:$PKG_CONFIG_PATH
./waf configure --prefix=/usr/local --enable-rpi --enable-rpi-mmal --enable-libmpv-shared
./waf build -j$(nproc)
sudo ./waf install

# System configuration
mkdir -p ~/.config/mpv
echo "
vo=rpi
hwdec=mmal
" >> ~/.config/mpv/mpv.conf

# mpv --vo=rpi --hwdec=mmal <video-file>