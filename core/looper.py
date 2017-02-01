from engine import hplayer
from engine import network

from time import sleep
import os, socket

if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'looper')

    def playloop():
		print("No Media... Retrying")
		sleep(1)
		player.play('*')

    # INTERNAL events
    player.on(['app-run', 'nomedia'], playloop)

    # RUN
    sleep(0.1)

    hplayer.setBasePath(["/media/usb", "/kxkm/media"])
    hplayer.run()                               # TODO: non blocking
