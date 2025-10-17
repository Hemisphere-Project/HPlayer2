#!/bin/sh
cd "$(dirname "$0")"/..

# Homebrew packages
brew install uv libtool automake autoconf pkg-config zeromq

# Build and install czmq and zyre from source
python3 scripts/bootstrap_native_deps.py

# Set PKG_CONFIG_PATH for local installs
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

# UV dependencies
uv sync --extra dev

# Run tests to verify installation
# uv run ruff check
uv run pytest


