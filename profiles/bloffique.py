from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/sync/', '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')

# Interfaces
hplayer.addInterface('zyre', "wlan0")
hplayer.addInterface('http2', 8080)
hplayer.addInterface('keyboard')

if HPlayer2.isRPi():
	hplayer.addInterface('keypad')


# Build playlist
#
@hplayer.files.on('file-changed')
def bulid_list(ev=None, *args):
    hplayer.playlist.load("*"+network.get_hostname()+"*")
bulid_list()

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	# print(path, list(args))
	if path.startswith('play'):
		hplayer.interface('zyre').node.broadcast(path, list(args), 200)   ## WARNING LATENCY !!
	else:
		hplayer.interface('zyre').node.broadcast(path, list(args))


# Bind Keypad / GPIO events
#
hplayer.on('keypad.right', 		lambda ev: broadcast('playindex', hplayer.playlist.nextIndex()))
hplayer.on('keypad.up', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keypad.down', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))
hplayer.on('keypad.left', 		lambda ev: broadcast('playindex', hplayer.playlist.prevIndex())) 
hplayer.on('keypad.select', 		lambda ev: broadcast('stop'))

@hplayer.on('zyre.playz')
def play_indexed(ev, *args):
    hplayer.playlist.emit('playindex', hplayer.playlist.findIndex(str(args[0])+"_*") )


# Keyboard
#
hplayer.on('keyboard.KEY_KP0-down', 		lambda ev: broadcast('playz', 0))
hplayer.on('keyboard.KEY_KP1-down', 		lambda ev: broadcast('playz', 1))
hplayer.on('keyboard.KEY_KP2-down', 		lambda ev: broadcast('playz', 2))
hplayer.on('keyboard.KEY_KP3-down', 		lambda ev: broadcast('playz', 3))
hplayer.on('keyboard.KEY_KP4-down', 		lambda ev: broadcast('playz', 4))
hplayer.on('keyboard.KEY_KP5-down', 		lambda ev: broadcast('playz', 5))
hplayer.on('keyboard.KEY_KP6-down', 		lambda ev: broadcast('playz', 6))
hplayer.on('keyboard.KEY_KP7-down', 		lambda ev: broadcast('playz', 7))
hplayer.on('keyboard.KEY_KP8-down', 		lambda ev: broadcast('playz', 8))
hplayer.on('keyboard.KEY_KP9-down', 		lambda ev: broadcast('playz', 9))
hplayer.on('keyboard.KEY_KPENTER-down',     	lambda ev: broadcast('stop'))

hplayer.on('keyboard.KEY_KPPLUS-down', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPPLUS-hold', 		lambda ev: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPMINUS-down', 	lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))	
hplayer.on('keyboard.KEY_KPMINUS-hold', 	lambda ev: broadcast('volume', hplayer.settings.get('volume')-1))	



# PATCH Keypad LCD update
def lcd_update(self):
	lines = ["", ""]

	# Line 1 : SCENE + VOLUME
	lines[0] = hplayer.files.currentDir().ljust(13, ' ')[:13]
	lines[0] += str(hplayer.settings.get('volume')).rjust(3, ' ')[:3]

	# Line 2 : MEDIA
	if not player.status()['media']: lines[1] = '-stop-'
	else: lines[1] = os.path.basename(player.status()['media'])[:-4]
	lines[1] = lines[1].ljust(14, ' ')[:14]
	lines[1] += str(hplayer.interface('zyre').activeCount()).rjust(2, ' ')[:2]

	return lines

if hplayer.isRPi():
	hplayer.interface('keypad').update = types.MethodType(lcd_update, hplayer.interface('keypad'))



# RUN
hplayer.run()                               						# TODO: non blocking
