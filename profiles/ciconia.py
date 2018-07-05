from core.engine import hplayer
from core.engine import network
import os

regie_ip = "3.0.0.10"

# PLAYER
player = hplayer.addplayer('mpv', 'myPlayer')

# Interfaces
player.addInterface('osc', [4000,4001])
player.addInterface('http', [8037])
player.addInterface('keypad')

def syncTest():
	if player.isPlaying():
		media = os.path.basename(player.status()['media'])[:-4]
		media += "/\"" + str(int(player.status()['time']))
	else:
		media = "-stop-"
	player.getInterface('osc').hostOut = regie_ip
	player.getInterface('osc').send(media)


player.on(['/synctest'],  syncTest)

# RUN
hplayer.setBasePath("/mnt/usb/")
hplayer.run()                               # TODO: non blocking
