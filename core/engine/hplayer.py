from __future__ import print_function
from . import network
import core.players as playerlib
from termcolor import colored
from time import sleep
import signal
import sys, os

runningFlag = True
players_pool = {}


# CTR-C Handler
def signal_handler(signal, frame):
        print ('\n'+colored('[SIGINT] You pressed Ctrl+C!', 'yellow'))
        global runningFlag
        runningFlag = False
signal.signal(signal.SIGINT, signal_handler)


def setBasePath(bpath):
    print(colored('HPlayer2', 'green'), "basepath:", bpath);
    for p in players():
        p.setBasePath(bpath)

def persistentSettings(spath):
    print(colored('HPlayer2', 'green'), "settings:", spath);
    for p in players():
        p.persistentSettings(spath)

def addplayer(ptype, name=None):
    if name and name in players_pool:
        print("player", name, "already exists")
    else:
        PlayerClass = playerlib.getPlayer(ptype)
        p = PlayerClass(name)
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

    sleep(0.1)

    name = "HPlayer2"
    nameP = colored(name, 'green')

    try:
        if network.get_ip("eth0") != "127.0.0.1":
            print(nameP, "IP for eth0 is", network.get_ip("eth0"));
        if network.get_ip("wlan0") != "127.0.0.1":
            print(nameP, "IP for wlan0  is", network.get_ip("wlan0"));
    except:
        pass

    print(nameP, "started.. Welcome ! \n");

    sys.stdout.flush()

    # START players
    for p in players():
        p.start()
        p.trigger('app-run')

    while runningFlag and running():
        sys.stdout.flush()
        sleep(0.5)

    # STOP
    print('\n' + nameP, "is closing..")
    for p in players():
        p.quit()

    print(nameP, "stopped. Goodbye !\n");
    sys.exit(0)
