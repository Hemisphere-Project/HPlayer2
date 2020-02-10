from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = '/data/sync/'+profilename


# INIT HPLAYER
hplayer = HPlayer2(base_path)

# PLAYERS
video = hplayer.addPlayer('mpv', 'video')
audio = hplayer.addPlayer('mpv', 'audio')

# Interfaces
# hplayer.addInterface('osc', 1222, 3737)
hplayer.addInterface('zyre', 'wlan0')
# hplayer.addInterface('http2', 8080)
# hplayer.addInterface('keyboard')
hplayer.addInterface('teleco')

# Overlay
# if hplayer.isRPi():
#     video.addOverlay('rpifade')


    
# RUN
hplayer.run()                               						# TODO: non blocking
