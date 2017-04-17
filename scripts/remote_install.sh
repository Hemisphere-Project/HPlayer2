#!/bin/bash
sudo apt install git -y
git clone https://github.com/Hemisphere-Project/HPlayer2.git
cd HPlayer2
sudo ./scripts/build_debian.sh
