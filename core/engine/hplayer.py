from __future__ import print_function
from . import network
from ..module import Module
import core.players as playerlib
import core.interfaces as ifacelib
from core.engine.sampler import Sampler
from core.engine.filemanager import FileManager
from core.engine.playlist import Playlist
from core.engine.settings import Settings
from core.engine.imgen import ImGen

from collections import OrderedDict
from threading import Timer
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


class HPlayer2(Module):

    def __init__(self, basepath=None, settingspath=None):
        # super().__init__(wildcard=True, delimiter=".")
        super().__init__(None, 'HPlayer2', 'green')
        self.nameP = colored(('[HPlayer2]').ljust(10, ' ')+' ', 'green')

        self._lastUsedPlayer = 0

        self._players       = OrderedDict()
        self._samplers      = OrderedDict()
        self._interfaces    = OrderedDict()

        self.settings       = Settings(self)
        self.files          = FileManager(self)
        self.playlist       = Playlist(self)
        
        self.imgen          = ImGen(self)

        self.settings.load(settingspath)
        self.files.add(basepath)

        self.autoBind(self)
        self.logQuietEvents = ['status']


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

    def addPlayer(self, ptype, name):
        # if not name: name = ptype+str(len(self._players))
        if name and name in self._players:
            self.log("player", name, "already exists")
        else:
            PlayerClass = playerlib.getPlayer(ptype)
            p = PlayerClass(self, name)
            self._players[name] = p

            # Bind Volume
            @self.settings.on('do-volume')
            @self.settings.on('do-mute')
            def vol(ev, value, settings):
                p._applyVolume( settings['volume'] if not settings['mute'] else 0 )

            # Bind Pan
            @self.settings.on('do-pan')
            @self.settings.on('do-audiomode')
            def pan(ev, value, settings):
                p._applyPan( settings['pan'] if settings['audiomode'] != 'mono' else 'mono' )

            # Bind Flip
            @self.settings.on('do-flip')
            def flip(ev, value, settings):
                p._applyFlip( settings['flip'] )

            # Bind OneLoop
            @self.settings.on('do-loop')
            @self.playlist.on('updated')
            def loop(ev, value, settings=None):
                oneLoop = (self.settings.get('loop') == 1) or (self.settings.get('loop') == 2 and self.playlist.size() == 1)
                p._applyOneLoop( oneLoop )


            # Bind playlist
            p.on('media-end',        lambda ev, *args: self.playlist.onMediaEnd())    # Media end    -> Playlist next
            self.playlist.on('end',  lambda ev, *args: p.stop())                      # Playlist end -> Stop player

            # Bind status (player update triggers hplayer emit)
            @p.on('status')
            def emitStatus(ev, *args):
                self.emit('status', self.statusPlayers())

            # Bind hardreset
            @p.on('hardreset')
            def reset(ev, *args):
                self.log('HARD KILL FROM PLAYER')
                os.system('pkill mpv')
                os._exit(0)

            self.emit('player-added', p)

        return self._players[name]


    def player(self, name):
        if name not in self._players:
            self.log("player", name, "not found")
        return self._players[name]

    def players(self):
        return list(self._players.values())

    def activePlayer(self):
        return self.players()[self._lastUsedPlayer]

    def statusPlayers(self):
        return [p.status() for p in self.players()]


    #
    # SAMPLER
    #

    def addSampler(self, ptype, name, poly=4):
        if name and name in self._samplers:
            self.log("sampler", name, "already exists")
        else:
            s = Sampler(self, ptype, poly)
            self._samplers[name] = s

            # Bind Volume
            # @self.settings.on('do-volume')
            # @self.settings.on('do-mute')
            # def vol(ev, value, settings):
            #     s.volume( settings['volume'] if not settings['mute'] else 0 )

            # # Bind Pan
            # @self.settings.on('do-pan')
            # @self.settings.on('do-audiomode')
            # def pan(ev, value, settings):
            #     s.pan( settings['pan'] if settings['audiomode'] != 'mono' else 'mono' )

            # # Bind Flip
            # @self.settings.on('do-flip')
            # def flip(ev, value, settings):
            #     s.flip( settings['flip'] )

            # Bind OneLoop
            # @self.settings.on('do-loop')
            # def loop(ev, value, settings):
            #     s.oneloop( settings['loop'] == 1 )

            # Bind status (player update triggers hplayer emit)
            @s.on('status')
            def emitStatus(ev, *args):
                self.emit('status', self.statusSamplers())

            # Bind hardreset
            @s.on('hardreset')
            def reset(ev, *args):
                self.log('HARD KILL FROM PLAYER')
                os.system('pkill mpv')
                os._exit(0)

            self.emit('sampler-added', s)

        return self._samplers[name]


    def sampler(self, name):
        if name not in self._samplers:
            self.log("sampler", name, "not found")
        return self._samplers[name]

    def samplers(self):
        return list(self._samplers.values())

    def statusSamplers(self):
        return [p.status() for p in self.samplers()]


    #
    # INTERFACES
    #

    def addInterface(self, iface, *argv):
        InterfaceClass = ifacelib.getInterface(iface)
        self._interfaces[iface] = InterfaceClass(self, *argv)
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

        # START samplers
        for s in self.samplers():
            s.start()

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
        for s in self.samplers():
            s.quit()
        for iface in self.interfaces():
            iface.quit()

        # os.system('ps faux | pgrep mpv | xargs kill')
        self.emit('app-quit')
        self.log("stopped. Goodbye !\n");
        # sys.exit(0)
        os._exit(0)


    #
    # BINDINGS
    #

    def autoBind(self, module):
        
        # SYSTEM
        #
        @module.on('hardreset')
        def hardreset(ev, *args): 
            os.system('systemctl restart NetworkManager')
            # global runningFlag
            # runningFlag = False
            # sleep(5.0)
            # sleep(1.0)
            self.log('HARD KILL')
            os._exit(0)

        @module.on('do-audioout')
        def doaudioout(ev, *args):
            if len(args) > 0:
                if args[0] == 'hdmi':
                    os.system('amixer cset numid=3 2')
                elif args[0] == 'jack':
                    os.system('amixer cset numid=3 1')

        # PLAYLIST
        #

        @module.on('play')
        @module.on('playpause')
        def play(ev, *args):
            pause = ev.startswith('playpause')
            if len(args) > 1:
                self.playlist.play(args[0], int(args[1]), pause=pause)
            elif len(args) > 0:
                self.playlist.play(args[0], pause=pause)
            else:
                self.playlist.play(pause=pause)

        @module.on('playonce')
        @module.on('playpauseonce')
        def playonce(ev, *args):
            if len(args) > 0:
                loop(ev, 0)
                play(ev, *args)

        @module.on('playloop')
        @module.on('playpauseloop')
        def playloop(ev, *args):
            if len(args) > 0:
                loop(ev, 2)
                play(ev, *args)
        
        @module.on('playindex')
        @module.on('playpauseindex')
        def playindex(ev, *args):
            if len(args) > 0:
                self.playlist.playindex(int(args[0]), ev.startswith('playpause'))
                
        # Play a list then trigger an event on media-end
        @module.on('playthen')
        @module.on('playpausethen')
        def playthen(ev, *args):
            if len(args) > 1:
                self.playlist.playthen(args[0], args[1], ev.startswith('playpause'))
            elif len(args) > 0:
                self.playlist.playthen(args[0], None, ev.startswith('playpause'))

        # Generate and display text as image
        @module.on('playtext')
        @module.on('playpausetext')
        def playtext(ev, *args):
            file = self.imgen.txt2img(*args)
            self.playlist.play(file, pause=pause)
            self.settings.set('loop', 1)
            
        @module.on('load')
        def load(ev, *args):
            if len(args) > 0:
                self.playlist.load(args[0])

        @module.on('add')
        def add(ev, *args):
            if len(args) > 0:
                self.playlist.add(args[0])

        @module.on('remove')   #index !
        def remove(ev, *args):
            if len(args) > 0:
                self.playlist.remove(args[0])

        @module.on('clear')
        def clear(ev, *args):
            self.playlist.clear()

        @module.on('next')
        def next(ev, *args):
            self.playlist.next()

        @module.on('prev')
        def prev(ev, *args):
            self.playlist.prev()


        # PLAYERS
        #

        @module.on('do-play')
        def doplay(ev, *args):
            for i,p in enumerate(self.players()): 
                if p.validExt(args[0]):
                    if i != self._lastUsedPlayer:
                        self.activePlayer().stop()
                    pause = args[2] if len(args) > 2 else False
                    p.play(args[0], pause)
                    self._lastUsedPlayer = i
                    return

        @module.on('stop')
        def stop(ev, *args):
            # TODO : double stop -> reset playlist index (-1)
            for p in self.players():
                resetPlaylist = not p.isPlaying()
                p.stop()
                if resetPlaylist:
                    self.playlist.rearm()

        @module.on('pause')
        def pause(ev, *args):
            for p in self.players(): 
                if p.isPlaying():
                    p.pause()

        @module.on('resume')
        @module.on('resumesync')
        def resume(ev, *args):
            for p in self.players(): 
                if p.isPlaying() or ev.startswith('resumesync'):
                    p.resume()

        @module.on('seek')
        def seek(ev, *args):
            if len(args) > 0:
                for p in self.players(): 
                    if p.isPlaying():
                        p.seekTo(int(args[0]))

        @module.on('skip')
        def skip(ev, *args):
            if len(args) > 0:
                for p in self.players(): 
                    if p.isPlaying():
                        p.skip(int(args[0]))
                

        # REGIE
        #
        
        @module.on('do-playseq')
        def doplayseq(ev, *args):
            if len(args) > 1 and self.interface('regie'):
                self.interface('regie').playseq(args[0], args[1])
        
        # SETTINGS
        #

        @module.on('loop')
        def loop(ev, *args):
            doLoop = 2
            if len(args) > 0:
                doLoop = int(args[0])
            self.settings.set('loop', doLoop)

        @module.on('unloop')
        def unloop(ev, *args):
            self.settings.set('loop', 0)

        @module.on('volume')
        def volume(ev, *args):
            if len(args) > 0:
                vol = int(args[0])
                if (vol < 0): vol = 0
                if (vol > 100): vol = 100
                self.settings.set('volume', vol)

        @module.on('volinc')
        def volume(ev, *args):
            inc = 1
            if len(args) > 0:
                inc = int(args[0])
            vol = self.settings.get('volume') + inc
            if (vol > 100): vol = 100
            self.settings.set('volume', vol)

        @module.on('voldec')
        def volume(ev, *args):
            dec = 1
            if len(args) > 0:
                dec = int(args[0])
            vol = self.settings.get('volume') - dec
            if (vol < 0): vol = 0
            self.settings.set('volume', vol)


        @module.on('mute')
        def mute(ev, *args):
            doMute = True
            if len(args) > 0:
                doMute = int(args[0]) > 0
            self.settings.set('mute', doMute)

        @module.on('unmute')
        def unmute(ev, *args):
            self.settings.set('mute', False)

        @module.on('pan')
        def pan(ev, *args):
            if len(args) == 1:
                self.settings.set('pan', [int(args[0][0]),int(args[0][1])])
            elif len(args) > 1:
                self.settings.set('pan', [int(args[0]),int(args[1])])

        @module.on('audiomode')
        def audiomode(ev, *args):
            if len(args) > 0:
                self.settings.set('audiomode', args[0])

        @module.on('audioout')
        def audiomode(ev, *args):
            if len(args) > 0:
                self.settings.set('audioout', args[0])
        
        @module.on('flip')
        def flip(ev, *args):
            doFlip = True
            if len(args) > 0:
                doFlip = int(args[0]) > 0
            self.settings.set('flip', doFlip)

        @module.on('fade')
        def fade(ev, *args):
            if len(args) == 1 and args[0][0] == '#':
                color = tuple(int(args[0][i:i+2], 16)/255.0 for i in (1, 3, 5))
                self.players()[0].getOverlay('rpifade').set(color[0], color[1], color[2], 1.0)
            elif len(args) > 3:
                self.players()[0].getOverlay('rpifade').set(float(args[0]),float(args[1]), float(args[2]), float(args[3]))
            elif len(args) > 2:
                self.players()[0].getOverlay('rpifade').set(float(args[0]),float(args[1]), float(args[2]), 1.0)
            else:
                self.players()[0].getOverlay('rpifade').set(0.0, 0.0, 0.0, 1.0)

        @module.on('unfade')
        def unfade(ev, *args):
            self.players()[0].getOverlay('rpifade').set(0.0, 0.0, 0.0, 0.0)

        @module.on('unflip')
        def unflip(ev, *args):
            self.settings.set('flip', False)

        @module.on('autoplay')
        def autoplay(ev, *args):
            doAP = True
            if len(args) > 0:
                doAP = int(args[0]) > 0
            self.settings.set('autoplay', doAP)