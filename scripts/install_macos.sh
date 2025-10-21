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


