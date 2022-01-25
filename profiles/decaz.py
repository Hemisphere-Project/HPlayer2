from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json
import time
from threading import Timer

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
gpio        = hplayer.addInterface('gpio', [], 300, 'PUP')
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
        



#LED osc on/off
@hplayer.on('osc.on')
def hello(ev, *args):
    gpio.set(2, False)

@hplayer.on('osc.off')
def hello(ev, *args):
    gpio.set(2, True)


timer1 = None
timer2 = None   

def triggerGPIO(pin1, state, pin2=None):
    print('Timer trigger', pin1, state)
    hplayer.emit('do-gpio', pin1, not state)
    if pin2:
        hplayer.emit('do-gpio', pin2, state)

@hplayer.on('do-gpio')
def dogpio(ev, *args):
    print('Gpio set', args)
    gpio.set(args[0], args[1])
    

# VIDEO playing gpio control on/off (besoin append au noms fichier lu "_durée-en-sec_on/off_playing/end_durée-en-sec")
@hplayer.on('video.playing')
@hplayer.on('video.end')
def trig(ev, *args):
    
    a=args[-1]
    b=a.split('/')[-1].split('_')[-5:-1]
    print('YOUU', b)
    if len(b) < 2: return
    
    if b[-2] == ev.split('.')[-1]:
        
        global timer1, timer2
        if timer1: 
            timer1.cancel()
        timer1 = Timer(float(b[-4]), triggerGPIO, ([2], b[-3]=='on', [4]) )
        timer1.start()
        
        if timer2: 
            timer2.cancel()
        timer2 = Timer(float(b[-4])+float(b[-1]), triggerGPIO, ([2], b[-3]!='on', [4]) )
        timer2.start()                
                
                
# VIDEO stopped gpio control

# VIDEO stopped
'''{@hplayer.on('video.stopped')
def hello(ev, *args):
    gpio.set(2, False)'''

# VIDEO play
@hplayer.on('gpio.15-on')
def hello(ev, *args):
    gpio.emit('play', 'small.mp4')
    
@hplayer.on('osc.hello')
def hello(ev, *args):
    osc.emit('play', 'youhou.wav')
    

@hplayer.on('osc.decazeville')
def hello(ev, *args):
    osc.emit('play', 'D_MEDIA 1_EPISODE_2.mp4')
 
    
# BTN pin 16
@hplayer.on('gpio.18')
def hello(ev, *args):
    gpio.set(2, args[0])


"""# OSC /hello
@hplayer.on('osc.hello')
def hello(ev, *args):
    gpio.set(14, False)"""

#volume control
@hplayer.on('osc.vol')
def volum(ev, *args):
    print(ev, args)
    v=args[0]
    print(v)
    hplayer.settings.set('volume', v)

 # OSC /goodbye
@hplayer.on('osc.goodbye')
def hello(ev, *args):
    gpio.set(14, False)   



    
# RUN
hplayer.run()                               						# TODO: non blocking
