from __future__ import print_function

import os
import threading
import glob
from termcolor import colored

from core import interfaces
from core import overlays

class BasePlayer(object):

    _lock = threading.Lock()
    _running = threading.Event()
    _running.set()

    name = "DUMMY Player"
    basepath = ["/media/usb/"]

    log = {
        'events':   False
    }

    _playlist = []
    _currentIndex = -1
    _validExt = '*'

    _events = {}
    _interfaces = {}
    _overlays = {}
    _status = {
        'volume':       100,
        'mute':         False,
        'loop':         True,
        'flip':         False,
        'random':       False,
        'isPlaying':    False,
        'isPaused':     False,
        'media':        None
    }

    def __init__(self):
        self.nameP = colored(self.name,'magenta')
        self.on('end', self.next)

    def setBasePath(self, bpath):
        if not isinstance(bpath, list):
            bpath = [bpath]
        self.basepath = []
        for base in bpath:
            self.basepath.append(os.path.join(base, ''))

    def addInterface(self, iface, args=[]):
        InterfaceClass = interfaces.getInterface(iface)
        self._interfaces[iface] = InterfaceClass(self, args)
        return self._interfaces[iface]

    def addOverlay(self, olay, args=[]):
        OverlayClass = overlays.getOverlay(olay)
        self._overlays[olay] = OverlayClass()
        return self._overlays[olay]

    def getInterface(self, name):
        if name in self._interfaces.keys():
            return self._interfaces[name]
        return None

    def getOverlay(self, name):
        if name in self._overlays.keys():
            return self._overlays[name]
        return None


    #
    # Player TOOLS
    #

    # CHECK EXT
    def validExt(self, filename):
        if self._validExt == '*':
            return True
        elif filename.lower().endswith(self._validExt):
            return True
        else:
            return False

    # BUILD LIST RECURSIVE
    def buildList(self, files):
        liste = []
        for entry in files:
            # full path directory -> add content recursively
            if os.path.isdir(entry):
                liste.extend(self.buildList(os.listdir(entry)))
            # full path file -> add it
            elif os.path.isfile(entry):
                if self.validExt(entry):
                    liste.append(entry)
            # full path file with WILDCARD
            elif entry[0] == '/' and len(glob.glob(entry)) > 0:
                for e in glob.glob(entry):
                    if os.path.isfile(e):
                        liste.extend(e)

            # check each base path
            else:
                for base in self.basepath:
                    fullpath = os.path.join(base,entry)
                    # relative path directory -> add content recursively
                    if os.path.isdir(fullpath):
                        liste.extend(self.buildList(fullpath))
                        break
                    # relative path file -> add content recursively
                    elif os.path.isfile(fullpath):
                        if self.validExt(entry):
                            liste.append(fullpath)
                            break
                    # relative path file with WILDCARD
                    elif len(glob.glob(fullpath)) > 0:
                        for e in glob.glob(fullpath):
                            if os.path.isfile(e) and self.validExt(e):
                                liste.append(e)
                        break

        liste = sorted(liste)
        return liste

    #
    # Player EVENTS
    #

    # EVENT Set callback
    def on(self, event, callback):
        if callback:
            if not type(event) is list:
                event = [event]
            for e in event:
                self._events[e] = callback

    # EVENT Trigger callback
    def trigger(self, event, args=None):
        if self.log['events']:
            print(self.nameP, "event:", event, "/ args:", args)

        if '*' in self._events:
            self._events['*'](event, args)

        if event in self._events:
            if args:
                self._events[event](args)
            else:
                self._events[event]()



    #
    # Player STATUS
    #

    # SET/GET is running
    def isRunning(self, state=None):
        # SET (optionnal)
        if state is not None:
            self._running.set() if state else self._running.clear()
        # GET
        for iface in self._interfaces.values():
            if not iface.isRunning():
                return False
        # GET
        for olay in self._overlays.values():
            if not olay.isRunning():
                return False
        return self._running.is_set()

    # STATUS Get
    def status(self):
        return self._status.copy()

    def isPlaying(self):
        return self._status['isPlaying']

    #
    # Player CONTROLS
    #

    # QUIT
    def quit(self):
        for iface in self._interfaces.values():
            iface.quit()
        for olay in self._overlays.values():
            olay.quit()
        self._quit()
        self.isRunning(False)

    # LOAD A PLAYLIST
    def load(self, playlist=None):

        if not playlist:
            playlist = self.basepath
        if not type(playlist) is list:
            playlist = [playlist]

        with self._lock:
            self._playlist = self.buildList(playlist)
            self._currentIndex = -1

        # print("Current playlist: ", self._playlist)

    # PLAY A Playlist or Index
    def play(self, arg=0):

        # Load playlist (if not index provided)
        if not isinstance(arg, int):
            self.load(arg)
            arg = 0

        # Play file at index
        error = False
        nomedia = False
        with self._lock:
            if arg >= 0 and arg < len(self._playlist) and os.path.isfile(self._playlist[arg]):
                self._currentIndex = arg
                self._status['media'] = self._playlist[arg]
                # print(self.nameP, "PLAY ", self._status['media'])
                self._play(self._playlist[arg])
            else:
                self._status['media'] = None
                print(self.nameP, "Empty playlist..")
                error = True
                nomedia = True

        if nomedia:
            self.trigger('nomedia')
        if error:
            self.stop()
        else:
            self.trigger('play', [self._status['media']])


    # STOP Playback
    def stop(self):
        print(self.nameP, "stop")
        self._status['media'] = None
        with self._lock:
            self._stop()
            self._currentIndex = -1
        self.trigger('stop')

    # PAUSE Playback
    def pause(self):
        self._pause()

    # RESUME Playback
    def resume(self):
        self._resume()

    # NEXT item in playlist
    def next(self):
        with self._lock:
            self._currentIndex += 1
            if self._currentIndex >= len(self._playlist) and self._status['loop']:
                self._currentIndex = 0
        self.play(self._currentIndex)

    # PREVIOUS item in playlist
    def prev(self):
        with self._lock:
            self._currentIndex -= 1
            if self._currentIndex < 0 and self._status['loop']:
                self._currentIndex = len(self._playlist)-1
            self.play(self._currentIndex)

     # SEEK to position
    def seekTo(self, milli):
        self._seekTo(milli)

    # LOOP
    def loop(self, doloop):
       self._status['loop'] = doloop

    # VOLUME
    def volume(self, vol):
       self._status['volume'] = vol
       self._applyVolume()

    # MUTE
    def mute(self, domute):
       self._status['mute'] = domute
       self._applyVolume()

    # FLIP
    def flip(self, doflip):
       self._status['flip'] = doflip
       self._applyFlip()

    #
    # Player INTERNAL actions: Methods to overwrite !
    #

    def _quit(self):
        print(self.nameP, "quit")

    def _play(self, path):
        self._status['isPlaying'] = True
        print(self.nameP, "play", path)

    def _stop(self):
        self._status['isPlaying'] = False
        print(self.nameP, "stop")

    def _pause(self):
        self._status['isPaused'] = True
        print(self.nameP, "pause")

    def _resume(self):
        self._status['isPaused'] = False
        print(self.nameP, "resume")

    def _seekTo(self, milli):
        print(self.nameP, "seek to", milli)

    def _applyVolume(self):
        if not self._status['mute']:
            print(self.nameP, "volume set to", self._status['volume'])
        else:
            print(self.nameP, "volume muted")

    def _applyFlip(self):
        if not self._status['flip']:
            print(self.nameP, "screen flipped")
        else:
            print(self.nameP, "screen not flipped")
