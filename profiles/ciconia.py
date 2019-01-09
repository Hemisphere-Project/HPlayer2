from core.engine import hplayer
from core.engine import network
import os

remote_ip = "3.0.0.255"

# PLAYER
player = hplayer.addplayer('mpv', 'ciconia')
player.loop(0)

# Interfaces
player.addInterface('osc', 4000, 4001)
player.addInterface('http', 8037)
player.addInterface('http2', 8080)
player.addInterface('keypad')

# Bind Keypad events
player.on(['keypad-up'], player.volume_inc)
player.on(['keypad-down'], player.volume_dec)
player.on(['keypad-right'], player.next)
player.on(['keypad-left'], player.prev)
player.on(['keypad-select'], player.stop)

# Synctest for ESP Remotes
def syncTest(arg):
	if player.status()['media'] is not None:
		display = os.path.basename(player.status()['media'])[:-4]
		if player.status()['time'] is not None:
			display += "  \"" + str(int(player.status()['time']))
	else:
		display = "-stop-"

	player.getInterface('osc').hostOut = remote_ip
	player.getInterface('osc').send(display)


player.on(['/synctest'], syncTest)



# RUN
hplayer.setBasePath(["/data/media", "/mnt/usb"])        # Media base path
hplayer.run()                               # TODO: non blocking
