from engine import hplayer
from time import sleep

import socket
import fcntl
import struct

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])


if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'myPlayer')

    # Interfaces
    player.addInterface('osc', [4000, 4001])

    # KXKM
    playerName = 'ipod1'

    # OSC events
    def syncTest():
        loop = "loop" if player.status()['loop'] else "unloop"
        playing = "playmovie" if player.isPlaying() else "stopmovie"
    	player.iface('osc').send(playerName, 'auto', loop, 'screen', playing, player.status()['media'])

    def fullSyncTest():
    	player.iface('osc').send(playerName, 'initinfo', get_ip_address('wlan0'))

    def setIpRegie(args):
        player.iface('osc').hostOut = args[0]

    player.on(['/synctest'],    syncTest)
    player.on(['/fullsynctest'], fullSyncTest)
    player.on(['/ipregie'],     setIpRegie)

    player.on(['/playmovie'],   lambda args: player.play(args[0]))
    player.on(['/loadmovie'],   lambda args: player.load(args[0]))
    player.on(['/attime'],      lambda args: player.seekTo(args[0]))
    player.on(['/stopmovie'],   player.stop)
    player.on(['/unpause'],     player.resume)

    # RUN
    hplayer.setBasePath("/home/pi/Videos/")
    hplayer.run()                               # TODO: non blocking
