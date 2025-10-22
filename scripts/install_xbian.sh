#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"

# Silent sudo
if sudo -n true 2>/dev/null; then
    echo "Sudo credentials cached."
else
    echo "Sudo credentials required."
    sudo -v
fi

# Parse if -y flag is given
while getopts "y" opt; do
    case $opt in
        y)
            AUTO_YES=true
            ;;
        *)
            ;;
    esac
done

# Add -y to apt commands if AUTO_YES is true
if [ "$AUTO_YES" = true ]; then
    APT_YES_FLAG="-y"
else
    APT_YES_FLAG=""
fi


# Exit on error
set -e

## check xBIAN (DEBIAN / RASPBIAN / UBUNTU)
if [[ $(command -v apt) ]]; then
    echo "xBIAN detected."
else
    echo "This script is intended for xBIAN systems (DEBIAN / RASPBIAN / UBUNTU)."
    echo "Aborting."
    exit 1
fi

# MPV
sudo apt install mpv $APT_YES_FLAG

# GStreamer
# apt install libdrm libmpg123 gstreamer1.0-plugins-ugly libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-pulseaudio gstreamer1.0-x gstreamer1.0-plugins-bad gstreamer1.0-alsa gstreamer1.0-plugins-base gstreamer1.0-plugins-good -y

# hplayer2 dependencies
sudo apt install python3 rsync libdrm-dev libgbm-dev libgles-dev libegl-dev libegl1-mesa-dev libgles2-mesa-dev $APT_YES_FLAG
sudo apt install libffi-dev libjack-dev libjpeg-dev libtool autotools-dev automake libopenblas0 cython3 python3-opencv $APT_YES_FLAG
sudo apt install libzmq3-dev $APT_YES_FLAG

# UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# RPi 
if [[ $(uname -m) = armv* || $(uname -m) = aarch64 ]]; then
    apt-get install i2c-tools $APT_YES_FLAG
fi

# Build and install czmq and zyre from source
python3 scripts/bootstrap_native_deps.py

# Set PKG_CONFIG_PATH for local installs
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

# UV dep install
cd "$(dirname "$(readlink -f "$0")")/.."
uv sync --extra dev
sed -i 's/^include-system-site-packages = .*/include-system-site-packages = true/' .venv/pyvenv.cfg

# Install shell completion
echo ""
echo "Installing shell completion..."
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect current shell
CURRENT_SHELL="$(basename "$SHELL")"

if [ "$CURRENT_SHELL" = "zsh" ]; then
    ZSHRC="$HOME/.zshrc"
    if [ ! -f "$ZSHRC" ]; then
        touch "$ZSHRC"
    fi
    
    if grep -q "hplayer2.*completion" "$ZSHRC" 2>/dev/null; then
        echo "Completion already configured in $ZSHRC"
    else
        echo "" >> "$ZSHRC"
        echo "# HPlayer2 completion" >> "$ZSHRC"
        echo "fpath=($SCRIPT_DIR \$fpath)" >> "$ZSHRC"
        echo "autoload -Uz compinit && compinit" >> "$ZSHRC"
        echo "Completion added to $ZSHRC"
        echo "Run 'source ~/.zshrc' or open a new terminal to enable tab completion"
    fi
elif [ "$CURRENT_SHELL" = "bash" ]; then
    SHELL_CONFIG="${HOME}/.bashrc"
    if [ ! -f "$SHELL_CONFIG" ]; then
        SHELL_CONFIG="${HOME}/.bash_profile"
    fi
    
    if grep -q "hplayer2-completion.bash" "$SHELL_CONFIG" 2>/dev/null; then
        echo "Completion already configured in $SHELL_CONFIG"
    else
        echo "" >> "$SHELL_CONFIG"
        echo "# HPlayer2 bash completion" >> "$SHELL_CONFIG"
        echo "[ -f \"$SCRIPT_DIR/hplayer2-completion.bash\" ] && source \"$SCRIPT_DIR/hplayer2-completion.bash\"" >> "$SHELL_CONFIG"
        echo "Completion added to $SHELL_CONFIG"
        echo "Run 'source $SHELL_CONFIG' or open a new terminal to enable tab completion"
    fi
fi

exit 0
