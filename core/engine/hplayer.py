from __future__ import print_function
from termcolor import colored
import players as playerlib
from time import sleep
import signal
import sys
import network

runningFlag = True
players_pool = {}
basepath = "~/media/"


# CTR-C Handler
def signal_handler(signal, frame):
        print ('\n'+colored('[SIGINT] You pressed Ctrl+C!', 'yellow'))
        global runningFlag
        runningFlag = False
signal.signal(signal.SIGINT, signal_handler)


def setBasePath(base):
    basepath = base
    for p in players():
        p.setBasePath(basepath)


def addplayer(ptype, name=None):
    if name and name in players_pool:
        print("player", name, "already exists")
    else:
        PlayerClass = playerlib.getPlayer(ptype)
        p = PlayerClass(name)
        p.setBasePath(basepath)
        players_pool[p.name] = p
    return players_pool[p.name]


def player(name):
    if name not in players:
        print("player", name, "not found")
    return players_pool[name]


def players():
    return players_pool.values()


def running():
    run = True
    for p in players():
        run = run and p.isRunning()
    return run


def run():


    name = "HPlayer2"
    nameP = colored(name, 'green')
    print('\n' + nameP, "started. Welcome !");
    print(nameP, "Device IP is", network.get_ip());

    while runningFlag and running():
        sleep(0.5)

    # STOP
    print('\n' + nameP, "is closing..")
    for p in players():
        p.quit()

    print(nameP, "stopped. Goodbye !\n");
    sys.exit(0)
