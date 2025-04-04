from core.engine import hplayer
from core.engine import network
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
import os, types, platform

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', '1watt')
player.loop(1)
# player.doLog['events'] = True

# INTERFACES
player.addInterface('zyre', 'wlan0')
player.addInterface('osc', 4000).hostOut = '10.0.0.255'
player.addInterface('http', 8037)
player.addInterface('keyboard')

is_RPi = platform.machine().startswith('armv')
if is_RPi:
	player.addInterface('keypad')


# FIX early boot ETH0 error
from threading import Timer
import subprocess
from time import sleep
def restartEth0():
    print('switch OFF eth0')
    subprocess.run(['ip', 'link', 'set', 'eth0', 'down'])
    sleep(15)
    print('switch ON eth0')
    subprocess.run(['ip', 'link', 'set', 'eth0', 'up'])  
# Timer(5, restartEth0).start()


# Remote modes
remote_mode = True

def switch_mode(**kwargs):
	global remote_mode
	remote_mode = not remote_mode

def remote_inc(**kwargs):
	if remote_mode: next_dir()
	else: vol_inc()

def remote_dec(**kwargs):
	if remote_mode: prev_dir()
	else: vol_dec()


# BROADCAST to other Pi's
def broadcast(path, *args):
	if path.startswith('/play'):
		player.getInterface('zyre').node.broadcast(path, list(args), 434)
	else:
		player.getInterface('zyre').node.broadcast(path, list(args))
	# player.getInterface('osc').hostOut = network.get_broadcast('wlan0')
	# player.getInterface('osc').sendBurst(path, *args)

# VOLUME
def vol_inc():
	broadcast('/volume', player.settings()['volume']+1)

def vol_dec():
	broadcast('/volume', player.settings()['volume']-1)


# Files list
#
base_path = '/data/usb'

available_dir = []
active_dir_length = 0
active_dir = 0
refreshTimer = None

def refresh_filelist():
    global refreshTimer, available_dir
    refreshTimer = None
    available_dir = [d for d in next(os.walk(base_path))[1] if not d.startswith('.')]
    available_dir.sort()
    if len(available_dir) == 0: available_dir.insert(0,'')
    if len(available_dir) >= 2: set_activedir(1)
    else: set_activedir(0)
    print('File list updated')

def file_change(event):
	global refreshTimer
	if not refreshTimer:
		refreshTimer = Timer(3.0, refresh_filelist)
		refreshTimer.start()

my_event_handler = PatternMatchingEventHandler(
                            patterns=["*"],
                            ignore_patterns=None,
                            ignore_directories=False,
                            case_sensitive=True
                        )
my_event_handler.on_any_event = file_change
my_observer = Observer()
my_observer.schedule(my_event_handler, base_path, recursive=True)
my_observer.start()

player.setBasePath(base_path)


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


# Init dirs
#
refresh_filelist()
#set_activedir(0)

player.on(['/scene'], change_scene)

# Bind Keypad
player.on(['keypad-left'], 		lambda ev: play_firstdir(0))
player.on(['keypad-up'], 		lambda ev: play_firstdir(1))
player.on(['keypad-down'], 		lambda ev: play_firstdir(2))
player.on(['keypad-right'], 	lambda ev: play_firstdir(3))
player.on(['keypad-select'], 	lambda ev: broadcast('/stop'))

# Bind Keyboard
player.on(['KEY_KP0-down'], 	lambda ev: set_activedir(0))
player.on(['KEY_KP1-down'], 	lambda ev: set_activedir(1))
player.on(['KEY_KP2-down'], 	lambda ev: set_activedir(2))
player.on(['KEY_KP3-down'], 	lambda ev: set_activedir(3))
player.on(['KEY_KP4-down'], 	lambda ev: set_activedir(4))
player.on(['KEY_KP5-down'], 	lambda ev: set_activedir(5))
player.on(['KEY_KP6-down'], 	lambda ev: set_activedir(6))
player.on(['KEY_KP7-down'], 	lambda ev: set_activedir(7))
player.on(['KEY_KP8-down'], 	lambda ev: set_activedir(8))
player.on(['KEY_KP9-down'], 	lambda ev: set_activedir(9))
player.on(['KEY_KPDOT-down'], 	lambda ev: sel_lastdir())
player.on(['KEY_KPENTER-down'], lambda ev: broadcast('/stop'))
player.on(['KEY_KPPLUS-down', 'KEY_KPPLUS-hold'], 	vol_inc)
player.on(['KEY_KPMINUS-down', 'KEY_KPMINUS-hold'], vol_dec)

# Bind HTTP remotes + Keyboard
player.on(['btn1', 'KEY_NUMLOCK-down'], 		lambda ev: play_activedir(0))
player.on(['btn2', 'KEY_KPSLASH-down'], 		lambda ev: play_activedir(1))
player.on(['btn3', 'KEY_KPASTERISK-down'], 		lambda ev: play_activedir(2))
player.on(['btn4', 'KEY_BACKSPACE-down'], 		lambda ev: play_activedir(3))
player.on(['inc'], 			remote_inc)
player.on(['dec'], 			remote_dec)
player.on(['push'], 		switch_mode)



# OSC synctest request from ESP remotes
def syncTest(arg, **kwargs):
	if remote_mode:
		#SCENE
		display = available_dir[active_dir].replace("scene ", "S.")[:5].ljust(5) + " "

		# MEDIA
		media = player.status()['media']
		for i in range(4):
			# if i == player.status()['index'] and media.startswith(current_dir()): display += str(i+1)
			if i < active_dir_length: display += '-'
			else : display += '.'

		display += "#"
		if not player.status()['media']: display += '-stop-'
		else: display += media[:-4].replace(base_path, '').replace("/scene ", "S.").replace("/", " / ")

	else:
		# VOLUME
		vol = player.settings()['volume']
		display = "VOLUME "
		display += str(vol).rjust(3)
		# PEERS
		display += "#Dispositifs".ljust(19)+str(player.getInterface('zyre').activeCount()).rjust(2)

	#print('synctest', display)
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
	lines[1] = lines[1].ljust(14, ' ')[:14]
	lines[1] += str(player.getInterface('zyre').activeCount()).rjust(2, ' ')[:2]

	return lines

if is_RPi:
	player.getInterface('keypad').update = types.MethodType(lcd_update, player.getInterface('keypad'))




# RUN
# hplayer.setBasePath(["/mnt/usb"])        	# Media base path
hplayer.run()                               # TODO: non blocking
