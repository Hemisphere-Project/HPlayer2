from core.engine.hplayer import HPlayer2
from core.engine import network
import os, sys, types, platform
import statistics, math
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
didJump = False
jumpFix = 300       # compensate the latency of jump (300ms for RockPro64 on timecode jump I.E. looping)

@hplayer.on('mtc.qf')
def f(ev, *args):
    global lastSpeed, lastPos, didJump, jumpFix

    doLog = True

    pos = player.position()

    # Check if player time is actually ellapsing
    if pos == lastPos or not player.isPlaying():
        # if doLog:
        #     print(str(args[0]), end="\t")
        #     print("no news from player.. dropping timecode tracking on this frame")
        return
    lastPos = pos

    clock = round(args[0].float, 2)
    diff = clock-pos

    speed = 1.0

    # framebuffer corrector
    #fix = 0.04    # compensate mtc latency from clock to tc tracker (typically 1 frame on Ubuntu x64 using Alsa Midi:Thru)
    fix = 0

    #jump
    if diff > 10 or diff < -2:
        player.seekTo(clock*1000+jumpFix)
        didJump = True
        print(str(args[0]), end="\t")
        print("timedelay=" + colored(round(diff,2),"red"), end="\t")
        print("JumpFix", jumpFix)

    else:   

        # Jump correction
        if didJump:
            didJump = False
            # Correcting JumpFix is dangerous: might diverge on different jump position / media quality / ...
            # if abs(diff+fix) > 0.01:
            #     jumpFix += min( max(-300, (diff+fix)*1000), 300)
            #     print("corrected JumpFix", jumpFix)

        # accel
        if (diff+fix) > 0.033 or (lastSpeed>1 and (diff+fix) > 0) :
            speed = round( 1+(diff+fix)*1.65, 2)
            speed = min(speed, 4.2)

        # decel
        elif (diff+fix) < -0.033 or (lastSpeed<1 and (diff+fix) < 0):
            speed = round( 1+ min(-0.04, diff+fix), 2)
            speed = max(speed, 0.1)

    player.speed(speed)
    lastSpeed = speed

    # LOG
    if doLog:
        if speed != 1.0:
            color1 = 'green'
            if abs(diff+fix) > 0.08: color1 = 'red'
            elif abs(diff+fix) > 0.04: color1 = 'yellow'

            color2 = 'white'
            if speed > 1: color2 = 'magenta'
            elif speed < 1: color2 = 'cyan'


            framedelta = math.trunc(diff*1000/30)
            color3 = 'green'
            if abs(framedelta) > 1: color3 = 'red'
            elif abs(framedelta) > 0: color3 = 'yellow'

            print(str(args[0]), end="\t")
            # print(str(clock), end="\t")
            # print(str(pos), end="\t")
            print("timedelay=" + colored(round(diff,2),color1), end="\t")
            print("framedelta=" + colored(framedelta,color3), end="\t")
            print("speed=" + colored(speed, color2) )

    

# RUN
hplayer.run()                                                       # TODO: non blocking
