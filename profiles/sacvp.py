from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/sync/'+profilename, '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(base_path)

# PLAYERS
video = hplayer.addPlayer('mpv', 'video')
# audio = hplayer.addPlayer('mpv', 'audio')

# Interfaces
# hplayer.addInterface('pyre')
# hplayer.addInterface('keyboard')
# hplayer.addInterface('osc', 1222, 3737)

hplayer.addInterface('zyre')
hplayer.addInterface('http2', 8080)
hplayer.addInterface('teleco')
hplayer.addInterface('regie', 9111)

# Overlay
if hplayer.isRPi():
    video.addOverlay('rpifade')

# default volume
@video.on('player-ready')
def init(ev):
    hplayer.settings.set('volume', 50)
    hplayer.settings.set('loop', -1)

# RUN
hplayer.run()                               						# TODO: non blocking
