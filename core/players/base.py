from __future__ import print_function

import os
import threading
import glob
import pickle
import re
from termcolor import colored
from pathlib import Path

from core import interfaces
from core import overlays

class BasePlayer(object):

    _lock = threading.Lock()
    _running = threading.Event()
    _running.set()

    name = "DUMMY Player"
    basepath = ["/media/usb/"]
    settingspath = None

    log = {
        'events':   False
    }

    _playlist = []
    _currentIndex = -1
    _validExt = ['.mp4', '.m4v', '.mkv', 'avi', '.mov', '.flv', '.mpg', 'wmv', '.3gp', '.mp3', '.aac', '.wma', '.wav', '.flac', '.aiff', '.m4a', '.ogg', '.opus', '.webm']

    _events = {}
    _interfaces = {}
    _overlays = {}
    _status = {
        'isPlaying':    False,
        'isPaused':     False,
        'media':        None,
        'time':         0
    }
    _settings = {
        'volume':       100,
        'mute':         False,
        'loop':         2,              # 0: no loop / 1: loop one / 2: loop all
        'pan':          [100,100],
        'flip':         False,
        'autoplay':     False
    }

    def __init__(self):
        self.nameP = colored(self.name,'magenta')
        self.on('end', self.onMediaEnd)

    def onMediaEnd(self):
        if self._settings['loop'] == 1:     # loop one
            self.play()
        elif self._settings['loop'] == 2:   # loop all
            self.next()
        else:
            self.stop()

    def setBasePath(self, bpath):
        if not isinstance(bpath, list):
            bpath = [bpath]
        self.basepath = []
        for base in bpath:
            self.basepath.append(os.path.join(base, ''))

    def persistentSettings(self, spath):
        self.settingspath = Path(spath)

    def addInterface(self, iface, *argv):
        InterfaceClass = interfaces.getInterface(iface)
        self._interfaces[iface] = InterfaceClass(self, *argv)
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
        vExt = self._validExt
        if not type(vExt) is list:
            vExt = [vExt]
        for ext in vExt:
            if ext == '*':
                return True
            elif filename.lower().endswith(ext.lower()):
                return True
        return False


    # BUILD LIST RECURSIVE
    def buildList(self, entries):
        liste = []
        if not isinstance(entries, (list,)):
            entries = [entries]

        for entry in entries:

            # ABSOLUTE PATH

            # full path directory -> add content recursively
            if os.path.isdir(entry):
                dirContent = [os.path.join(entry, f) for f in os.listdir(entry)]
                dirContent.sort()
                liste.extend(self.buildList( dirContent ))

            # full path file -> add it
            elif os.path.isfile(entry):
                if self.validExt(entry):
                    liste.append(entry)

            # full path file with WILDCARD
            ## TODO PROBABLY BROKEN !
            # elif entry[0] == '/' and len(glob.glob(entry)) > 0:
            # 	for e in glob.glob(entry):
            #         if os.path.isfile(e):
            #             liste.extend(e)

            # RELATIVE PATH

            # check each base path
            else:
                for base in self.basepath:
                    if os.path.isdir(base):
                        fullpath = os.path.join(base, entry)
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
                        else:
                            globlist = []
                            for root, dirs, files in os.walk(base, topdown=False):
                               for name in files:
                                  fpath = os.path.join(root, name)
                                  match = re.match( r''+fullpath.replace('*','.*'), fpath, re.M|re.I)
                                  if ('/.' not in fpath) and match:
                                    	globlist.append(fpath)
                            #print(globlist)
                            for e in globlist:
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

    def isPaused(self):
        return self._status['isPaused']

    # SETTINGS
    def settings(self):
        return self._settings.copy()

    def settings_set(self, id, val):
        if id in self._settings:
            self._settings[id] = val
            self.trigger('settings-update', self._settings.copy())
            self.settings_save()

    def settings_load(self):
        if self.settingspath and self.settingspath.is_file():
            with open(self.settingspath, 'rb') as fd:
                self._settings = pickle.load(fd)
                self._applyVolume()
                self._applyPan()
                self._applyFlip()
                print(self.nameP, 'settings loaded:', self._settings)
                if self._settings['autoplay']:
                    self.play()

    def settings_save(self):
        if self.settingspath:
            with open(self.settingspath, 'wb') as fd:
                pickle.dump(self._settings, fd)
    #
    # Player CONTROLS
    #

    # START
    def start(self):
        self.on(['player-ready'], self.settings_load)
        for iface in self._interfaces.values():
            iface.start()
        # for olay in self._overlays.values():
        #     olay.start()
        self.load()             # Load default playlist based on basepath provided
        self.isRunning(True)
        self._start()

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

        print(self.nameP, "playlist loaded:", self._playlist)
        # print("Current playlist: ", self._playlist)

    # PLAY A Playlist or Index
    def play(self, arg=None):

        index = self._currentIndex
        if index == -1:
            index = 0

        # Direct index provided
        if isinstance(arg, int):
            index = arg

        # new playlist or media provided
        elif arg is not None:
            self.load(arg)
            index = 0

        valid = False

        # empty playlist: try a re-scan
        if len(self._playlist) == 0:
            self.load()
            index = 0

        # media not found: try a res-can
        if 0 <= index < len(self._playlist) and not os.path.isfile(self._playlist[index]):
            self.load()
            index = 0

        # Play file at index
        with self._lock:
            if 0 <= index < len(self._playlist) and os.path.isfile(self._playlist[index]):
                self._play(self._playlist[index])
                self._currentIndex = index
                self._status['media'] = self._playlist[index]
                valid = True

        # Emit play event
        if valid:
            self.trigger('play', [self._status['media']])

        # Handle error
        else:
            if self.isPlaying():
                self.stop()
            self.trigger('nomedia')

            if len(self._playlist) == 0:
                print(self.nameP, "No media found in", self.basepath)
            elif not (0 <= index < len(self._playlist)):
                print(self.nameP, "Index out of playlist range:", index, self._playlist)
            else:
                print(self.nameP, "Media not found:", self._playlist[index])


    # STOP Playback
    def stop(self):
        print(self.nameP, "stop")
        with self._lock:
            if self.isPlaying():
                self._stop()
            else:
                self._currentIndex = -1
        self._status['media'] = None
        self._status['time'] = 0
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
            if self._currentIndex >= len(self._playlist):
                self._currentIndex = 0
        self.play(self._currentIndex)

    # PREVIOUS item in playlist
    def prev(self):
        with self._lock:
            self._currentIndex -= 1
            if self._currentIndex < 0:
                self._currentIndex = len(self._playlist)-1
        self.play(self._currentIndex)

     # SEEK to position
    def seekTo(self, milli):
        self._seekTo(milli)

    # LOOP
    def loop(self, doloop):
        self.settings_set('loop', doloop)

    # AUTOPLAY
    def autoplay(self, doauto):
        self.settings_set('autoplay', doauto)
        if doauto and not self.isPlaying():
            self.load()
            self.play()

    # VOLUME
    def volume(self, vol):
        self.settings_set('volume', vol)
        self._applyVolume()

    # VOLUME INC
    def volume_inc(self):
        vol = self._settings['volume']
        vol += 1
        if vol > 100: vol = 100
        self.settings_set('volume', vol)
        self._applyVolume()

    # VOLUME DEC
    def volume_dec(self):
        vol = self._settings['volume']
        vol -= 1
        if vol < 0: vol = 0
        self.settings_set('volume', vol)
        self._applyVolume()

    # MUTE
    def mute(self, domute):
        self.settings_set('mute', domute)
        self._applyVolume()

    # TOGGLE MUTE
    def mute_toggle(self):
        self.mute(not self._settings['mute'])

    # PAN
    def pan(self, pano):
        self.settings_set('pan', pano)
        self._applyPan()

    # FLIP
    def flip(self, doflip):
       self.settings_set('flip', doflip)
       self._applyFlip()

    # TOGGLE FLIP
    def flip_toggle(self):
       self.flip(not self._settings['flip'])

    #
    # Player INTERNAL actions: Methods to overwrite !
    #

    def _start(self):
        print(self.nameP, "start")

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
        if not self._settings['mute']:
            print(self.nameP, "volume set to", self._settings['volume'])
        else:
            print(self.nameP, "volume muted")

    def _applyPan(self):
        print(self.nameP, "pan set to", self._settings['pan'])

    def _applyFlip(self):
        if not self._settings['flip']:
            print(self.nameP, "screen flipped")
        else:
            print(self.nameP, "screen not flipped")
