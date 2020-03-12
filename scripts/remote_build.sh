#!/bin/bash
pacman -Sy git --noconfirm
git clone https://github.com/Hemisphere-Project/HPlayer2.git
cd HPlayer2
./scripts/build_arch.sh
