#!/bin/bash
pacman -Sy git --noconfirm
git clone https://github.com/Hemisphere-Project/HPlayer2.git
cd HPlayer2
./scripts/install_dependencies.sh
./scripts/install_mpv.sh
