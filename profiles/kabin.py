from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json


# INIT HPLAYER
hplayer = HPlayer2('/data/usb')

# PLAYERS
video = hplayer.addPlayer('mpv', 'video')


# INTERFACES
hplayer.addInterface('http2', 80, {'page': 'mini'})
hplayer.addInterface('teleco')

# Overlay
if hplayer.isRPi():
    video.addOverlay('rpifade')


# default volume
@video.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', -1)

# RUN
hplayer.run()         
