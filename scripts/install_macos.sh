#!/bin/sh
cd "$(dirname "$0")"/..

# Check for Homebrew
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is not installed. Please install Homebrew first: https://brew.sh"
    exit 1
fi

# Exit on error
set -e

# Homebrew packages
brew install uv libtool automake autoconf pkg-config zeromq mpv 

# Build and install czmq and zyre from source
#python3 scripts/bootstrap_native_deps.py
uv run python scripts/bootstrap_native_deps.py

# Set PKG_CONFIG_PATH for local installs
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

# UV dependencies
uv sync --extra dev

# Run tests to verify installation
# uv run ruff check
uv run pytest

# Install shell completion
echo ""
echo "Installing shell completion..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
    SHELL_CONFIG="${HOME}/.bash_profile"
    if [ ! -f "$SHELL_CONFIG" ]; then
        SHELL_CONFIG="${HOME}/.bashrc"
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


