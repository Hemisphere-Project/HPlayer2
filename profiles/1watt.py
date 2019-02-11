from core.engine import hplayer
from core.engine import network
import os

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', '1watt')
player.loop(1)
# player.doLog['events'] = True

# Interfaces
player.addInterface('osc', 4000, 4000).hostOut = network.get_broadcast()
player.addInterface('http', 8037)
player.addInterface('http2', 8080)
player.addInterface('keypad')
player.addInterface('keyboard')

# Sub folders
base_path = '/data/media'
available_dir = next(os.walk(base_path))[1]
available_dir.insert(0,'')
active_dir = 0

def current_dir():
	return os.path.join(basepath, available_dir[active_dir])

def next_dir():
	active_dir += 1
	if active_dir >= len(available_dir): active_dir=0

def prev_dir():
	active_dir -= 1
	if active_dir < 0: active_dir=len(available_dir)-1


# Broadcast Order on OSC to other Pi's
def broadcast(path, args=None):
	player.getInterface('osc').hostOut = network.get_broadcast()
	player.getInterface('osc').send(path, args)

# Bind Keypad
player.on(['keypad-left'], 		lambda: broadcast('/playindex', 0))
player.on(['keypad-up'], 		lambda: broadcast('/playindex', 1))
player.on(['keypad-down'], 		lambda: broadcast('/playindex', 2))
player.on(['keypad-right'], 	lambda: broadcast('/playindex', 3))
player.on(['keypad-select'], 	lambda: broadcast('/stop'))

# Bind Keyboard
player.on(['KEY_KP1-down'], 	lambda: broadcast('/playindex', 0))
player.on(['KEY_KP2-down'], 	lambda: broadcast('/playindex', 1))
player.on(['KEY_KP3-down'], 	lambda: broadcast('/playindex', 2))
player.on(['KEY_KP4-down'], 	lambda: broadcast('/playindex', 3))
player.on(['KEY_KP5-down'], 	lambda: broadcast('/playindex', 4))
player.on(['KEY_KP6-down'], 	lambda: broadcast('/playindex', 5))
player.on(['KEY_KP7-down'], 	lambda: broadcast('/playindex', 6))
player.on(['KEY_KP8-down'], 	lambda: broadcast('/playindex', 7))
player.on(['KEY_KP9-down'], 	lambda: broadcast('/playindex', 8))
player.on(['KEY_KPENTER-down'], lambda: broadcast('/stop'))

# Bind HTTP remotes
player.on(['btn1'], 		lambda: broadcast('/playlist', current_dir(), 0))
player.on(['btn2'], 		lambda: broadcast('/playlist', current_dir(), 1))
player.on(['btn3'], 		lambda: broadcast('/playlist', current_dir(), 2))
player.on(['btn4'], 		lambda: broadcast('/playlist', current_dir(), 3))
player.on(['next'], 		next_dir) 
player.on(['prev'], 		prev_dir)


# OSC synctest request from ESP remotes
def syncTest(arg):
	display = available_dir[active_dir] + " \""
	if player.status()['media'] is not None:
		display += os.path.basename(player.status()['media'])[:-4]
	else:
		display += "-stop-"
	player.getInterface('osc').send(display)

player.on(['/synctest'], syncTest)




# RUN
# hplayer.setBasePath(["/mnt/usb"])        	# Media base path
hplayer.run()                               # TODO: non blocking
