from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json
import time

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/usb', '/data/media']


# INIT HPLAYER
hplayer = HPlayer2(base_path, '/data/hplayer2-insolite.conf')


# PLAYERS
video = hplayer.addPlayer('mpv', 'video')

# INTERFACES
keyboard    = hplayer.addInterface('keyboard')
osc         = hplayer.addInterface('osc', 3333, 4444)
# gpio        = hplayer.addInterface('gpio', [15], 300, 'PUP')
# zyre        = hplayer.addInterface('zyre')
http2       = hplayer.addInterface('http2', 8080)
# regie       = hplayer.addInterface('regie', 9111, projectfolder)

# Overlay
# if hplayer.isRPi():
#     video.addOverlay('rpifade')


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
            # regie.playseq(hplayer.files.currentIndex(), numk-1)
            pass
            
    # ENTER    
    elif key == 'ENTER' and mode == 'down':
        # zyre.node.broadcast('stop')
        pass
    
    # DOT
    elif key == 'DOT':
        dotHold = (mode != 'up')
        
    elif key == 'NUMLOCK' and mode == 'down': pass
    elif key == 'SLASH' and mode == 'down': pass
    elif key == 'ASTERISK' and mode == 'down': pass
    elif key == 'BACKSPACE' and mode == 'down': pass
    
    # volume
    elif key == 'PLUS' and (mode == 'down' or mode == 'hold'):
        # zyre.node.broadcast('volume', [hplayer.settings.get('volume')+1])
        pass
    elif key == 'MINUS' and (mode == 'down' or mode == 'hold'):
        # zyre.node.broadcast('volume', [hplayer.settings.get('volume')-1])
        pass	
        
    
@hplayer.on('osc.pad')
def hello(ev, *args):
    
    scene = 'Scene-'+str(args[0])
    media = ('0' if args[1] < 10 else '')+str(args[1])+'-*'
    
    osc.emit('play', scene+'/'+media  )

    
# RUN
hplayer.run()                               						# TODO: non blocking
