# Get MPV Build tools
cd "$(dirname "$(readlink -f "$0")")"

# libass / ffmpeg / mpv dependencies
pacman -S freetype2 fribidi fontconfig yasm git autoconf pkg-config libtool --noconfirm --needed
pacman -S lua luajit libvdpau libva libxv libjpeg libxkbcommon libxrandr libv4l libxss libcaca sdl2 --noconfirm --needed
pacman -S base-devel libx264 mesa fbida libbluray --noconfirm --needed
pacman -S alsa-lib alsa-firmware ttf-roboto --noconfirm --needed


rm -rf mpv-build
git clone https://github.com/mpv-player/mpv-build.git
cd mpv-build

set -e
export LC_ALL=C

sed -i 's/do_clone "ffmpeg"/#do_clone "ffmpeg"/g' update
sed -i 's/checkout ffmpeg/#checkout ffmpeg/g' update
sed -i 's/scripts\/ffmpeg-config/#scripts\/ffmpeg-config/g' build
sed -i 's/scripts\/ffmpeg-build/#scripts\/ffmpeg-build/g' build

./rebuild -j4




########## https://community.mnt.re/t/notes-on-building-ffmpeg-and-mpv-to-use-the-hardware-h-264-decoder/305
##########
git clone https://github.com/martinetd/FFmpeg
cd FFmpeg
git checkout v4l2-request
./configure --prefix=/usr --enable-v4l2-request --enable-libdrm --enable-libudev --enable-shared --enable-hwaccel=h264_v4l2request


###########
git clone https://github.com/Kwiboo/FFmpeg
cd FFmpeg
git checkout v4l2-request-hwaccel-4.3-rpi 
./configure --prefix=/usr --enable-v4l2-request --enable-libdrm --enable-libudev --enable-shared --enable-hwaccel=h264_v4l2request



###############
https://github.com/spookyfirehorse/ffmpeg-and-mpv-for-rpi4