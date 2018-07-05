from core.engine import hplayer
from core.engine import network
import os

regie_ip = "3.0.0.10"

# PLAYER
player = hplayer.addplayer('mpv', 'myPlayer')

# Interfaces
player.addInterface('osc', [4000,4001])
player.addInterface('http', [8037])

def syncTest():
    print 'synctest'
    loop = "loop" if player.status()['loop'] else "unloop"
    screen = "screen" if not player.status()['flip'] else "screenflip"
    media = os.path.basename(player.status()['media']) if player.isPlaying() else "-stop-"
    player.getInterface('osc').hostOut = regie_ip
    player.getInterface('osc').send(media)
	

player.on(['/synctest'],  syncTest)
#player.on(['stop'], syncTest)

# RUN
hplayer.setBasePath("/mnt/usb/")
hplayer.run()                               # TODO: non blocking
