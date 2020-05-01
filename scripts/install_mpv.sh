#!/bin/bash

#######
# MPV
#######
DISTRO=''
if [[ $(command -v apt) ]]; then
    DISTRO='xbian'
elif [[ $(command -v pacman) ]]; then
    DISTRO='arch'
else
    echo "Distribution not detected.."
fi
    
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
    rm -rf mpv-build
    git clone https://github.com/mpv-player/mpv-build.git
    cd mpv-build
    #echo --enable-libmpv-shared > mpv_options

    # RPi: enable MMAL
    if [[ $(uname -m) = armv* ]]; then
        echo --enable-mmal  > ffmpeg_options
        echo --enable-omx-rpi >> ffmpeg_options
        echo --enable-libv4l2 >> ffmpeg_options

        echo --enable-rpi > mpv_options
        echo --enable-rpi-mmal >> mpv_options
        # echo --disable-vaapi >> mpv_options
    fi

    # Build
    # ./use-mpv-release
    # ./use-ffmpeg-release

    # fixed rebuild
    set -e
    export LC_ALL=C
    # ./update
    # ./clean
    
    #cd mpv 
    #git checkout refs/tags/"v0.28.2"    # 0.30.0 release is broken on RPi / 0.29.1 has random freeze
    #cd ..

    if [[ $(uname -m) = armv* ]]; then
        ./build -j4
    else
        ./build -j8
    fi
    cd ..

    # Copy bin
    mkdir -p ../bin
    cp mpv-build/mpv/build/mpv  ../bin/mpv
    cp mpv-build/mpv/build/mpv  "../bin/mpv-$DISTRO-$ARCHI"


    # Clean
    #rm -fR mpv-build

fi

exit 0
