from core.engine.hplayer import HPlayer2
from core.engine.playlist import Playlist
from core.engine import network

import os
import json, glob


# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# ATTACHED ESP 
myESP = 0
# try:
#     with open(os.path.join(projectfolder, 'esp.json')) as json_file:
#         data = json.load(json_file)
#         if devicename in data:
#             myESP = data[devicename]
#             hplayer.log('attached to ESP', myESP)
# except: pass

# ATTACHED ETENDARD: get ETENDARD from etendard.json
myETEND = None
try:
    with open(os.path.join(projectfolder, 'etendard.json')) as json_file:
        data = json.load(json_file)
        if devicename in data:
            myETEND = data[devicename]
            hplayer.log('attached to ETENDARD', myETEND)
except: pass

# ATTACHED GROUP: get GROUP from group.json
myGROUP = []
try:
    with open(os.path.join(projectfolder, 'group.json')) as json_file:
        data = json.load(json_file)
        for k in data:
            if devicename in data[k]:
                myGROUP = data[k]
                hplayer.log('attached to GROUP', myGROUP)
except: pass

# PLAYLIST Sampler
playlistSampler = None


# PLAYERS
# ETENDARD
if myETEND:
    video = hplayer.addPlayer('videonet', 'video')
    video.setSize(*myETEND['size'], myETEND['snake'], myETEND['vflip'], myETEND['hflip'])
    video.setIP(myETEND['ip'])
    hplayer.log('mode VIDEO4ARTNET')
    # Ethernet Zyre
    hplayer.addInterface('zyre', 'wint')

# HDMI
else:
    video = hplayer.addPlayer('mpv', 'video')
    video.imagetime(0)
    stream = hplayer.addPlayer('mpvstream', 'stream')
    hplayer.log('mode HDMI')

    # Any Zyre
    hplayer.addInterface('zyre')
    
    # Sampler (play 0_* media from the same directory)
    # sampler = hplayer.addSampler('jp', 'audio', 1)
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
            
    # @hplayer.on('*.stop')
    # def samplerStop(ev, *args):
    #     global lastSamplerMedia
    #     if lastSamplerMedia:
    #         sampler.stop()
    #         lastSamplerMedia = None
    
    
    # Sampler Pad
    sampler = hplayer.addSampler('jp', 'audio', 2)
    
    # Playlist Sampler 1 from ZZ_AUDIO1 => loops
    playlistSampler1 = Playlist(hplayer, 'Playlist-sampler')
    filelist= hplayer.files.listFiles('ZZ_AUDIOLOOP/*')
    filelist = [f for f in filelist if sampler.playerAt(0).validExt(f)] 
    print()
    print(filelist)
    print()
    playlistSampler1.load(filelist)
    
    # Playlist Sampler 2 from ZZ_AUDIO2 => one shot
    playlistSampler2 = Playlist(hplayer, 'Playlist-sampler')
    filelist= hplayer.files.listFiles('ZZ_AUDIOSHOT/*')
    filelist = [f for f in filelist if sampler.playerAt(1).validExt(f)]
    print()
    print(filelist)
    print()
    playlistSampler2.load(filelist)
    

# INTERFACES
hplayer.addInterface('midictrl', 'LPD8', 10)
# hplayer.addInterface('keyboard')
hplayer.addInterface('osc', 1222, 9000, '127.0.0.1')
hplayer.addInterface('mqtt', '10.0.0.2')
hplayer.addInterface('http2', 8080)
hplayer.addInterface('teleco')
# hplayer.addInterface('serial', '^M5', 10)
hplayer.addInterface('regie', 9111, projectfolder)
# gpio = hplayer.addInterface('gpio', [16, 20, 21], 1, 0, 'PUP') # service tek debounce @ 1 ??
if myESP:
    hplayer.addInterface('btserial', 'k32-'+str(myESP))

# Overlay
# if hplayer.isRPi():
#     video.addOverlay('rpifade')

