from __future__ import print_function
import time, signal, sys
from termcolor import colored

from player import PlayerAbstract

oscPortIN = 4000
oscPortOUT = 4001

runningFlag = True

players = {}

# CTR-C Handler
def signal_handler(signal, frame):
        print ('\n'+colored('[SIGINT] You pressed Ctrl+C!','yellow'))
        global runningFlag
        runningFlag = False
signal.signal(signal.SIGINT, signal_handler)


def CreatePlayer(name, player, basepath):
    if name in players:
        print(nameP,"player",name,"already exists")
    else:
        players[name] = PlayerAbstract(name=name, player=player, basepath=basepath)
    return players[name]

def Player(name):
    if name not in players:
        print(nameP,"player",name,"not found")
    return players[name]

def Players():
    return players.values()

def isRunning():
    isRunning = runningFlag
    for n,p in players.items():
        isRunning = isRunning and p.isRunning()
    return isRunning


if __name__ == '__main__':

    name = "HPlayer2"
    nameP = colored(name,'green')
    print('\n'+nameP,"started. Welcome !");

    # Add PLAYER
    player = CreatePlayer(name='j0nny', player='mpv', basepath='/media/usb/')
    player.addInterface('osc', [oscPortIN, oscPortOUT])
    player.addInterface('http')

    # GADAGNE logic
    #defaultFile = 'cut.mp4'
    fails = True
    defaultFile = '2015-11-01-ink.mp4'
    #push1File = '2015-09-04-smoke.mp4'
    push1File = 'cut.mp4'
    push2File = 'cut2.mp4'
    push3File = 'cut3.mp4'

    player.on('end', lambda: Player('j0nny').play(defaultFile) )
    player.on('push1', lambda: Player('j0nny').play(push1File) )
    player.on('push2', lambda: Player('j0nny').play(push2File) )
    player.on('push3', lambda: Player('j0nny').play(push3File) )

    player.on('gpio24', lambda: Player('j0nny').play(push1File) )

    # RUN
    while isRunning():

        # GADAGNE logic
        if Player('j0nny').isPlaying(): fails=False
        elif fails: Player('j0nny').play(defaultFile)
        else: fails=True

        time.sleep(1)

    # STOP
    print('\n'+nameP,"is closing..")
    for p in Players():
        p.quit()

    print(nameP,"stopped. Goodbye !\n");
    sys.exit(0)
