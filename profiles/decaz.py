from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json
import time

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
osc =   hplayer.addInterface('osc', 1222, 3737)
gpio =  hplayer.addInterface('gpio', [15], 300, 'PUP')
zyre =  hplayer.addInterface('zyre')
http2 = hplayer.addInterface('http2', 8080)
regie = hplayer.addInterface('regie', 9111, projectfolder)

# Overlay
if hplayer.isRPi():
    video.addOverlay('rpifade')


# print all events
# @hplayer.on('*.*')
# def all(ev, *args):
#     print('ALL EVENTS', ev, args)


# LED init
gpio.set(14, False)

# VIDEO stopped
@hplayer.on('video.stopped')
def hello(ev, *args):
    gpio.set(14, False)



# VIDEO playing start LED
wait = 3

@hplayer.on('video.playing')
def hello(ev, *args):
    time.sleep(wait)
    gpio.set(14, True)


# VIDEO play
@hplayer.on('gpio.15-on')
def hello(ev, *args):
    gpio.emit('play', 'small.mp4')
    
@hplayer.on('osc.hello')
def hello(ev, *args):
    global wait
    wait = int(args[0])
    osc.emit('play', 'small.mp4')
    print(args[0])
    
# BTN pin 16
@hplayer.on('gpio.18')
def hello(ev, *args):
    gpio.set(14, args[0])


# OSC /hello
@hplayer.on('osc.hello')
def hello(ev, *args):
    gpio.set(14, False)
 

 # OSC /goodbye
@hplayer.on('osc.goodbye')
def hello(ev, *args):
    gpio.set(14, False)   

    
# RUN
hplayer.run()                               						# TODO: non blocking
