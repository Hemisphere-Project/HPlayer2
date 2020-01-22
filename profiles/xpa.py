import os, types, platform
from core.engine import hplayer
from core.engine import network
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from threading import Timer

# NAME
#
playerName = network.get_hostname()

# PLAYER
#
player = hplayer.addplayer('mpv', network.get_hostname())
player.loop(1)
# player.doLog['events'] = True

# Interfaces
#
player.addInterface('zyre', 'wlan0')
player.addInterface('osc', 4000, 4000).hostOut = '255.255.255.255'
player.addInterface('http2', 8080)
player.addInterface('http', 8037)
player.addInterface('keyboard')

is_RPi = platform.machine().startswith('armv')
if is_RPi:
	player.addInterface('keypad')


# Files list
#
if is_RPi: base_path = '/data/sync'
else: base_path = '/home/mgr/Videos'

available_dir = []
active_dir_length = 0
refreshTimer = None

def refresh_filelist():
	global refreshTimer, available_dir
	refreshTimer = None
	available_dir = [d for d in next(os.walk(base_path))[1] if not d.startswith('.')]
	available_dir.sort()
	if len(available_dir) == 0: available_dir.insert(0,'')
	print('File list updated')

def file_change(event):
	global refreshTimer
	if not refreshTimer:
		refreshTimer = Timer(3.0, refresh_filelist)
		refreshTimer.start()

my_event_handler = PatternMatchingEventHandler("*", "", False, True)
my_event_handler.on_any_event = file_change
my_observer = Observer()
my_observer.schedule(my_event_handler, base_path, recursive=True)
my_observer.start()

player.setBasePath(base_path)

# Broadcast Order on OSC/Zyre to other Pi's
#
def broadcast(path, *args):
	if player.getInterface('zyre').activeCount() <= 1:
		player.getInterface('osc').hostOut = network.get_broadcast('wlan0')
		player.getInterface('osc').sendBurst(path, *args)

	if path.startswith('/play'):
		player.getInterface('zyre').node.broadcast(path, list(args), 250)   ## WARNING LATENCY !! (1WATT 434ms)

	else:
		player.getInterface('zyre').node.broadcast(path, list(args))


# Play media in indexed directory
# /playmedia callback
# args = [ 0:dir-index, 1:media-startswith]
#
def play_ActiveIndex(args): 	
	target_dir = args[0]
	if target_dir < len(available_dir):
		target_path = os.path.join(base_path, available_dir[target_dir])
		available_files = [f for f in next(os.walk(target_path))[2] if not f.startswith('.')]
		available_files.sort()
		for f in available_files:
			if f.startswith(str(args[1])):
				set_activedir(target_dir)
				player.play( available_files.index(f) )

# Play media in indexed directory
# Zyre Broadcast
#
def play_indexInActivedir(index):
	broadcast('/playActiveIndex', active_dir, index)

# Set active dir
#
def set_activedir(index):
	if index >= 0 and index < len(available_dir):
		global active_dir, active_dir_length
		active_dir = index
		active_dir_length = len(player.buildList(current_dir()))
		player.stop()
		player.load(current_dir())

# Get full path of activedir
#
def current_dir():
	return os.path.join(base_path, available_dir[active_dir])

# Go to next dir
#
def next_dir():
	new_dir = active_dir+1
	if new_dir  >= len(available_dir): new_dir=0
	set_activedir(new_dir)

# Go to prev dir
#
def prev_dir():
	new_dir = active_dir-1
	if new_dir < 0: new_dir=len(available_dir)-1
	set_activedir(new_dir)


# Init dirs
#
refresh_filelist()
set_activedir(0)

# Bind custom Zyre events
#
player.on(['/rescan'], refresh_filelist)
player.on(['/playActiveIndex'],  play_ActiveIndex)


# Bind Keypad events
#
player.on(['keypad-down'], 		next_dir)
player.on(['keypad-up'], 		prev_dir)
player.on(['keypad-right'], 	player.next) 
player.on(['keypad-left'], 		player.prev)
player.on(['keypad-select'], 	player.stop)


