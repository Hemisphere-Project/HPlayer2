from core.engine import hplayer
from core.engine import network
import os

regie_ip = "3.0.0.10"

# PLAYER
player = hplayer.addplayer('mpv', 'ciconia')
player.loop(False)

# Interfaces
player.addInterface('osc', 4000, 4001)
player.addInterface('http', 8037)
player.addInterface('keypad')


def syncTest():
	if player.status()['media'] is not None:
		display = os.path.basename(player.status()['media'])[:-4]
		if player.status()['time'] is not None:
			display += "  \"" + str(int(player.status()['time']))
	else:
		display = "-stop-"

	player.getInterface('osc').hostOut = regie_ip
	player.getInterface('osc').send(display)
	print(display)


player.on(['/synctest'], syncTest)



# RUN
hplayer.setBasePath("/mnt/usb")
hplayer.run()                               # TODO: non blocking
