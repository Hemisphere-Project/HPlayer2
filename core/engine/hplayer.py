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
from threading import Timer, Event
from termcolor import colored
from time import sleep
import signal
import sys, os, platform, shutil, subprocess, inspect
from pymitter import EventEmitter
from platformdirs import user_data_dir
import tempfile


_RUN_EVENT = Event()
_RUN_EVENT.set()

# CTR-C Handler
def signal_handler(signal, frame):
    print('\n'+colored('[SIGINT] You pressed Ctrl+C!', 'yellow'))
    _RUN_EVENT.clear()
signal.signal(signal.SIGINT, signal_handler)


class HPlayer2(Module):

    def __init__(self, mediaPath=None, config=None, datadir=None, extraMediaPath=None):
        # Backward compatibility: detect old API usage
        # Old API: HPlayer2(basepath, settingspath)
        # New API: HPlayer2(mediaPath=..., config=..., datadir=..., extraMediaPath=...)
        
        # If mediaPath is a string and config is also a string (old API pattern)
        # OR if both positional args are provided as strings
        if isinstance(mediaPath, str) and isinstance(config, str) and datadir is None and extraMediaPath is None:
            # Old API: HPlayer2(basepath, settingspath)
            old_basepath = mediaPath
            old_settingspath = config
            mediaPath = old_basepath
            config = old_settingspath
            datadir = None
            extraMediaPath = None
        
        # super().__init__(wildcard=True, delimiter=".")
        super().__init__(None, 'HPlayer2', 'green')
        self.nameP = colored(('[HPlayer2]').ljust(10, ' ')+' ', 'green')

        self._shutdown_event = _RUN_EVENT
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._exit_code = 0

        self._lastUsedPlayer = 0

        self._players       = OrderedDict()
        self._samplers      = OrderedDict()
        self._interfaces    = OrderedDict()

        # State flags
        self.appReady = False      # Set when app-ready event is emitted
        self.appRunning = False    # Set when app-run event is emitted

        # Determine datadir
        if datadir is None:
            datadir = user_data_dir("HPlayer2", "Hemisphere")
        self.datadir = datadir

        # Create datadir
        try:
            os.makedirs(self.datadir, exist_ok=True)
        except Exception as e:
            self.log(colored(f"ERROR: Failed to create datadir {self.datadir}: {e}", 'red'))

        # Setup temp directory
        self.tempdir = os.path.join(self.datadir, 'tmp')
        try:
            os.makedirs(self.tempdir, exist_ok=True)
            tempfile.tempdir = self.tempdir
        except Exception as e:
            self.log(colored(f"ERROR: Failed to create temp directory {self.tempdir}: {e}", 'red'))

        # Helper to normalize paths (resolve relative paths based on datadir)
        def normalize_path(path):
            if os.path.isabs(path):
                return path
            return os.path.join(self.datadir, path)

        # Helper to normalize path list
        def normalize_paths(paths):
            if paths is None:
                return []
            if not isinstance(paths, list):
                paths = [paths]
            return [normalize_path(p) for p in paths]

        # Build mediaPath list
        if mediaPath is None:
            # Use default: datadir/media
            basepath = [os.path.join(self.datadir, 'media')]
        else:
            # Use provided mediaPath (normalized)
            basepath = normalize_paths(mediaPath)

        # Append extraMediaPath if provided
        if extraMediaPath is not None:
            basepath.extend(normalize_paths(extraMediaPath))

        # Create media directories
        for path in basepath:
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                self.log(colored(f"ERROR: Failed to create media directory {path}: {e}", 'red'))

        # Determine config file path
        settingspath = None
        if config is not None:
            if config is True:
                # Auto-detect profile name from calling file
                try:
                    frame = inspect.currentframe().f_back
                    calling_file = frame.f_globals.get('__file__', None)
                    if calling_file:
                        profile_name = os.path.splitext(os.path.basename(calling_file))[0]
                        settingspath = os.path.join(self.datadir, f'hplayer2-{profile_name}.cfg')
                    else:
                        self.log(colored("WARNING: Could not detect profile name for config auto-naming", 'yellow'))
                except Exception as e:
                    self.log(colored(f"WARNING: Failed to detect profile name: {e}", 'yellow'))
            elif os.path.isabs(config):
                # Absolute path provided
                settingspath = config
            else:
                # Relative name or name.cfg
                if not config.endswith('.cfg'):
                    config = config + '.cfg'
                settingspath = os.path.join(self.datadir, config)

        # Initialize components
        self.settings       = Settings(self, settingspath)
        self.files          = FileManager(self)
        self.playlist       = Playlist(self)
        
        self.imgen          = ImGen(self)

        self.files.add(basepath)

        self.autoBind(self)
        self.logQuietEvents = ['status']


    def log(self, *argv):
        print(self.nameP, *argv)

    @staticmethod
    def isRPi():
        return platform.machine().startswith('armv')

    @staticmethod
    def hostname():
        return network.get_hostname()

    #
    # PLAYERS
    #

    def addPlayer(self, ptype, name):
        # if not name: name = ptype+str(len(self._players))
        if name and name in self._players:
            self.log("player", name, "already exists")
        else:
            try:
                PlayerClass = playerlib.getPlayer(ptype)
            except (ImportError, AttributeError) as err:
                self.log("player", ptype, "not available:", err)
                return None

            try:
                p = PlayerClass(self, name)
            except RuntimeError as err:
                self.log("player", ptype, "disabled:", err)
                return None
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

            # Bind Brightness
            @self.settings.on('do-brightness')
            def brightness(ev, value, settings):
                p._applyBrightness( settings['brightness'] )
                
            # Bind Contrast
            @self.settings.on('do-contrast')
            def contrast(ev, value, settings):
                p._applyContrast( settings['contrast'] )

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
                self._kill_process('mpv')
                self.request_shutdown(force=True)

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

    def _kill_process(self, name):
        pkill = shutil.which('pkill')
        if pkill:
            subprocess.run([pkill, name], check=False)
        else:
            self.log('pkill not available; unable to terminate', name)

    def _force_exit(self, code=0):
        os._exit(code)

    def request_shutdown(self, exit_code=0, *, force=False, force_delay=None):
        """Signal the main loop to terminate and optionally force exit."""
        self._exit_code = exit_code
        if not self._shutdown_requested and force_delay:
            Timer(force_delay, self._force_exit, args=(exit_code,)).start()
        self._shutdown_requested = True
        self._shutdown_event.clear()
        if force:
            self._force_exit(exit_code)

    def shutdown(self, exit_code=0):
        """Public helper to request a graceful shutdown."""
        self.request_shutdown(exit_code=exit_code)

    def _stop_components(self):
        if self._shutdown_complete:
            return

        self._shutdown_complete = True

        self.log()
        self.log("is closing..")
        self.emit('app-closing')

        interfaces = list(self.interfaces())
        players = self.players()
        samplers = self.samplers()

        for iface in interfaces:
            iface.quit(False)
        for player in players:
            player.quit()
        for sampler in samplers:
            sampler.quit()

        for iface in interfaces:
            iface.quit(True)

        self.emit('app-quit')
        self.log("stopped. Goodbye !\n")


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
                self._kill_process('mpv')
                self.request_shutdown(force=True)

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
        try:
            InterfaceClass = ifacelib.getInterface(iface)
        except (ImportError, AttributeError) as err:
            self.log("interface", iface, "not available:", err)
            return None

        try:
            instance = InterfaceClass(self, *argv)
        except RuntimeError as err:
            self.log("interface", iface, "disabled:", err)
            return None

        self._interfaces[iface] = instance
        return instance


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
        self._shutdown_event.set()
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._exit_code = 0

        try:
            try:
                if network.get_ip("eth0") != "127.0.0.1":
                    self.log("IP for eth0 is", network.get_ip("eth0"))
                if network.get_ip("wint") != "127.0.0.1":
                    self.log("IP for wint  is", network.get_ip("wint"))
                if network.get_ip("wlan0") != "127.0.0.1":
                    self.log("IP for wlan0  is", network.get_ip("wlan0"))
            except Exception:
                pass

            self.log("started.. Welcome ! \n")

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

            # WAIT for players and samplers to be ready, but respect shutdown signals
            for component in self.players() + self.samplers():
                while (self._shutdown_event.is_set()
                       and component.isRunning()
                       and not component.isReady()):
                    sleep(0.1)

                if not self._shutdown_event.is_set():
                    self.log("shutdown requested before components became ready")
                    break

                if not component.isRunning() and not component.isReady():
                    self.log(component.name, "failed to start correctly; continuing without waiting")
            
            self.appReady = True
            self.emit('app-ready')

            # LOAD persistent settings
            self.settings.load()

            self.appRunning = True
            self.emit('app-run')

            while self._shutdown_event.is_set() and self.running():
                sys.stdout.flush()
                sleep(0.5)
        finally:
            self.appRunning = False
            self.appReady = False
            self._stop_components()

        return self._exit_code


    #
    # BINDINGS
    #

    def autoBind(self, module):
        
        # SYSTEM
        #
        @module.on('hardreset')
        def hardreset(ev, *args): 
            systemctl = shutil.which('systemctl')
            if systemctl:
                subprocess.run([systemctl, 'restart', 'NetworkManager'], check=False)
            else:
                self.log('systemctl not available; skipping NetworkManager restart')
            self.request_shutdown(force_delay=5.0)
            self._kill_process('mpv')
            self.log('HARD KILL in 5s')
            # os._exit(0)

        # @module.on('do-audioout')
        # def doaudioout(ev, *args):
        #     if len(args) > 0:
        #         doreset = False
        #         if args[0] == 'hdmi':
        #             if not 'pcm.!default hdmi0' in open('/etc/asound.conf').read():
        #                 os.system('rw && \
        #                           sed -i "s/pcm.!default .*/pcm.!default hdmi0/g" /etc/asound.conf && \
        #                           sed -i "s/ctl.!default .*/ctl.!default hdmi0/g" /etc/asound.conf && \
        #                           sync && ro')
        #                 doreset = True
        #             os.system('amixer sset PCM 96%')
                    
                    
                        
        #         elif args[0] == 'jack':
        #             if not 'pcm.!default jack' in open('/etc/asound.conf').read():
        #                 os.system('rw && \
        #                           sed -i "s/pcm.!default .*/pcm.!default jack/g" /etc/asound.conf && \
        #                           sed -i "s/ctl.!default .*/ctl.!default jack/g" /etc/asound.conf && \
        #                           sync && ro')
        #                 doreset = True
        #             os.system('amixer sset PCM 96%')
                        
        #         elif args[0] == 'usb':
        #             if not 'pcm.!default usb' in open('/etc/asound.conf').read():
        #                 os.system('rw && \
        #                           sed -i "s/pcm.!default .*/pcm.!default usb/g" /etc/asound.conf && \
        #                           sed -i "s/ctl.!default .*/ctl.!default usb/g" /etc/asound.conf && \
        #                           sync && ro')
        #                 doreset = True
        #             os.system('amixer sset Speaker 96%')
                
        #         if doreset:
        #             module.emit('hardreset')

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
            
        # Play stream
        @module.on('playstream')
        def playstream(ev, *args):
            if len(args) > 0:
                self.playlist.playstream(args[0])
            
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

        @module.on('do-playlist')
        def doplaylist(ev, *args):
            self.playlist.load(args[0] if len(args) > 0 else None)

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
        
        @module.on('get-settings')
        def getsettings(ev, *args):
            self.settings.update()

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
                
        @module.on('brightness')
        def brightness(ev, *args):
            if len(args) > 0:
                bright = int(args[0])
                if (bright < 0): bright = 0
                if (bright > 100): bright = 100
                self.settings.set('brightness', bright)
                
        @module.on('contrast')
        def contrast(ev, *args):
            if len(args) > 0:
                contrast = int(args[0])
                if (contrast < 0): contrast = 0
                if (contrast > 100): contrast = 100
                self.settings.set('contrast', contrast)
        
        @module.on('flip')
        def flip(ev, *args):
            doFlip = True
            if len(args) > 0:
                doFlip = int(args[0]) > 0
            self.settings.set('flip', doFlip)

        @module.on('fade')
        def fade(ev, *args):
            o = self.players()[0].getOverlay('rpifade')
            if not o: return
            if len(args) == 1 and args[0][0] == '#':
                color = tuple(int(args[0][i:i+2], 16)/255.0 for i in (1, 3, 5))
                o.set(color[0], color[1], color[2], 1.0)
            elif len(args) > 3:
                o.set(float(args[0]),float(args[1]), float(args[2]), float(args[3]))
            elif len(args) > 2:
                o.set(float(args[0]),float(args[1]), float(args[2]), 1.0)
            else:
                o.set(0.0, 0.0, 0.0, 1.0)

        @module.on('unfade')
        def unfade(ev, *args):
            o = self.players()[0].getOverlay('rpifade')
            if o: o.set(0.0, 0.0, 0.0, 0.0)

        @module.on('unflip')
        def unflip(ev, *args):
            self.settings.set('flip', False)

        @module.on('autoplay')
        def autoplay(ev, *args):
            doAP = True
            if len(args) > 0:
                doAP = int(args[0]) > 0
            self.settings.set('autoplay', doAP)

        @module.on('do-autoplay')
        def doautoplay(ev, *args):
            if args[0] and not self.activePlayer().isPlaying():
                self.playlist.play()
            elif not args[0] and self.activePlayer().isPlaying():
                self.activePlayer().stop()
            
        @module.on('filter')
        def filter(ev, *args):
            print('filter', args)
            if len(args) > 0:
                self.settings.set('filter', args[0])
            else:
                self.settings.set('filter', '')
