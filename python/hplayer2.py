from __future__ import print_function
import time, signal, sys
from termcolor import colored

from player import PlayerAbstract

oscPortIN = 4000
oscPortOUT = 4001

httpPort = 8080

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

    # PLAYER
    player = CreatePlayer(name='gadagne', player='mpv', basepath='/media/usb/')

    # Interfaces
    # player.addInterface('osc', [oscPortIN, oscPortOUT])
    player.addInterface('http', [httpPort])
    player.addInterface('gpio', [16,19,20,21,26])

    # GADAGNE logic
    fails = 100
    defaultFile = 'media0.mp4'
    push1File = 'media1.mp4'
    push2File = 'media2.mp4'
    push3File = 'media3.mp4'

    # Loop default file
    player.on('end', lambda: player.play(defaultFile) )

    # HTTP + GPIO events
    player.on(['push1', 'gpio20'], lambda: player.play(push1File) )
    player.on(['push2', 'gpio21'], lambda: player.play(push2File) )
    player.on(['push3', 'gpio26'], lambda: player.play(push3File) )


    # RUN
    while isRunning():

        # GADAGNE logic
        if player.isPlaying():
            fails=0
        elif fails>5:
            print(nameP,"reset to Default Video");
            player.play(defaultFile)
        else:
            fails+=1

        time.sleep(1)

    # STOP
    print('\n'+nameP,"is closing..")
    for p in Players():
        p.quit()

    print(nameP,"stopped. Goodbye !\n");
    sys.exit(0)
