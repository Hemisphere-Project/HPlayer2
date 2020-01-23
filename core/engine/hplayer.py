from __future__ import print_function
from . import network
import core.players as playerlib
import core.interfaces as ifacelib

from collections import OrderedDict
from termcolor import colored
from time import sleep
import signal
import sys, os, platform
from pymitter import EventEmitter


runningFlag = True

# CTR-C Handler
def signal_handler(signal, frame):
        print ('\n'+colored('[SIGINT] You pressed Ctrl+C!', 'yellow'))
        global runningFlag
        runningFlag = False
signal.signal(signal.SIGINT, signal_handler)


class Hplayer(EventEmitter):

    def __init__(self, roots=None):
        super().__init__(wildcard=True, delimiter=".")
        self.nameP = colored('HPlayer2', 'green')

        self._players = OrderedDict()
        self._interfaces = {}

        self._lastPlayer = 0


    def log(self, *argv):
        print(self.nameP, *argv)


    def isRPi(self):
        return platform.machine().startswith('armv')    


    def addPlayer(self, ptype, name=None):
        # if not name:
        #     name = network.get_hostname()
        if name and name in self._players:
            print("player", name, "already exists")
        else:
            PlayerClass = playerlib.getPlayer(ptype)
            p = PlayerClass(name)
            self._players[p.name] = p
        return self._players[p.name]


    def player(self, name):
        if name not in self._players:
            print("player", name, "not found")
        return self._players[name]


    def players(self):
        return self._players.values()


    def addInterface(self, ifacename, *argv):
        InterfaceClass = ifacelib.getInterface(ifacename)
        self._interfaces[ifacename] = InterfaceClass(self, *argv)
        self.autoBind(self._interfaces[ifacename])
        return self._interfaces[ifacename]


    def interface(self, name):
        if name in self._interfaces.keys():
            return self._interfaces[name]
        return None

    def interfaces(self):
        return self._interfaces.values()

    def setBasePath(self, bpath):
        self.log("set basepath:", bpath);
        for p in self.players():
            p.setBasePath(bpath)


    def persistentSettings(self, spath):
        self.log("settings:", spath);
        for p in self.players():
            p.persistentSettings(spath)


    def running(self):
        run = True
        for p in self.players():
            run = run and p.isRunning()
        for iface in self.interfaces():
            run = run and iface.isRunning():
        return run
        

    def run(self):

        sleep(0.1)

        try:
            if network.get_ip("eth0") != "127.0.0.1":
                self.log("IP for eth0 is", network.get_ip("eth0"));
            if network.get_ip("wlan0") != "127.0.0.1":
                self.log("IP for wlan0  is", network.get_ip("wlan0"));
        except:
            pass

        self.log("started.. Welcome ! \n");

        sys.stdout.flush()

        # START players
        for p in self.players():
            p.start()

        # START interfaces
        for iface in self.interfaces():
            iface.start()

        self.emit('app-run')

        while runningFlag and self.running():
            sys.stdout.flush()
            sleep(0.5)

        # STOP
        print('\n' + nameP, "is closing..")
        for p in self.players():
            p.quit()
        for iface in self.interfaces():
            iface.quit()

        self.log("stopped. Goodbye !\n");
        sys.exit(0)


    def autoBind(self, iface):
        
        @iface.on('play')
        def play(*args):
            if len(args) > 0:
                # MOVE playlist managment from player to hplayer !!
                # SCAN extension and decide
                pass
            else:
                # if self._lastPlayer < len(self.players()):
                #     self.players()[self._lastPlayer].play()
                pass
        
        @iface.on('playindex')
        def playindex(*args):
            if len(args) > 0:
                # MOVE playlist managment from player to hplayer !!
                # SCAN extension and decide
                pass

        @iface.on('playlist')
        def playlist(*args):
            if len(args) > 0:
                # MOVE playlist managment from player to hplayer !!
                # SCAN extension and decide
                pass

        @iface.on('next')
        def nex(*args):
            # MOVE playlist managment from player to hplayer !!
            # SCAN extension and decide
            pass

        @iface.on('prev')
        def prev(*args):
            # MOVE playlist managment from player to hplayer !!
            # SCAN extension and decide
            pass

        @iface.on('stop')
        def stop(*args):
            for p in self.players(): 
                p.stop()

        @iface.on('pause')
        def pause(*args):
            for p in self.players(): 
                p.pause()

        @iface.on('resume')
        def resume(*args):
            for p in self.players(): 
                p.resume()

        @iface.on('loop')
        def loop(*args):
            if len(args) > 0:
                for p in self.players(): 
                    p.loop(int(args[0]))

        @iface.on('unloop')
        def unloop(*args):
            for p in self.players(): 
                p.loop(0)

        @iface.on('volume')
        def volume(*args):
            if len(args) > 0:
                for p in self.players(): 
                    p.volume(int(args[0]))

        @iface.on('mute')
        def mute(*args):
            for p in self.players(): 
                p.mute(True)

        @iface.on('unmute')
        def unmute(*args):
            for p in self.players(): 
                p.mute(False)

        @iface.on('pan')
        def pan(*args):
            if len(args) > 1:
                for p in self.players(): 
                    p.pan(int(args[0]),int(args[1]))
        
        @iface.on('flip')
        def flip(*args):
            for p in self.players(): 
                p.flip(True)

        @iface.on('unflip')
        def unflip(*args):
            for p in self.players(): 
                p.flip(False)