#
# SYNC PLAY
#

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	delay = 500 if path.startswith('play') else 0
	if path.startswith('play'):
		hplayer.interface('zyre').node.broadcast(path, list(args), delay)   ## WARNING LATENCY !!
  
# Cast to group on OSC/Zyre
def groupcast(path, *args):
    delay = 500 if path.startswith('play') else 0
    if len(myGROUP) > 0:
        for group in myGROUP:
            hplayer.interface('zyre').node.shout(group, path, list(args), delay)   ## WARNING LATENCY !!
    else:
        hplayer.interface('zyre').node.tomyself(path, list(args))

#
# MIDI CTRL
#
volumeLoop = 100
volumeShot = 100

@hplayer.on('midictrl.noteon')
@hplayer.on('midictrl.cc')
@hplayer.on('midictrl.pc')
def midiEvent(ev, *args):
    if not playlistSampler1: return
    if not playlistSampler2: return
    global volumeLoop, volumeShot
    track = None
    light = None
    
    if ev == 'midictrl.noteon':
        value = args[0]['note']    
        if value == 40: 
            light = 1
            track = playlistSampler1.trackAtIndex(0)
        elif value == 41: 
            light = 2
            track = playlistSampler1.trackAtIndex(1)
        elif value == 42: 
            light = 3
            track = playlistSampler1.trackAtIndex(2)
        elif value == 43: 
            light = 4
            track = playlistSampler1.trackAtIndex(3)
        elif value == 36: 
            light = 5
            track = playlistSampler1.trackAtIndex(4)
        elif value == 37: 
            light = 6
            track = playlistSampler1.trackAtIndex(5)
        elif value == 38: 
            light = 7
            track = playlistSampler1.trackAtIndex(6)
        elif value == 39: 
            track = 'stop'
            light = 'stop'
            
        if track == 'stop': 
            sampler.stop()
        elif track: 
            sampler.play(track, oneloop=True, index=0)
        
        if light == 'stop': hplayer.interface('osc').send('/hartnet/stop')
        elif light: hplayer.interface('osc').send('/hartnet/play', light)
    
    if ev == 'midictrl.cc':
        value = args[0]['control']
        
        if value == 16:   track = playlistSampler2.trackAtIndex(0)
        elif value == 17: track = playlistSampler2.trackAtIndex(1)
        elif value == 18: track = playlistSampler2.trackAtIndex(2)
        elif value == 19: track = playlistSampler2.trackAtIndex(3)
        elif value == 12: track = playlistSampler2.trackAtIndex(4)
        elif value == 13: track = playlistSampler2.trackAtIndex(5)
        elif value == 14: track = playlistSampler2.trackAtIndex(6)
        elif value == 15: track = 'stop'
        
        # volumes
        elif value == 70:  
            hplayer.emit('volume', args[0]['value']*100/127)           # video volume
        elif value == 73:  
            volumeLoop = args[0]['value']*100/127
            sampler.playerAt(0)._applyVolume(volumeLoop)    # sampler0 volume
        elif value == 77:  
            volumeShot = args[0]['value']*100/127
            sampler.playerAt(1)._applyVolume(volumeShot)    # sampler1 volume
        
        # play sampler shot
        if track == 'stop': 
            sampler.stop()
        elif track: 
            sampler.play(track, oneloop=False, index=1)
    
    if ev == 'midictrl.pc':
        value = args[0]['program']
        if value == 4:   light = 1
        elif value == 5: light = 2
        elif value == 6: light = 3
        elif value == 7: light = 4
        elif value == 0: light = 5
        elif value == 1: light = 6
        elif value == 2: light = 7
        elif value == 3: light = 'stop'
        
        if light == 'stop': hplayer.interface('osc').send('/hartnet/stop')
        elif light: hplayer.interface('osc').send('/hartnet/play', light)


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

keyboardMode = 'solo' # 'regie' / 'solo' / 'all'

