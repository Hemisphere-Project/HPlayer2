from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder]


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
hplayer.addInterface('regie', 9111, projectfolder)

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
