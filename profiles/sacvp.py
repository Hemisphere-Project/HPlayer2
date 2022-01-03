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
hplayer = HPlayer2(base_path)


# PLAYERS
video = hplayer.addPlayer('mpv', 'video')
# audio = hplayer.addPlayer('mpv', 'audio')

# ATTACHED ESP 
myESP = 0
try:
    with open(os.path.join(projectfolder, 'esp.json')) as json_file:
        data = json.load(json_file)
        if devicename in data:
            myESP = data[devicename]
            hplayer.log('attached to ESP', myESP)
except: pass

# INTERFACES
hplayer.addInterface('keyboard')
hplayer.addInterface('osc', 1222, 3737)
hplayer.addInterface('zyre')
# hplayer.addInterface('mqtt', '10.0.0.1')
hplayer.addInterface('http2', 8080)
hplayer.addInterface('teleco')
hplayer.addInterface('regie', 9111, projectfolder)
if myESP:
    hplayer.addInterface('btserial', 'k32-'+str(myESP))


# Overlay
if hplayer.isRPi():
    video.addOverlay('rpifade')



#
# SYNC PLAY
#

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	# print(path, list(args))
	if path.startswith('play'):
		hplayer.interface('zyre').node.broadcast(path, list(args), 500)   ## WARNING LATENCY !!
	else:
		hplayer.interface('zyre').node.broadcast(path, list(args))


# Keyboard
#
dotHold = False

@hplayer.on('keyboard.*')
def keyboard(ev, *args):
    print('KEY', ev, args)
    global dotHold
    
    base, key = ev.split("keyboard.KEY_")
    if not key: return
    
    key, mode = key.split("-")
    if key.startswith('KP'): key = key[2:]
    
    if key.isdigit() and mode == 'down':
        numk = int(key)
        if dotHold:
            # select folder
            try:
                broadcast('load', hplayer.files.listDir()[numk])
                print("LOAD DIR", hplayer.files.listDir()[numk])
            except:
                print("LOAD DIR: error index not found", numk)
                
        else:
            # play media
            broadcast('playindex', numk)
            print("PLAY INDEX", numk)
        
    elif key == 'ENTER' and mode == 'down':
        broadcast('stop')
    
    elif key == 'DOT':
        dotHold = (mode != 'up')
        
    elif key == 'NUMLOCK' and mode == 'down': pass
    elif key == 'SLASH' and mode == 'down': pass
    elif key == 'ASTERISK' and mode == 'down': pass
    elif key == 'BACKSPACE' and mode == 'down': pass
    
    elif key == 'PLUS' and (mode == 'down' or mode == 'hold'):
        broadcast('volume', hplayer.settings.get('volume')+1)
        
    elif key == 'MINUS' and (mode == 'down' or mode == 'hold'):
        broadcast('volume', hplayer.settings.get('volume')-1)	






#
# LIGHTS ESP32
#

# ESP -> MQTT / BT
lastEspEvent = 'sacvp.esp'  # save last event
@hplayer.on('*.esp')
def espRelay(ev, *args):
    if myESP:
        global lastEspEvent
        lastEspEvent = ev
        hplayer.interface('mqtt').send('k32/e'+str(myESP)+'/'+args[0]['topic'], args[0]['data'])
        hplayer.interface('btserial').send(args[0]['topic'], args[0]['data'])


# File name -> Trigger ESP
@hplayer.on('*.playing')
def espPlay(ev, *args):
    last = args[0].split('.')[0].split('_')[-1]
    if last[0] == 'L' and len(last) > 1:
        mem = last[1:]
        if mem == 'x':             # STOP leds
            hplayer.emit('sacvp.esp', {'topic': 'leds/stop', 'data': ''})
        elif mem.isnumeric():      # MEM leds
            hplayer.emit('sacvp.esp', {'topic': 'leds/mem', 'data': mem})


# Stop -> Blackout ESP
@hplayer.on('*.stopped')
@hplayer.on('*.paused')
def espStop(ev, *args):
    global lastEspEvent
    if lastEspEvent == 'sacvp.esp':
        hplayer.emit('sacvp.esp', {'topic': 'leds/stop', 'data': ''})


# default volume
@video.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 50)
    hplayer.settings.set('loop', -1)

# RUN
hplayer.run()                               						# TODO: non blocking
