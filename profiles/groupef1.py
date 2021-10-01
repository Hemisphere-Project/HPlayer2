from core.engine.hplayer import HPlayer2
from core.engine import network
import os, sys, types, platform
import statistics
from termcolor import colored

# DIRECTORY / FILE
profilename = os.path.basename(__file__).split('.')[0]
base_path = ['/data/sync/', '/data/usb']

hplayer = HPlayer2(base_path)

# PLAYERS
player     = hplayer.addPlayer('mpv','mpv')

# Interfaces
hplayer.addInterface('mtc', "Midi Through:Midi Through Port-0 14:0")

# No Loop, neither playlist
@hplayer.on('mpv.ready')
def f(ev, *args):
    hplayer.settings.set('loop', -1)


@hplayer.on('mpv.ready')
def f(ev, *args):
    hplayer.playlist.play('*')
    # player.pause()

lastSpeed = 1.0
lastPos = -1

@hplayer.on('mtc.qf')
def f(ev, *args):
    global lastSpeed, lastPos

    pos = player.position()

    # Check if player time is actually ellapsing
    if pos == lastPos or not player.isPlaying():
        # print("no news from player.. timecode tracker standing by")
        return
    lastPos = pos

    clock = round(args[0].float, 2)
    diff = clock-pos

    speed = 1.0

    # corrector
    fix = 0.04    # compensate mtc latency from clock to tc tracker (typically 1 frame on Ubuntu x64 using Alsa Midi:Thru)
    fix = 0

    #jump
    if abs(diff) > 1.0:
            player.seekTo(clock*1000)

    # accel
    elif (diff+fix) > 0.04 or (lastSpeed>1 and (diff+fix) > 0) :
        speed = round( 1+diff*2+fix, 2)
        speed = min(speed, 3.0)

    # decel
    elif (diff+fix) < -0.04 or (lastSpeed<1 and (diff+fix) < 0):
        speed = round( 1+ min(-0.1, diff*2+fix), 2)
        speed = max(speed, 0.1)
        
    color1 = 'green'
    if abs(diff) > 0.08: color1 = 'red'
    elif abs(diff) > 0.04: color1 = 'yellow'

    color2 = 'white'
    if speed > 1: color2 = 'magenta'
    elif speed < 1: color2 = 'cyan'

    print(args[0], clock, pos, "delay=", colored( round(diff,2),color1) , colored(speed, color2))
    
    player.speed(speed)
    lastSpeed = speed

# RUN
hplayer.run()                                                       # TODO: non blocking
