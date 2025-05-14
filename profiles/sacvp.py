from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform
import json, glob


# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, '/data/hplayer2-sacvp.json')


# PLAYERS
video = hplayer.addPlayer('mpv', 'video')
stream = hplayer.addPlayer('mpvstream', 'stream')

# Not working...
# SAMPLER (play 0_* media from the same directory)
# sampler = hplayer.addSampler('mpv', 'jp', 1)
# lastSamplerMedia = None
# @hplayer.on('video.playing')
# def samplerPlay(ev, *args):
#     global lastSamplerMedia
#     directory = os.path.dirname(args[0])
#     mediaList = hplayer.files.listFiles(directory + '/0_*')
#     media = mediaList[0] if len(mediaList) > 0 else None
#     if lastSamplerMedia != media:
#         if not media: sampler.stop()
#         else: sampler.play(media, oneloop=True, index=0)
#         lastSamplerMedia = media
        

# ATTACHED ESP 
myESP = 0
# try:
#     with open(os.path.join(projectfolder, 'esp.json')) as json_file:
#         data = json.load(json_file)
#         if devicename in data:
#             myESP = data[devicename]
#             hplayer.log('attached to ESP', myESP)
# except: pass

# INTERFACES
hplayer.addInterface('keyboard')
hplayer.addInterface('osc', 1222, 3737)
hplayer.addInterface('serial', 'M5', 10)
hplayer.addInterface('zyre')
hplayer.addInterface('mqtt', '10.0.0.2')
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


# SMS
#
sms_counter = 0
peers_counter_dispatch = 0
for f in glob.glob('/tmp/txt2img*'): os.remove(f)   # clear old msgs

# SMS DISPATCHER (only CASA) MQTT -> ZYRE  
@hplayer.on('mqtt.textdispatch')
def textdispatchM(ev, *args):
    zyre = hplayer.interface('zyre')
    peersList = list(zyre.peersList())
    peersList.remove(zyre.node.zyre.uuid())
    if len(peersList) == 0: return
    
    global peers_counter_dispatch
    peers_counter_dispatch = (peers_counter_dispatch+1)%len(peersList)
    hplayer.interface('zyre').node.whisper(peersList[peers_counter_dispatch], 'text', args)
    

# SMS TEXT ALL (only CASA) MQTT -> ZYRE  
@hplayer.on('mqtt.textall')
def textclearM(ev, *args):
    hplayer.interface('zyre').node.broadcast('textall', args)
    
    
# SMS STOP ALL (only CASA) MQTT -> ZYRE  
@hplayer.on('mqtt.textstop')
def textclearM(ev, *args):
    hplayer.interface('zyre').node.broadcast('textstop')
    
    
# SMS DISPLAY
@hplayer.on('zyre.text')
def text(ev, *args):
    global sms_counter

    args = list(args[0])
    if len(args) == 1: args.append(None)            #encoding
    if len(args) == 2: args.append(sms_counter)     #suffix
    
    print(args)
    file = hplayer.imgen.txt2img(*args)
    
    hplayer.settings.set('loop', 2)
    hplayer.playlist.load(glob.glob('/tmp/txt2img*'))
    
    i = hplayer.playlist.findIndex(file)
    if i > -1: hplayer.playlist.remove(i)
    hplayer.playlist.randomize()
    hplayer.playlist.add(file)
    hplayer.playlist.last()
    
    sms_counter = (sms_counter+1)%10


@hplayer.on('zyre.textstop')
def textstop(ev, *args):
    hplayer.interface(ev.split('.')[0]).emit('stop')
    global sms_counter
    sms_counter = 0
    os.system('rm -Rf /tmp/txt2img*')
        
  
@hplayer.on('zyre.textall')
def textclear(ev, *args):
    textstop(ev)
    msg = args[0]
    if len(msg) >= 1 and len(msg[0]) >= 1:
        msg[0] = msg[0].replace("+33", "0")
        if msg[0].startswith("0") and len(msg[0]) == 10:
            msg[0] = ' '.join(msg[0][i:i+2] for i in range(0, len(msg[0]), 2))
        text(None, msg)
        

# PIR
#
@hplayer.on('*.pir')
def pir(ev, *args):
    if len(args) > 0:
        if args[0] == 'ON':
             if not video.isPlaying():
                hplayer.playlist.playindex(0)
             hplayer.settings.set('loop', 2)
        elif args[0] == 'OFF':
             if video.isPlaying():
                hplayer.settings.set('loop', 0)


# Keyboard
#
dotHold = False

@hplayer.on('keyboard.*')
def keyboard(ev, *args):
    global dotHold
    
    base, key = ev.split("keyboard.KEY_")
    if not key: return
    
    key, mode = key.split("-")
    if key.startswith('KP'): key = key[2:]
    
    # 0 -> 9
    if key.isdigit() and mode == 'down':
        numk = int(key)
        if dotHold:
            # select folder (locally only)
            hplayer.files.selectDir(numk)
                
        else:
            # play sequence regie
            hplayer.interface('regie').playseq(hplayer.files.currentIndex(), numk-1)
            
        
    elif key == 'ENTER' and mode == 'down':
        broadcast('stop')
    
    elif key == 'DOT':
        dotHold = (mode != 'up')
        
    elif key == 'NUMLOCK' and mode == 'down': pass
    elif key == 'SLASH' and mode == 'down': pass
    elif key == 'ASTERISK' and mode == 'down': pass
    elif key == 'BACKSPACE' and mode == 'down': pass
    
    # volume
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
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 1)
   

# file = hplayer.imgen.txt2img("004F006B00200073007500700065007200202764FE0F", "UCS2")
# hplayer.playlist.play(file)
            
# RUN
hplayer.run()                               						# TODO: non blocking
