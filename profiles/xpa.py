from core.engine import hplayer
from core.engine import network
import os, sys, types, platform

profilename = os.path.basename(__file__).split('.')[0]

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv')
player.loop(0)
player.doLog['events'] = True

# Interfaces
player.addInterface('zyre', 'wlan0')
player.addInterface('http2', 8080)
# player.addInterface('http', 8037)
player.addInterface('keyboard')

if hplayer.isRPi():
	player.addInterface('keypad')
	player.addInterface('gpio', [21], 310)


# DIRECTORY / FILE
if hplayer.isRPi(): base_path = '/data/sync/media'
else: base_path = '/home/mgr/Videos'


# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	if path.startswith('/seq'):
		player.getInterface('zyre').node.broadcast(path, list(args), 100)   ## WARNING LATENCY !!
	else:
		player.getInterface('zyre').node.broadcast(path, list(args))

# MASTER / SLAVE sequencer
iamLeader = False
currentSequence = 0
lastSequence = 3

# Detect if i am zyre Leader
@player.on('zyre')
def leadSequencer(data):
	global iamLeader
	iamLeader = (data['from'] == 'self')

# Receive a sequence command -> do Play !
@player.on('/seq')
def doPlay(s):
	if type(s) is list: s = s[0]
	global currentSequence
	currentSequence = s
	player.play(str(s)+"*")

# Receive a exit command -> last seq
@player.on('/exit')
def doExit(s):
	doPlay(lastSequence)

@player.on('stop')
def endSequence():
	if not iamLeader: 
		return
	global currentSequence
	if currentSequence == 0 or currentSequence == lastSequence:
		broadcast('/seq', 0)
	else:
		broadcast('/seq', currentSequence+1)


# Bind Keypad / GPIO events
#
player.on(['keypad-left'], 					lambda: broadcast('/seq', 1))
player.on(['keypad-up'], 					lambda: broadcast('/seq', 2))
player.on(['keypad-down'], 					lambda: broadcast('/seq', 3))
player.on(['keypad-right'], 				lambda: broadcast('/seq', 4)) 
player.on(['keypad-select', 'gpio21-on'], 	lambda: broadcast('/exit'))


# Keyboard
#
player.on(['KEY_KP0-down'], 	lambda: broadcast('/seq', 0))
player.on(['KEY_KP1-down'], 	lambda: broadcast('/seq', 1))
player.on(['KEY_KP2-down'], 	lambda: broadcast('/seq', 2))
player.on(['KEY_KP3-down'], 	lambda: broadcast('/seq', 3))
player.on(['KEY_KP4-down'], 	lambda: broadcast('/seq', 4))
player.on(['KEY_KP5-down'], 	lambda: broadcast('/seq', 5))
player.on(['KEY_KP6-down'], 	lambda: broadcast('/seq', 6))
player.on(['KEY_KP7-down'], 	lambda: broadcast('/seq', 7))
player.on(['KEY_KP8-down'], 	lambda: broadcast('/seq', 8))
player.on(['KEY_KP9-down'], 	lambda: broadcast('/seq', 9))
player.on(['KEY_KPENTER-down'], lambda: broadcast('/exit'))
player.on(['KEY_KPPLUS-down', 	'KEY_KPPLUS-hold'], 	broadcast('/volume', player.settings()['volume']+1))
player.on(['KEY_KPMINUS-down', 	'KEY_KPMINUS-hold'], 	broadcast('/volume', player.settings()['volume']-1))	



# PATCH Keypad LCD update
def lcd_update(self):
	lines = ["", ""]

	# Line 1 : SCENE + VOLUME
	lines[0] = profilename.ljust(13, ' ')[:13]
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
