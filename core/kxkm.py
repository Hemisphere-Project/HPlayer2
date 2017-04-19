from engine import hplayer
from time import sleep
import os

from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
import netifaces as ni

def get_ip():
    ip = '127.0.0.1'
    try:
        ip = ni.ifaddresses('eth0')[AF_INET][0]['addr']
    except:
        pass
    return ip

def get_broadcast():
    ip = '127.0.0.1'
    try:
        ip = ni.ifaddresses('eth0')[AF_INET][0]['broadcast']
    except:
        pass
    return ip


if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'ipod2')

    # Interfaces
    player.addInterface('osc', [1222, 3737])

    # KXKM
    playerName = '/ipod2'
    regie_ip = None

    # OSC events
    def syncTest():
        loop = "loop" if player.status()['loop'] else "unloop"
        screen = "screen" if not player.status()['flip'] else "screenflip"
        playing = "playmovie" if player.isPlaying() else "stopmovie"
        media = player.status()['media']
        if media:
            media = os.path.basename(media)
        if not regie_ip:
            player.iface('osc').hostOut = get_broadcast()
    	player.iface('osc').send(playerName, 'auto', loop, screen, playing, media)

    def fullSyncTest():
        if not regie_ip:
            player.iface('osc').hostOut = get_broadcast()
    	player.iface('osc').send(playerName, 'initinfo', get_ip())

    def setIpRegie(args):
        global regie_ip
        regie_ip = args[0]
        player.iface('osc').hostOut = regie_ip

    player.on(['/synctest'],    syncTest)
    player.on(['/fullsynctest'], fullSyncTest)
    player.on(['/ipregie'],     setIpRegie)

    player.on(['/playmovie'],   lambda args: player.play(args[0]))
    player.on(['/loadmovie'],   lambda args: player.load(args[0]))
    player.on(['/attime'],      lambda args: player.seekTo(args[0]))
    player.on(['/stopmovie'],   player.stop)
    player.on(['/unpause'],     player.resume)

    # RUN
    sleep(0.1)
    print("Device IP: ", get_ip())

    hplayer.setBasePath("/home/pi/Videos/")
    hplayer.run()                               # TODO: non blocking