# KEYBOARD: MODE PILOTAGE REGIE
#
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

            # load folder into playlist
            if keyboardMode == 'solo':
                hplayer.playlist.load( hplayer.files.currentDir() ) 
            elif keyboardMode == 'all':
                broadcast('load', hplayer.files.currentDir())
                
        else:
            # play sequence regie
            if keyboardMode == 'regie':
                hplayer.interface('regie').playseq(hplayer.files.currentIndex(), numk-1)

            # playlist index all
            elif keyboardMode == 'all':
                broadcast('playindex', numk)

            # playlist index solo
            elif keyboardMode == 'solo':
                hplayer.playlist.playindex(numk)
            
        
    elif key == 'ENTER' and mode == 'down':
        hplayer.emit('stop') if keyboardMode == 'solo' else broadcast('stop')
    
    elif key == 'DOT':
        dotHold = (mode != 'up')
        
    elif key == 'NUMLOCK' and mode == 'down': pass
    elif key == 'SLASH' and mode == 'down': pass
    elif key == 'ASTERISK' and mode == 'down': pass
    elif key == 'BACKSPACE' and mode == 'down': pass
    
    # volume
    elif key == 'PLUS' and (mode == 'down' or mode == 'hold'):
        v = hplayer.settings.get('volume')+1
        hplayer.emit('volume', v) if keyboardMode == 'solo' else broadcast('volume', v)
    elif key == 'MINUS' and (mode == 'down' or mode == 'hold'):
        v = hplayer.settings.get('volume')-1
        hplayer.emit('volume', v) if keyboardMode == 'solo' else broadcast('volume', v)


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
    if myESP:
        if len(args) == 0: return
        last = args[0].split('.')[0].split('_')[-1]
        if len(last) == 0: return
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
    if myESP:
        global lastEspEvent
        if lastEspEvent == 'sacvp.esp':
            hplayer.emit('sacvp.esp', {'topic': 'leds/stop', 'data': ''})

#
# GPIO
#

# BTN 1
playlist1 = Playlist(hplayer, 'Playlist-btn1')
playlist1.load("1_*.*")
@hplayer.on('gpio.16')
def play1(ev, *args):
    isAlreadyPlaying = hplayer.activePlayer().status()['media'] and hplayer.activePlayer().status()['media'].split('/')[-1].startswith("1_")
    print("BTN1:", args[0] == 0, "isPlaying", isAlreadyPlaying )
    if args[0] == 0:
        if not isAlreadyPlaying:
            hplayer.playlist.clear()
            playlist1.next()
    elif isAlreadyPlaying:
        hplayer.activePlayer().stop()
  
# BTN 2
playlist2 = Playlist(hplayer, 'Playlist-btn2')
playlist2.load("2_*.*")
@hplayer.on('gpio.20')
def play2(ev, *args):
    isAlreadyPlaying = hplayer.activePlayer().status()['media'] and hplayer.activePlayer().status()['media'].split('/')[-1].startswith("2_")
    print("BTN2:", args[0] == 0, "isPlaying", isAlreadyPlaying )
    if args[0] == 0:
        if not isAlreadyPlaying:
            hplayer.playlist.clear()
            playlist2.next()
    elif isAlreadyPlaying:
        hplayer.activePlayer().stop()
    
    
# BTN 3
playlist3 = Playlist(hplayer, 'Playlist-btn3')
playlist3.load("3_*.*")
@hplayer.on('gpio.21')
def play1(ev, *args):
    isAlreadyPlaying = hplayer.activePlayer().status()['media'] and hplayer.activePlayer().status()['media'].split('/')[-1].startswith("3_")
    print("BTN3:", args[0] == 0, "isPlaying", isAlreadyPlaying )
    if args[0] == 0:
        if not isAlreadyPlaying:
            hplayer.playlist.clear()
            playlist3.next()
    elif isAlreadyPlaying:
        hplayer.activePlayer().stop()


#
# RUN
#

# default volume
@hplayer.on('app-run')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', 1)


# file = hplayer.imgen.txt2img("004F006B00200073007500700065007200202764FE0F", "UCS2")
# hplayer.playlist.play(file)
            
# RUN
hplayer.run()                               						# TODO: non blocking
