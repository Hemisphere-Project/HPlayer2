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

# Brodcast IPs
# remotes_broadcast = network.get_broadcast("wlan1")
# rpis_broadcast = network.get_broadcast("eth0")
# if rpis_broadcast == '127.0.0.1': rpis_broadcast = network.get_broadcast("wlan0")

# Remote modes
remote_mode = True

# Sub folders
base_path = '/mnt/usb'
available_dir = [d for d in next(os.walk(base_path))[1] if not d.startswith('.')]
available_dir.sort()
if len(available_dir) == 0:
	available_dir.insert(0,'')
active_dir = 0


def current_dir():
	return os.path.join(base_path, available_dir[active_dir])

def next_dir():
	global active_dir
	active_dir += 1
	if active_dir >= len(available_dir): active_dir=0

def prev_dir():
	global active_dir
	active_dir -= 1
	if active_dir < 0: active_dir=len(available_dir)-1

def last_dir():
	global active_dir
	active_dir = len(available_dir)-1

def sel_dir(dir):
	dir = dir[0]
	if dir in available_dir:
		global active_dir
		active_dir = available_dir.index(dir)

def switch_mode():
	global remote_mode
	remote_mode = not remote_mode

def remote_inc():
	if remote_mode: next_dir()
	else: player.volume_inc()

def remote_dec():
	if remote_mode: prev_dir()
	else: player.volume_dec()


# Broadcast Order on OSC to other Pi's
def broadcast(path, *args):
	# player.getInterface('osc').hostOut = rpis_broadcast
	player.getInterface('osc').send(path, *args)

def play_inlist(index):
	broadcast('/playlist', current_dir(), index)
	broadcast('/scene', available_dir[active_dir])

def play_final(index):
	last_dir()
	play_inlist(index)


player.on(['/scene'], 			sel_dir)

# Bind Keypad
player.on(['keypad-left'], 		lambda: play_inlist(0))
player.on(['keypad-up'], 		lambda: play_inlist(1))
player.on(['keypad-down'], 		lambda: play_inlist(2))
player.on(['keypad-right'], 	lambda: play_inlist(3))
player.on(['keypad-select'], 	lambda: broadcast('/stop'))

# Bind Keyboard
player.on(['KEY_KP1-down'], 	lambda: play_final(0))
player.on(['KEY_KP2-down'], 	lambda: play_final(1))
player.on(['KEY_KP3-down'], 	lambda: play_final(2))
player.on(['KEY_KP4-down'], 	lambda: play_final(3))
player.on(['KEY_KP5-down'], 	lambda: play_final(4))
player.on(['KEY_KP6-down'], 	lambda: play_final(5))
player.on(['KEY_KP7-down'], 	lambda: play_final(6))
player.on(['KEY_KP8-down'], 	lambda: play_final(7))
player.on(['KEY_KP9-down'], 	lambda: play_final(8))
player.on(['KEY_KPENTER-down'], lambda: broadcast('/stop'))

# Bind HTTP remotes
player.on(['btn1'], 		lambda: play_inlist(0))
player.on(['btn2'], 		lambda: play_inlist(1))
player.on(['btn3'], 		lambda: play_inlist(2))
player.on(['btn4'], 		lambda: play_inlist(3))
player.on(['inc'], 			remote_inc)
player.on(['dec'], 			remote_dec)
player.on(['push'], 		switch_mode)


# OSC synctest request from ESP remotes
def syncTest(arg):
	if remote_mode:
		display = available_dir[active_dir] + " #"
		if player.status()['media'] is not None:
			display += os.path.basename(player.status()['media'])[:-4]
		else:
			display += "-stop-"
	else:
		display = "VOLUME#"+str(player.settings()['volume'])

	# player.getInterface('osc').hostOut = remotes_broadcast
	player.getInterface('osc').send(display)

player.on(['/synctest'], syncTest)




# RUN
# hplayer.setBasePath(["/mnt/usb"])        	# Media base path
hplayer.run()                               # TODO: non blocking
