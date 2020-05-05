from core.engine import hplayer
from core.engine import network
import os, types, platform

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', 'chalon')
player.loop(1)
# player.doLog['events'] = True

# Interfaces
player.addInterface('zyre', 'wlan0')
player.addInterface('http2', 8080)
player.addInterface('http', 8037)
player.addInterface('keyboard')

is_RPi = platform.machine().startswith('armv')
if is_RPi:
	player.addInterface('keypad')


# BROADCAST to other Pi's
def broadcast(path, *args):
	if path.startswith('/play'):
		player.getInterface('zyre').node.broadcast(path, list(args), 434)   ## WARNING LATENCY !! (1WATT 434ms)
	else:
		player.getInterface('zyre').node.broadcast(path, list(args))


# DIRECTORY / FILE
if is_RPi: base_path = '/mnt/usb'
else: base_path = '/home/mgr/Videos'
available_dir = [d for d in next(os.walk(base_path))[1] if not d.startswith('.')]
available_dir.sort()
active_dir = 0
active_dir_length = 0
if len(available_dir) == 0: available_dir.insert(0,'')
set_activedir(0)


def play_media(target_dir):
	if target_dir < len(available_dir):
		target_path = os.path.join(base_path, available_dir[target_dir])
		available_files = [f for f in next(os.walk(target_path))[2] if not f.startswith('.')]
		available_files.sort()
		for f in available_files:
			if f.startswith(str(args[1])):
				set_activedir(target_dir)
				player.play( available_files.index(f) )

def play_activedir(index):
	#available_files = [f for f in next(os.walk(current_dir()))[2] if not f.startswith('.')]
	#media = available_files[index]
	broadcast('/playmedia', active_dir, index)

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

def set_activedir(index):
	if index >= 0 and index < len(available_dir):
		global active_dir, active_dir_length
		active_dir = index
		active_dir_length = len(player.buildList(current_dir()))
		player.stop()
		change_scene(available_dir[active_dir])
		player.load(current_dir())

def change_scene(dir):
	if isinstance(dir, list):
		dir = dir[0]
	if dir in available_dir:
		global active_dir
		active_dir = available_dir.index(dir)
		# DO NOT RE-BROADCAST !!

player.on(['/playmedia'], 		lambda ev, dir: play_media(dir))

#
# Bind Keypad
#
player.on(['keypad-down'], 		lambda ev: next_dir())
player.on(['keypad-up'], 		lambda ev: prev_dir())
player.on(['keypad-right'], 	lambda ev: player.next()) 
player.on(['keypad-left'], 		lambda ev: player.prev())
player.on(['keypad-select'], 	lambda ev: player.stop())

#
# Bind Keyboard
#
tabPressed = False

def keyboard_tab(switch):
	global tabPressed
	tabPressed = switch

def keyboard_numbers(n):
	global tabPressed
	if tabPressed:
		set_activedir(n)
	elif n > 0: 
		play_activedir(n)

def vol_inc():
	broadcast('/volume', player.settings()['volume']+1)

def vol_dec():
	broadcast('/volume', player.settings()['volume']-1)

player.on(['KEY_TAB-down'], 	lambda ev: keyboard_tab(True))
player.on(['KEY_TAB-up'], 		lambda ev: keyboard_tab(False))

player.on(['KEY_KP0-down'], 	lambda ev: keyboard_numbers(0))
player.on(['KEY_KP1-down'], 	lambda ev: keyboard_numbers(1))
player.on(['KEY_KP2-down'], 	lambda ev: keyboard_numbers(2))
player.on(['KEY_KP3-down'], 	lambda ev: keyboard_numbers(3))
player.on(['KEY_KP4-down'], 	lambda ev: keyboard_numbers(4))
player.on(['KEY_KP5-down'], 	lambda ev: keyboard_numbers(5))
player.on(['KEY_KP6-down'], 	lambda ev: keyboard_numbers(6))
player.on(['KEY_KP7-down'], 	lambda ev: keyboard_numbers(7))
player.on(['KEY_KP8-down'], 	lambda ev: keyboard_numbers(8))
player.on(['KEY_KP9-down'], 	lambda ev: keyboard_numbers(9))
# player.on(['KEY_KPDOT-down'], 	lambda ev: keyboard_dot())
player.on(['KEY_KPENTER-down'], lambda ev: broadcast('/stop'))
player.on(['KEY_KPPLUS-down', 'KEY_KPPLUS-hold'], 	lambda ev: vol_inc())
player.on(['KEY_KPMINUS-down', 'KEY_KPMINUS-hold'], lambda ev: vol_dec())



# PATCH Keypad LCD update
def lcd_update(self):
	lines = ["", ""]

	# Line 1 : SCENE + VOLUME
	lines[0] = available_dir[active_dir].ljust(13, ' ')[:13]
	lines[0] += str(self.player.settings()['volume']).rjust(3, ' ')[:3]

	# Line 2 : MEDIA
	if not self.player.status()['media']: lines[1] = '-stop-'
	else: lines[1] = os.path.basename(self.player.status()['media'])[:-4]
	lines[1] = lines[1].ljust(14, ' ')[:14]
	lines[1] += str(player.getInterface('zyre').activeCount()).rjust(2, ' ')[:2]

	return lines

if is_RPi:
	player.getInterface('keypad').update = types.MethodType(lcd_update, player.getInterface('keypad'))



# RUN
hplayer.setBasePath(["/mnt/usb"])        	# Media base path
hplayer.persistentSettings("/data/hplayer2-kxkm.cfg")   # Path to persitent config
hplayer.run()                               # TODO: non blocking
