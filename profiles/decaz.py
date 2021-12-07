from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json


# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, '/data/hplayer2-decaz.conf')


# PLAYERS
video = hplayer.addPlayer('mpv', 'video')

# INTERFACES
# hplayer.addInterface('keyboard')
hplayer.addInterface('osc', 1222, 3737)
# hplayer.addInterface('zyre')
hplayer.addInterface('http2', 8080)
hplayer.addInterface('regie', 9111, projectfolder)

# Overlay
if hplayer.isRPi():
    video.addOverlay('rpifade')


# print all events
# @hplayer.on('*.*')
# def all(ev, *args):
#     print('ALL EVENTS', ev, args)

@hplayer.on('osc.hello')
def hello(ev, *args):
    print('YEAH!', args)
    
    
# RUN
hplayer.run()                               						# TODO: non blocking
