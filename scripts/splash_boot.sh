#!/bin/bash
cd "$(dirname "$0")"
cp res/splash.png /home/pi/splash.png
sudo cp res/splash.service /etc/systemd/system/
sudo systemctl enable splash.service
