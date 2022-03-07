from core.engine.hplayer import HPlayer2
from core.engine import network


import os, sys, types, platform
import json, random


# INIT HPLAYER
hplayer = HPlayer2('/data/usb')

# PLAYERS
video = hplayer.addPlayer('gst', 'video')


# INTERFACES
ticker      = hplayer.addInterface('ticker', 120, 'tick')
# keyboard    = hplayer.addInterface('keyboard')
# osc         = hplayer.addInterface('osc', 1222, 3737)
# mqtt        = hplayer.addInterface('mqtt', '10.0.0.1')
http2       = hplayer.addInterface('http2', 80, {'page': 'mini'})
# teleco      = hplayer.addInterface('teleco')

# Overlay
# if hplayer.isRPi():
#     video.addOverlay('rpifade')

    
    
# Add new uploads to playlist    
@http2.on('file-uploaded')
def upload(ev, *args):
    hplayer.playlist.add(args[0])



rythm = [2, 4, 4, 8, 8, 12]
nextTick = -1

# Ticker next
@ticker.on('tick')
def tick(ev, *args):
    global nextTick
    if args[0] >= nextTick:
        nextTick += random.choice(rythm)*4
        hplayer.playlist.random()

@video.on('media-end')        
def nextend(ev, *args):
    global nextTick
    nextTick += random.choice(rythm)*4
    hplayer.playlist.random()


# default volume
@video.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', -1)
    hplayer.playlist.load('/data/usb')

# RUN
hplayer.run()                               						# TODO: non blocking
