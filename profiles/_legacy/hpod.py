from core.engine import hplayer
from core.engine import network
import os, platform

# KXKM
playerName = network.get_hostname()
is_RPi = platform.machine().startswith('armv')
regie_ip = None

# PLAYER
player = hplayer.addplayer('mpv', playerName)

# Interfaces
player.addInterface('osc', 1222, 3737)

# Overlay
if is_RPi:
    player.addOverlay('rpifade')

# OSC events
def syncTest():
    loop = "loop" if player.status()['loop'] else "unloop"
    screen = "screen" if not player.status()['flip'] else "screenflip"
    playing = "playmovie" if player.isPlaying() else "stopmovie"
    media = player.status()['media']
    if media:
        media = os.path.basename(media)
    if not regie_ip:
        player.getInterface('osc').hostOut = network.get_broadcast()
    player.getInterface('osc').send(playerName, 'auto', loop, screen, playing, media)

def fullSyncTest():
    if not regie_ip:
        player.getInterface('osc').hostOut = network.get_broadcast()
    player.getInterface('osc').send(playerName, 'initinfo', network.get_ip())

def setIpRegie(args):
    global regie_ip
    regie_ip = args[0]
    player.getInterface('osc').hostOut = regie_ip

def fadeColor(args=None):
    if is_RPi:
        if args and len(args) == 3:
            player.getOverlay('rpifade').set(args[0]/255.0, args[1]/255.0, args[2]/255.0, 1.0)
        elif args and len(args) == 4:
            player.getOverlay('rpifade').set(args[0]/255.0, args[1]/255.0, args[2]/255.0, args[3]/255.0)
        else:
            player.getOverlay('rpifade').set(1.0, 1.0, 1.0, 1.0)

def unfadeColor():
    if is_RPi:
        player.getOverlay('rpifade').set(alpha=0.0)

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
hplayer.setBasePath(["/mnt/usb", "/data"])
hplayer.run()
