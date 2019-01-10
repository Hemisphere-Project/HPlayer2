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


# Broadcast Order on OSC
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


# Answer to Synctest request (ESP remotes)
def syncTest(arg):
	if player.status()['media'] is not None:
		display = os.path.basename(player.status()['media'])[:-4]
		if player.status()['time'] is not None:
			display += "  \"" + str(int(player.status()['time']))
	else:
		display = "-stop-"
	player.getInterface('osc').send(display)

player.on(['/synctest'], syncTest)




# RUN
hplayer.setBasePath(["/mnt/usb"])        # Media base path
hplayer.run()                               # TODO: non blocking
