from core.engine import hplayer
from core.engine import network
import os, platform

# NAME
playerName = network.get_hostname()

# PLAYER
player = hplayer.addplayer('mpv', playerName)

# INTERFACES
player.addInterface('http2', 8080)
player.addInterface('osc', 1222, 3737)
player.addInterface('keypad')
player.addInterface('keyboard').asIRremote()

#
## HPOD (Régie Max)
#

is_RPi = platform.machine().startswith('armv')
regie_ip = None

# Overlay
if is_RPi:
    player.addOverlay('rpifade')

# OSC events
def syncTest():
    loop = "loop" if player.settings()['loop'] else "unloop"
    screen = "screen" if not player.settings()['flip'] else "screenflip"
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


# Touch OSC multiPAD
def on_event(event, args):
    # print('YO', event, args)
    if event.startswith('/1/multipush1') and args[0] == 1.0:
        e = event.split('/')
        x = int(e[4])-1
        y = 4-int(e[3])
        i = y*4+x
        player.play(i)
        print('trig ', i)
player.on(['*'], on_event)

# RUN
hplayer.setBasePath(["/data/media", "/mnt/usb"])        # Media base path
hplayer.persistentSettings("/data/hplayer2-kxkm.cfg")   # Path to persitent config
hplayer.run()
