from engine import hplayer
from engine import network

from time import sleep
import os, socket

if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'audioscope')
    player.loop(True)                       
    player.log['events'] = True

    # Interfaces
    player.addInterface('osc', [1222, 3737])
    player.addInterface('http', [8080])
    player.addInterface('nfc', [0.5])

    # HTTP + GPIO events
    player.on(['nfc-card'], lambda args: player.play(args[0]['uid']+"-*.*"))
    player.on(['nfc-nocard'], player.stop)

    # RUN
    sleep(0.1)

    hplayer.setBasePath(["/media/usb", "/hmsphr/media"])
    hplayer.run()                               # TODO: non blocking
