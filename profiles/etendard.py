from core.engine.hplayer import HPlayer2
from core.engine.playlist import Playlist
from core.engine import network

import os


# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
projectfolder = os.path.join('/data/sync', profilename)

sacvpfolder = '/data/sync/sacvp'

devicename = network.get_hostname()
devicefolder = os.path.join('/data/sync/solo', devicename)

base_path = ['/data/usb', projectfolder, devicefolder, sacvpfolder]


# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
video = hplayer.addPlayer('videonet', 'video')
video.setSize(36, 138)
video.setIP("2.12.0.2")

# LOAD ROOT FOLDER AS PLAYLIST
hplayer.playlist.load( hplayer.files.currentList() )


# INTERFACES
hplayer.addInterface('keyboard')
hplayer.addInterface('zyre', 'wint')
hplayer.addInterface('osc', 1222, 3737)
hplayer.addInterface('mqtt', '10.0.0.1')
hplayer.addInterface('http2', 8080)
hplayer.addInterface('teleco')
hplayer.addInterface('serial', '^M5', 10)
hplayer.addInterface('regie', 9111, projectfolder)
gpio = hplayer.addInterface('gpio', [16, 20, 21], 1, 0, 'PUP') # service tek debounce @ 1 ??

# Overlay
# if hplayer.isRPi():
#     video.addOverlay('rpifade')

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
# RUN
#

# default volume
@video.on('ready')
def init(ev, *args):
    hplayer.settings.set('volume', 100)
    hplayer.settings.set('loop', -1)
            
# RUN
hplayer.run()                               						# TODO: non blocking