# Bind Keyboard
tabPressed = False

def keyboard_tab(switch):
	global tabPressed
	tabPressed = switch

def keyboard_numbers(n):
	global tabPressed
	if tabPressed:
		set_activedir(n)
	elif n > 0: 
		play_indexInActivedir(n)

def vol_inc():
	broadcast('/volume', player.settings()['volume']+1)

def vol_dec():
	broadcast('/volume', player.settings()['volume']-1)

player.on(['KEY_TAB-down'], 	lambda: keyboard_tab(True))
player.on(['KEY_TAB-up'], 		lambda: keyboard_tab(False))

player.on(['KEY_KP0-down'], 	lambda: keyboard_numbers(0))
player.on(['KEY_KP1-down'], 	lambda: keyboard_numbers(1))
player.on(['KEY_KP2-down'], 	lambda: keyboard_numbers(2))
player.on(['KEY_KP3-down'], 	lambda: keyboard_numbers(3))
player.on(['KEY_KP4-down'], 	lambda: keyboard_numbers(4))
player.on(['KEY_KP5-down'], 	lambda: keyboard_numbers(5))
player.on(['KEY_KP6-down'], 	lambda: keyboard_numbers(6))
player.on(['KEY_KP7-down'], 	lambda: keyboard_numbers(7))
player.on(['KEY_KP8-down'], 	lambda: keyboard_numbers(8))
player.on(['KEY_KP9-down'], 	lambda: keyboard_numbers(9))
player.on(['KEY_KPDOT-down'], 	lambda: broadcast('/rescan'))
player.on(['KEY_KPENTER-down'], lambda: broadcast('/stop'))
player.on(['KEY_KPPLUS-down', 	'KEY_KPPLUS-hold'], 	vol_inc)
player.on(['KEY_KPMINUS-down', 	'KEY_KPMINUS-hold'], 	vol_dec)


# Bind HTTP button remotes
#
# player.on(['btn1'], 		lambda: play_indexInActivedir(0))
# player.on(['btn2'], 		lambda: play_indexInActivedir(1))
# player.on(['btn3'], 		lambda: play_indexInActivedir(2))
# player.on(['btn4'], 		lambda: play_indexInActivedir(3))
# player.on(['btn5'], 		lambda: play_indexInActivedir(4))
# player.on(['btn6'], 		lambda: play_indexInActivedir(5))
# player.on(['btn7'], 		lambda: play_indexInActivedir(6))
# player.on(['btn8'], 		lambda: broadcast('/stop'))
# player.on(['inc'], 			remote_inc)
# player.on(['dec'], 			remote_dec)
# player.on(['push'], 		switch_mode)


# OSC synctest request from ESP remotes
#
# def syncTest(arg):
# 	if remote_page == 0:
# 		#SCENE
# 		display = available_dir[active_dir].replace("scene ", "S.")[:6].ljust(6)
# 		display += "#"

# 		# MEDIA
# 		media = player.status()['media']
# 		for i in range(7):
# 			# if i == player.status()['index'] and media.startswith(current_dir()): display += str(i+1)
# 			if i < active_dir_length: display += ' *'
# 			else : display += ' .'

# 		display += "#"
# 		if not player.status()['media']: display += '-stop-'
# 		else: display += media[:-4].replace(base_path, '')[1:].replace("scene", "S.").replace("/", " / ")

# 	elif remote_page == 1:
# 		# VOLUME
# 		vol = player.settings()['volume']
# 		display = "VOLUME "
# 		display += str(vol).rjust(3)
# 		# PEERS
# 		display += "#Dispositifs".ljust(19)+str(player.getInterface('zyre').activeCount()).rjust(2)
		
# 	else:
# 	    display = "page "+str(remote_page)

# 	player.getInterface('osc').send(display)

# player.on(['/synctest'], syncTest)


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
#hplayer.setBasePath(["/mnt/usb"])        	# Media base path
hplayer.run()                               # TODO: non blocking


# EXIT
my_observer.stop()
my_observer.join()
