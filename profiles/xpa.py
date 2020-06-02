from core.engine.hplayer import HPlayer2
from core.engine import network

import os, sys, types, platform

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/sync/'+profilename, '/data/usb']

# INIT HPLAYER
hplayer = HPlayer2(base_path, "/data/hplayer2-"+profilename+".cfg")

# PLAYERS
player 	= hplayer.addPlayer('mpv','mpv')
midi 	= hplayer.addPlayer('midi','midi')

# Interfaces
hplayer.addInterface('zyre', 'wlan0')
hplayer.addInterface('http2', 8080)
# hplayer.addInterface('http', 8037)
hplayer.addInterface('keyboard')

if HPlayer2.isRPi():
	hplayer.addInterface('keypad')
	hplayer.addInterface('gpio', [21], 310)




# MASTER / SLAVE sequencer
iamLeader = False

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	# print(path, list(args))
	if path.startswith('play'):
		hplayer.interface('zyre').node.broadcast(path, list(args), 200)   ## WARNING LATENCY !!
	else:
		hplayer.interface('zyre').node.broadcast(path, list(args))

# Detect if i am zyre Leader
@hplayer.on('zyre.event')
def leadSequencer(*data):
	global iamLeader
	iamLeader = (data[0]['from'] == 'self')

# Receive a sequence command -> do Play !
@hplayer.on('zyre.playdir')
def doPlay(*data):
	# print(data)
	s = data[0]
	hplayer.playlist.play( hplayer.files.selectDir(s)+'/'+HPlayer2.name()+'*' )

# Receive an exit command -> last seq
@hplayer.on('zyre.end')
def doExit():
	hplayer.playlist.play( hplayer.files.selectDir(2)+'/'+HPlayer2.name()+'*' )


# Media end: next dir / or loop (based on directory name)
@hplayer.on('playlist.end')
# @midi.on('stop')
def endSequence():
	if not iamLeader:  
		return
	if 'loop' in hplayer.files.currentDir():
		broadcast('playdir', hplayer.files.currentIndex())
	elif hplayer.files.currentIndex() == 2:
		broadcast('playdir', 0)
	else:
		broadcast('playdir', hplayer.files.nextIndex())


# Bind Keypad / GPIO events
#
hplayer.on('keypad.left', 		lambda: broadcast('playdir', 0))
hplayer.on('keypad.up', 		lambda: broadcast('playdir', 1))
hplayer.on('keypad.down', 		lambda: broadcast('playdir', 2))
hplayer.on('keypad.right', 		lambda: broadcast('playdir', 3)) 
hplayer.on('keypad.select', 	lambda: broadcast('stop'))
hplayer.on('gpio.21-on', 		lambda: broadcast('end'))


# Keyboard
#
hplayer.on('keyboard.KEY_KP0-down', 		lambda: broadcast('playdir', 0))
hplayer.on('keyboard.KEY_KP1-down', 		lambda: broadcast('playdir', 1))
hplayer.on('keyboard.KEY_KP2-down', 		lambda: broadcast('playdir', 2))
hplayer.on('keyboard.KEY_KP3-down', 		lambda: broadcast('playdir', 3))
hplayer.on('keyboard.KEY_KP4-down', 		lambda: broadcast('playdir', 4))
hplayer.on('keyboard.KEY_KP5-down', 		lambda: broadcast('playdir', 5))
hplayer.on('keyboard.KEY_KP6-down', 		lambda: broadcast('playdir', 6))
hplayer.on('keyboard.KEY_KP7-down', 		lambda: broadcast('playdir', 7))
hplayer.on('keyboard.KEY_KP8-down', 		lambda: broadcast('playdir', 8))
hplayer.on('keyboard.KEY_KP9-down', 		lambda: broadcast('playdir', 9))
hplayer.on('keyboard.KEY_KPENTER-down',     lambda: broadcast('stop'))
hplayer.on('keyboard.KEY_KPDOT-down',       lambda: broadcast('end'))

hplayer.on('keyboard.KEY_KPPLUS-down', 		lambda: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPPLUS-hold', 		lambda: broadcast('volume', hplayer.settings.get('volume')+1))
hplayer.on('keyboard.KEY_KPMINUS-down', 	lambda: broadcast('volume', hplayer.settings.get('volume')-1))	
hplayer.on('keyboard.KEY_KPMINUS-hold', 	lambda: broadcast('volume', hplayer.settings.get('volume')-1))	



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
