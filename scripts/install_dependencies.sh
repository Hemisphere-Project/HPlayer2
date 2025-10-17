#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"

# Dummy sudo request to ask for password at the beginning
sudo echo ""

# exit on error
set -e

##
## Install plateform spcific dependencies
##
DISTRO=''

## xBIAN (DEBIAN / RASPBIAN / UBUNTU)
if [[ $(command -v apt) ]]; then
    DISTRO='xbian'

    # MPV
    sudo apt install mpv -y

    # GStreamer
    # sudo apt install libdrm libmpg123 gstreamer1.0-plugins-ugly libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-pulseaudio gstreamer1.0-x gstreamer1.0-plugins-bad gstreamer1.0-alsa gstreamer1.0-plugins-base gstreamer1.0-plugins-good -y

    # hplayer2 dependencies
    sudo apt install python3 rsync libdrm-dev libgbm-dev libgles-dev libegl-dev libegl1-mesa-dev libgles2-mesa-dev -y
    sudo apt install libffi-dev libjack-dev libjpeg-dev libtool autotools-dev automake libopenblas0 cython3 python3-opencv -y
    sudo apt install libzmq3-dev -y

    # RPi
    if [[ $(uname -m) = armv* ]]; then
    	sudo apt-get install i2c-tools -y
    fi

## ARCH Linux
elif [[ $(command -v pacman) ]]; then
    DISTRO='arch'

    # MPV
    sudo pacman -S mpv --noconfirm --needed

    # GStreamer
    # sudo pacman -S gst-python libdrm mpg123 gst-plugins-ugly gst-libav gst-plugins-base-libs gstreamer gst-plugins-bad gst-plugins-base gst-plugins-good --noconfirm --needed
    
    # hplayer2 dependencies
    sudo pacman -S pkg-config python cython liblo libxcrypt ttf-dejavu rsync python-pipenv mesa --noconfirm --needed

    # Python (with overwrites)
    # sudo pacman -S python-flask-socketio --overwrite *flask_socketio/* --overwrite *lask_SocketIO* --overwrite *socketio* --overwrite *bidict* --overwrite *engineio* --overwrite *flask* --overwrite *blinker* --overwrite *click* --overwrite *jinja2* --overwrite *itsdangerous* --overwrite *werkzeug* --overwrite *markupsafe* --overwrite *six* --noconfirm --needed    
    # sudo pacman -S python-netifaces --overwrite *netifaces* --noconfirm --needed
    # sudo pacman -S python-wheel --noconfirm --needed


    # RPi
    if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
      sudo pacman -S i2c-tools --noconfirm --needed
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


# ZMQ
# cd /tmp
# git clone https://github.com/zeromq/libzmq.git --depth=1 && cd libzmq
# ./autogen.sh && ./configure && make check -j4
# make install && ldconfig


# CZMQ
cd "$(dirname "$(readlink -f "$0")")"
git clone https://github.com/zeromq/czmq.git --depth=1 && cd czmq
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libczmq.so.4 /usr/lib/
# cd bindings/python/ && python setup.py build && python setup.py install
cd "$(dirname "$(readlink -f "$0")")/.."
# uv add --editable "$(dirname "$(readlink -f "$0")")/czmq/bindings/python"

# ZYRE
cd "$(dirname "$(readlink -f "$0")")"
git clone https://github.com/zeromq/zyre.git --depth=1 && cd zyre
./autogen.sh && ./configure && make check -j4
make install && ldconfig
ln -s /usr/local/lib/libzyre.so.2 /usr/lib/
# cd bindings/python/ && python setup.py build && python setup.py install
cd "$(dirname "$(readlink -f "$0")")/.."
# uv add --editable "$(dirname "$(readlink -f "$0")")/zyre/bindings/python"

# UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# UV dep install
cd "$(dirname "$(readlink -f "$0")")"
cd ..
uv sync
sed -i 's/^include-system-site-packages = .*/include-system-site-packages = true/' .venv/pyvenv.cfg


# RPi
# if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
#     cd "$(dirname "$(readlink -f "$0")")/.."
#     pipenv install RPi.GPIO
#     pipenv install queuelib
#     pipenv install Adafruit-CharLCD
# fi

exit 0
