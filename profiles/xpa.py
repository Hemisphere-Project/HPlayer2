from core.engine import hplayer
from core.engine import network
from core.engine.filemanager import FileManager
import os, sys, types, platform

profilename = os.path.basename(__file__).split('.')[0]

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv')
player.loop(0)

midi = hplayer.addplayer('midi')
midi.loop(0)

# player.doLog['events'] = True

# Interfaces
player.addInterface('zyre', 'wlan0')
player.addInterface('http2', 8080)
# player.addInterface('http', 8037)
player.addInterface('keyboard')

if hplayer.isRPi():
	player.addInterface('keypad')
	player.addInterface('gpio', [21], 310)


# DIRECTORY / FILE
if hplayer.isRPi(): base_path = '/data/sync/xpa'
else: base_path = '/home/mgr/Videos'

# FILES
files = FileManager( [base_path] )

# MASTER / SLAVE sequencer
iamLeader = False

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	if path.startswith('/dir'):
		player.getInterface('zyre').node.broadcast(path, list(args), 100)   ## WARNING LATENCY !!
	else:
		player.getInterface('zyre').node.broadcast(path, list(args))

# Detect if i am zyre Leader
@player.on('zyre')
def leadSequencer(data):
	global iamLeader
	iamLeader = (data['from'] == 'self')

# Receive a sequence command -> do Play !
@player.on('/dir')
def doPlay(s):
	if type(s) is list: s = s[0]
	player.play( files.selectDir(s)+'/'+playerName+'*' )

# Receive an exit command -> last seq
@player.on('/end')
def doExit(s):
	player.play( files.selectDir(-1)+'/'+playerName+'*' )

# Media end: next dir / or loop (based on directory name)
@player.on('stop')
def endSequence():
	if not iamLeader: 
		return
	if 'loop' in files.currentDir():
		broadcast('/dir', files.currentIndex())
	else:
		broadcast('/dir', files.nextIndex())


# Bind Keypad / GPIO events
#
player.on(['keypad-left'], 					lambda: broadcast('/dir', 1))
player.on(['keypad-up'], 					lambda: broadcast('/dir', 2))
player.on(['keypad-down'], 					lambda: broadcast('/dir', 3))
player.on(['keypad-right'], 				lambda: broadcast('/dir', 4)) 
player.on(['keypad-select', 'gpio21-on'], 	lambda: broadcast('/end'))


# Keyboard
#
player.on(['KEY_KP0-down'], 	lambda: broadcast('/dir', 0))
player.on(['KEY_KP1-down'], 	lambda: broadcast('/dir', 1))
player.on(['KEY_KP2-down'], 	lambda: broadcast('/dir', 2))
player.on(['KEY_KP3-down'], 	lambda: broadcast('/dir', 3))
player.on(['KEY_KP4-down'], 	lambda: broadcast('/dir', 4))
player.on(['KEY_KP5-down'], 	lambda: broadcast('/dir', 5))
player.on(['KEY_KP6-down'], 	lambda: broadcast('/dir', 6))
player.on(['KEY_KP7-down'], 	lambda: broadcast('/dir', 7))
player.on(['KEY_KP8-down'], 	lambda: broadcast('/dir', 8))
player.on(['KEY_KP9-down'], 	lambda: broadcast('/dir', 9))
player.on(['KEY_KPENTER-down'], lambda: broadcast('/end'))
player.on(['KEY_KPPLUS-down', 	'KEY_KPPLUS-hold'], 	broadcast('/volume', player.settings()['volume']+1))
player.on(['KEY_KPMINUS-down', 	'KEY_KPMINUS-hold'], 	broadcast('/volume', player.settings()['volume']-1))	



# PATCH Keypad LCD update
def lcd_update(self):
	lines = ["", ""]

	# Line 1 : SCENE + VOLUME
	lines[0] = files.currentDir().ljust(13, ' ')[:13]
	lines[0] += str(self.player.settings()['volume']).rjust(3, ' ')[:3]

	# Line 2 : MEDIA
	if not self.player.status()['media']: lines[1] = '-stop-'
	else: lines[1] = os.path.basename(self.player.status()['media'])[:-4]
	lines[1] = lines[1].ljust(14, ' ')[:14]
	lines[1] += str(player.getInterface('zyre').activeCount()).rjust(2, ' ')[:2]

	return lines

if hplayer.isRPi():
	player.getInterface('keypad').update = types.MethodType(lcd_update, player.getInterface('keypad'))



# RUN
hplayer.setBasePath([base_path])        							# Media base path
hplayer.persistentSettings("/data/hplayer2-"+profilename+".cfg")   	# Path to persitent config
hplayer.run()                               						# TODO: non blocking
