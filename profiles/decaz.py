from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json
import time

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

base_path = ['/data/usb', projectfolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, '/data/hplayer2-decaz.conf')


# PLAYERS
video = hplayer.addPlayer('mpv', 'video')

# INTERFACES
keyboard    = hplayer.addInterface('keyboard')
osc         = hplayer.addInterface('osc', 1222, 3737)
gpio        = hplayer.addInterface('gpio', [15], 300, 'PUP')
zyre        = hplayer.addInterface('zyre')
#mqtt        = hplayer.addInterface('mqtt', '10.0.0.1')
http2       = hplayer.addInterface('http2', 8080)
teleco      = hplayer.addInterface('teleco')
regie       = hplayer.addInterface('regie', 9111, projectfolder)

# Overlay
if hplayer.isRPi():
    video.addOverlay('rpifade')


# print all events
# @hplayer.on('*.*')
# def all(ev, *args):
#     print('ALL EVENTS', ev, args)


#
# SYNC PLAY
#


# Keyboard
#
dotHold = False

@hplayer.on('keyboard.*')
def keyboard(ev, *args):
    global dotHold
    
    base, key = ev.split("keyboard.KEY_")
    if not key: return
    
    key, mode = key.split("-")
    if key.startswith('KP'): 
        key = key[2:]
    
    # 0 -> 9
    if key.isdigit() and mode == 'down':
        numk = int(key)
        if dotHold:
            # select folder (locally only)
            hplayer.files.selectDir(numk)
                
        else:
            # play sequence regie 
            regie.playseq(hplayer.files.currentIndex(), numk-1)
            
    # ENTER    
    elif key == 'ENTER' and mode == 'down':
        zyre.node.broadcast('stop')
    
    # DOT
    elif key == 'DOT':
        dotHold = (mode != 'up')
        
    elif key == 'NUMLOCK' and mode == 'down': pass
    elif key == 'SLASH' and mode == 'down': pass
    elif key == 'ASTERISK' and mode == 'down': pass
    elif key == 'BACKSPACE' and mode == 'down': pass
    
    # volume
    elif key == 'PLUS' and (mode == 'down' or mode == 'hold'):
        zyre.node.broadcast('volume', [hplayer.settings.get('volume')+1])
    elif key == 'MINUS' and (mode == 'down' or mode == 'hold'):
        zyre.node.broadcast('volume', [hplayer.settings.get('volume')-1])	
        


# LED init
gpio.set(14, False)

# VIDEO stopped
@hplayer.on('*.stopped')
def hello(ev, *args):
    gpio.set(14, False)



# VIDEO playing start LED
wait = 3

@hplayer.on('*.playing')
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
