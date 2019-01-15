from core.engine import hplayer
from core.engine import network
import os, types, platform

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', 'hidesee')
player.loop(1)
# player.doLog['events'] = True

# Interfaces
player.addInterface('zyre', 'wlan0')
player.addInterface('osc', 4000, 4000).hostOut = '3.0.0.255'	# remote
player.addInterface('http', 8037)
player.addInterface('keyboard')

is_RPi = platform.machine().startswith('armv')
if is_RPi:
	player.addInterface('keypad')


# Remote modes
total_page = 2
remote_page = 0

def switch_mode():
	global remote_page
	remote_page = (remote_page+1)%total_page

def remote_inc():
	if remote_page == 0: next_dir()
	elif remote_page == 1: vol_inc()

def remote_dec():
	if remote_page == 0: prev_dir()
	elif remote_page == 1: vol_dec()

def vol_inc():
	broadcast('/volume', player.settings()['volume']+1)

def vol_dec():
	broadcast('/volume', player.settings()['volume']-1)


# Broadcast Order on OSC to other Pi's
def broadcast(path, *args):
	if path.startswith('/play'):
		player.getInterface('zyre').node.broadcast(path, list(args), 0)   ## WARNING LATENCY !! (1WATT 434ms)
	else:
		player.getInterface('zyre').node.broadcast(path, list(args))

	# player.getInterface('osc').hostOut = network.get_broadcast('wlan0')
	# player.getInterface('osc').sendBurst(path, *args)

def play_activedir(index):
	broadcast('/playlist', current_dir(), index)
	broadcast('/scene', available_dir[active_dir])

def play_lastdir(index):
	sel_lastdir()
	play_activedir(index)

def play_firstdir(index):
	sel_firstdir()
	play_activedir(index)


def current_dir():
	return os.path.join(base_path, available_dir[active_dir])

def next_dir():
	new_dir = active_dir+1
	if new_dir  >= len(available_dir): new_dir=0
	set_activedir(new_dir)

def prev_dir():
	new_dir = active_dir-1
	if new_dir < 0: new_dir=len(available_dir)-1
	set_activedir(new_dir)

def sel_lastdir():
	set_activedir(len(available_dir)-1)

def sel_firstdir():
	set_activedir(0)

def set_activedir(index):
	if index >= 0 and index < len(available_dir):
		global active_dir, active_dir_length
		active_dir = index
		active_dir_length = len(player.buildList(current_dir()))
		broadcast('/scene', available_dir[active_dir])

def change_scene(dir):
	if isinstance(dir, list):
		dir = dir[0]
	if dir in available_dir:
		global active_dir
		active_dir = available_dir.index(dir)
		# DO NOT RE-BROADCAST !!

# Sub folders
if is_RPi: base_path = '/mnt/usb'
else: base_path = '/home/mgr/Videos'
available_dir = [d for d in next(os.walk(base_path))[1] if not d.startswith('.')]
available_dir.sort()
active_dir_length = 0
if len(available_dir) == 0: available_dir.insert(0,'')
set_activedir(0)



player.on(['/scene'], 			change_scene)

# Bind Keypad
player.on(['keypad-left'], 		lambda: play_firstdir(0))
player.on(['keypad-up'], 		lambda: play_firstdir(1))
player.on(['keypad-down'], 		lambda: play_firstdir(2))
player.on(['keypad-right'], 	lambda: play_firstdir(3))
player.on(['keypad-select'], 	lambda: broadcast('/stop'))

# Bind Keyboard
player.on(['KEY_KP0-down'], 	lambda: set_activedir(0))
player.on(['KEY_KP1-down'], 	lambda: set_activedir(1))
player.on(['KEY_KP2-down'], 	lambda: set_activedir(2))
player.on(['KEY_KP3-down'], 	lambda: set_activedir(3))
player.on(['KEY_KP4-down'], 	lambda: set_activedir(4))
player.on(['KEY_KP5-down'], 	lambda: set_activedir(5))
player.on(['KEY_KP6-down'], 	lambda: set_activedir(6))
player.on(['KEY_KP7-down'], 	lambda: set_activedir(7))
player.on(['KEY_KP8-down'], 	lambda: set_activedir(8))
player.on(['KEY_KP9-down'], 	lambda: set_activedir(9))
player.on(['KEY_KPDOT-down'], 	lambda: sel_lastdir())
player.on(['KEY_KPENTER-down'], lambda: broadcast('/stop'))
player.on(['KEY_KPPLUS-down', 'KEY_KPPLUS-hold'], 	vol_inc)
player.on(['KEY_KPMINUS-down', 'KEY_KPMINUS-hold'], vol_dec)

# Bind HTTP remotes + Keyboard
player.on(['btn1', 'KEY_NUMLOCK-down'], 		lambda: play_activedir(0))
player.on(['btn2', 'KEY_KPSLASH-down'], 		lambda: play_activedir(1))
player.on(['btn3', 'KEY_KPASTERISK-down'], 		lambda: play_activedir(2))
player.on(['btn4', 'KEY_BACKSPACE-down'], 		lambda: play_activedir(3))
player.on(['inc'], 			remote_inc)
player.on(['dec'], 			remote_dec)
player.on(['push'], 		switch_mode)



# OSC synctest request from ESP remotes
def syncTest(arg):
	if remote_page == 0:
		#SCENE
		display = available_dir[active_dir].replace("scene ", "S.")[:6].ljust(6)

		# MEDIA
		media = player.status()['media']
		for i in range(4):
			# if i == player.status()['index'] and media.startswith(current_dir()): display += str(i+1)
			if i < active_dir_length: display += '-'
			else : display += '.'

		display += "#"
		if not player.status()['media']: display += '-stop-'
		else: display += media[:-4].replace(base_path, '')[1:].replace("scene", "S.").replace("/", " / ")

	elif remote_page == 1:
		# VOLUME
		vol = player.settings()['volume']
		display = "VOLUME "
		display += str(vol).rjust(3)
		# PEERS
		display += "#Dispositifs".ljust(19)+str(player.getInterface('zyre').activeCount()).rjust(2)
		
	else:
	    display = "page "+str(remote_page)

	player.getInterface('osc').send(display)

player.on(['/synctest'], syncTest)


# PATCH Keypad LCD update
def lcd_update(self):
	lines = ["", ""]

	# Line 1 : SCENE + VOLUME
	lines[0] = available_dir[active_dir].ljust(13, ' ')[:13]
	lines[0] += str(self.player.settings()['volume']).rjust(3, ' ')[:3]

	# Line 2 : MEDIA
	if not self.player.status()['media']: lines[1] = '-stop-'
	else: lines[1] = os.path.basename(self.player.status()['media'])[:-4]
	lines[1] = lines[1].ljust(16, ' ')[:16]

	return lines

if is_RPi:
	player.getInterface('keypad').update = types.MethodType(lcd_update, player.getInterface('keypad'))




# RUN
#hplayer.setBasePath(["/mnt/usb"])        	# Media base path
hplayer.run()                               # TODO: non blocking
