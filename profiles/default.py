from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json


# INIT HPLAYER
hplayer = HPlayer2(
        basepath=['/data/usb', '/data/media'], 
        settingspath="/data/hplayer2.cfg")

# PLAYERS
player = hplayer.addPlayer('mpv', 'player')

# INTERFACES
# hplayer.addInterface('keyboard')
hplayer.addInterface('osc', 4000, 4001)
hplayer.addInterface('http2', 8080)

# RUN
hplayer.run()                               						# TODO: non blocking

