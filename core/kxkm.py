from engine import hplayer
from engine import network

from time import sleep
import os, socket

if __name__ == '__main__':

    # PLAYER
    player = hplayer.addplayer('mpv', 'ipod2')

    # Interfaces
    player.addInterface('osc', [1222, 3737])

    # Overlay
    player.addOverlay('rpifader')

    # KXKM
    playerName = socket.gethostname()
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
            player.getInterface('osc').hostOut = network.get_broadcast('eth0')
    	player.getInterface('osc').send(playerName, 'auto', loop, screen, playing, media)

    def fullSyncTest():
        if not regie_ip:
            player.getInterface('osc').hostOut = network.get_broadcast('eth0')
    	player.getInterface('osc').send(playerName, 'initinfo', network.get_ip('eth0'))

    def setIpRegie(args):
        global regie_ip
        regie_ip = args[0]
        player.getInterface('osc').hostOut = regie_ip

    def fadeColor(args=None):
        if args and len(args) == 3:
            player.getOverlay('rpifader').set(args[0]/255.0, args[1]/255.0, args[2]/255.0, 1.0)
        elif args and len(args) == 4:
            player.getOverlay('rpifader').set(args[0]/255.0, args[1]/255.0, args[2]/255.0, args[3]/255.0)
        else:
            player.getOverlay('rpifader').set(1.0, 1.0, 1.0, 1.0)

    def unfadeColor():
        player.getOverlay('rpifader').set(alpha=0.0)

    def playmovie(args=None):
        player.play( args[0] ) if args else player.play()


    player.on(['/synctest'],    syncTest)
    player.on(['/fullsynctest'], fullSyncTest)
    player.on(['/ipregie'],     setIpRegie)

    player.on(['/playmovie'],   playmovie)
    player.on(['/loadmovie'],   lambda args: player.load(args[0]))
    player.on(['/attime'],      lambda args: player.seekTo(args[0]))
    player.on(['/stopmovie'],   player.stop)
    player.on(['/unpause'],     player.resume)

    player.on(['/fade'],        fadeColor)
    player.on(['/unfade'],      unfadeColor)

    # RUN
    sleep(0.1)

    hplayer.setBasePath(["/media/usb", "/kxkm/media"])
    hplayer.run()                               # TODO: non blocking
