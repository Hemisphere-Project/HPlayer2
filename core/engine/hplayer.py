from __future__ import print_function
from . import network
import core.players as playerlib
import core.interfaces as ifacelib
from core.engine.filemanager import FileManager
from core.engine.playlist import Playlist
from core.engine.settings import Settings

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


class HPlayer2(EventEmitter):

    def __init__(self, basepath=None, settingspath=None):
        super().__init__(wildcard=True, delimiter=".")
        self.nameP = colored('HPlayer2', 'green')

        self._lastUsedPlayer = 0

        self._players       = OrderedDict()
        self._interfaces    = OrderedDict()

        self.settings       = Settings(self, settingspath)
        self.files          = FileManager(self, basepath)
        self.playlist       = Playlist(self)

        self.autoBind(self.settings)
        self.autoBind(self.files)
        self.autoBind(self.playlist)


    def log(self, *argv):
        print(self.nameP, *argv)

    @staticmethod
    def isRPi():
        return platform.machine().startswith('armv')

    @staticmethod
    def name():
        return network.get_hostname()

    #
    # PLAYERS
    #

    def addPlayer(self, ptype, name=None):
        if not name: name = ptype+str(len(self._players))
        if name and name in self._players:
            print("player", name, "already exists")
        else:
            PlayerClass = playerlib.getPlayer(ptype)
            p = PlayerClass(self, name)
            self._players[name] = p

            # Bind settings
            self.settings.on('do-volume',       p._applyVolume)
            self.settings.on('do-mute',         p._applyVolume)
            self.settings.on('do-pan',          p._applyPan)
            self.settings.on('do-audiomode',    p._applyPan)
            self.settings.on('do-flip',         p._applyFlip)

            # Bind playlist
            p.on('end',                         self.playlist.onMediaEnd)    # Media end    -> Playlist next
            self.playlist.on('end',             p.stop)                      # Playlist end -> Stop player

            # Bind status (player update triggers hplayer emit)
            @p.on('status')
            def emitStatus(*args):
                self.emit('status', self.status())

            self.emit('player-added', p)

        return self._players[name]


    def player(self, name):
        if name not in self._players:
            print("player", name, "not found")
        return self._players[name]


    def players(self):
        return list(self._players.values())


    def activePlayer(self):
        return self.players()[self._lastUsedPlayer]

    def status(self):
        return [p.status() for p in self.players()]


    #
    # INTERFACES
    #

    def addInterface(self, iface, *argv):
        InterfaceClass = ifacelib.getInterface(iface)
        self._interfaces[iface] = InterfaceClass(self, *argv)
        self.autoBind(self._interfaces[iface])
        return self._interfaces[iface]


    def interface(self, name):
        if name in self._interfaces.keys():
            return self._interfaces[name]
        return None

    def interfaces(self):
        return self._interfaces.values()


    #
    # RUN
    #

    def running(self):
        run = True
        for p in self.players():
            run = run and p.isRunning()
        for iface in self.interfaces():
            run = run and iface.isRunning()
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
        self.log()
        self.log("is closing..")
        self.emit('app-closing')
        for p in self.players():
            p.quit()
        for iface in self.interfaces():
            iface.quit()

        os.system('ps faux | pgrep mpv | xargs kill')
        self.log("stopped. Goodbye !\n");
        self.emit('app-quit')
        sys.exit(0)


    #
    # BINDINGS
    #

    def autoBind(self, module):
        
        # SYSTEM
        #
        @module.on('hardreset')
        def hardreset(*args):
            os.system('systemctl restart NetworkManager')
            global runningFlag
            runningFlag = False


        # PLAYLIST
        #

        @module.on('play')
        def play(*args):
            if len(args) > 1:
                self.playlist.play(args[0], int(args[1]))
            elif len(args) > 0:
                self.playlist.play(args[0])
            else:
                self.playlist.play()

        @module.on('playonce')
        def playonce(*args):
            if len(args) > 0:
                loop(0)
                play(*args)

        @module.on('playloop')
        def playloop(*args):
            if len(args) > 0:
                loop(2)
                play(*args)

        @module.on('load')
        def load(*args):
            if len(args) > 0:
                self.playlist.load(args[0])
        
        @module.on('playindex')
        def playindex(*args):
            if len(args) > 0:
                self.playlist.playindex(int(args[0]))

        @module.on('add')
        def add(*args):
            if len(args) > 0:
                self.playlist.add(args[0])

        @module.on('remove')   #index !
        def remove(*args):
            if len(args) > 0:
                self.playlist.remove(args[0])

        @module.on('clear')
        def clear(*args):
            self.playlist.clear()

        @module.on('next')
        def next(*args):
            self.playlist.next()

        @module.on('prev')
        def prev(*args):
            self.playlist.prev()


        # PLAYERS
        #

        @module.on('do-play')
        def doplay(*args):
            for i,p in enumerate(self.players()): 
                if p.validExt(args[0]):
                    if i != self._lastUsedPlayer:
                        self.activePlayer().stop()
                    p.play(args[0])
                    self._lastUsedPlayer = i
                    return

        @module.on('stop')
        def stop(*args):
            # TODO : double stop -> reset playlist index (-1)
            for p in self.players():
                p.stop()

        @module.on('pause')
        def pause(*args):
            for p in self.players(): 
                if p.isPlaying():
                    p.pause()

        @module.on('resume')
        def resume(*args):
            for p in self.players(): 
                if p.isPlaying():
                    p.resume()

        @module.on('seek')
        def seek(*args):
            if len(args) > 0:
                for p in self.players(): 
                    if p.isPlaying():
                        p.seekTo(int(args[0]))

        @module.on('skip')
        def skip(*args):
            if len(args) > 0:
                for p in self.players(): 
                    if p.isPlaying():
                        p.skip(int(args[0]))
                

        # SETTINGS
        #

        @module.on('loop')
        def loop(*args):
            doLoop = 2
            if len(args) > 0:
                doLoop = int(args[0])
            self.settings.set('loop', doLoop)

        @module.on('unloop')
        def unloop(*args):
            self.settings.set('loop', 0)

        @module.on('volume')
        def volume(*args):
            if len(args) > 0:
                vol = int(args[0])
                if (vol < 0): vol = 0
                if (vol > 100): vol = 100
                self.settings.set('volume', vol)

        @module.on('mute')
        def mute(*args):
            doMute = True
            if len(args) > 0:
                doMute = int(args[0]) > 0
            self.settings.set('mute', doMute)

        @module.on('unmute')
        def unmute(*args):
            self.settings.set('mute', False)

        @module.on('pan')
        def pan(*args):
            if len(args) > 1:
                self.settings.set('pan', [int(args[0]),int(args[1])])
        
        @module.on('flip')
        def flip(*args):
            doFlip = True
            if len(args) > 0:
                doFlip = int(args[0]) > 0
            self.settings.set('flip', doFlip)

        @module.on('fade')
        def fade(*args):
            if len(args) > 3:
                self.players()[0].getOverlay('rpifade').set(float(args[0]),float(args[1]), float(args[2]), float(args[3]))
            else:
                self.players()[0].getOverlay('rpifade').set(0.0, 0.0, 0.0, 1.0)

        @module.on('unfade')
        def unfade(*args):
            self.players()[0].getOverlay('rpifade').set(0.0, 0.0, 0.0, 0.0)

        @module.on('unflip')
        def unflip(*args):
            self.settings.set('flip', False)

        @module.on('autoplay')
        def autoplay(*args):
            doAP = True
            if len(args) > 0:
                doAP = int(args[0]) > 0
            self.settings.set('autoplay', doAP)

        @module.on('notautoplay')
        def notautoplay(*args):
            self.settings.set('autoplay', False)