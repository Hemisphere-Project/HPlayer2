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


def CreatePlayer(name, player):
    if name in players:
        print(nameP,"player",name,"already exists")
    else:
        players[name] = PlayerAbstract(name=name, player=player)

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
    CreatePlayer(name='j0nny', player='mpv')
    Player('j0nny').addInterface('osc', [oscPortIN, oscPortOUT])

    # Add PLAYER
    CreatePlayer(name='r4ymond', player='mpv')
    Player('r4ymond').addInterface('osc', [oscPortIN+100, oscPortOUT+100])

    # RUN
    while isRunning():
        time.sleep(1)

    # STOP
    print('\n'+nameP,"is closing..")
    for p in Players():
        p.quit()

    print(nameP,"stopped. Goodbye !\n");
    sys.exit(0)
