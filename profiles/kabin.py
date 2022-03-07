from core.engine.hplayer import HPlayer2
from core.engine import network


import os, sys, types, platform
import json


# INIT HPLAYER
hplayer = HPlayer2('/media/usb/test')

# PLAYERS
video = hplayer.addPlayer('gst', 'video')


# INTERFACES
ticker      = hplayer.addInterface('ticker', 137, 'tick')
# keyboard    = hplayer.addInterface('keyboard')
# osc         = hplayer.addInterface('osc', 1222, 3737)
# mqtt        = hplayer.addInterface('mqtt', '10.0.0.1')
http2       = hplayer.addInterface('http2', 8080, {'page': 'mini'})
# teleco      = hplayer.addInterface('teleco')

# Overlay
# if hplayer.isRPi():
#     video.addOverlay('rpifade')



# default volume
@video.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', -1)
    hplayer.playlist.load('/media/usb/test')
    hplayer.playlist.play(0)
    
    
# Add new uploads to playlist    
@http2.on('file-uploaded')
def upload(ev, *args):
    hplayer.playlist.add(args[0])


# Ticker next
@ticker.on('tick')
def tick(ev, *args):
    if args[0]%8 == 0:
        hplayer.playlist.random()


# RUN
hplayer.run()                               						# TODO: non blocking
