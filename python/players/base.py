from __future__ import print_function

import os
import threading
from termcolor import colored

import interfaces

class BasePlayer(object):

    _lock = threading.Lock()
    _running = threading.Event()
    _running.set()

    name = "DUMMY Player"
    basepath = "~/media/"

    _playlist = []
    _currentIndex = -1
    _validExt = '*'

    _events = {}
    _interfaces = []
    _status = {
        'volume':       50,
        'mute':         False,
        'loop':         True,
        'random':       False,
        'isPlaying':    False,
        'isPaused':     False
    }

    def __init__(self):
        self.nameP = colored(self.name,'magenta')

    def setBasePath(self, basepath):
        self.basepath = basepath if basepath else "~/media/"

    def addInterface(self, iface, args=[]):
        InterfaceClass = interfaces.getInterface(iface)
        self._interfaces.append(InterfaceClass(self, args))
        return self._interfaces[-1]

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
            if os.path.isdir(entry):
                liste.extend(self.addToList(liste, os.listdir(entry)))
            elif os.path.isdir(self.basepath+entry):
                liste.extend(self.addToList(liste, os.listdir(self.basepath+entry)))
            elif os.path.isfile(entry):
                if self.validExt(entry):
                    liste.append(entry)
            elif os.path.isfile(self.basepath+entry):
                if self.validExt(entry):
                    liste.append(self.basepath+entry)
            else:
                print(self.nameP, "can't find", entry, "- skipping..")
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
    def trigger(self, event):
        if event in self._events:
            print(self.nameP, "event:", event)
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
        for iface in self._interfaces:
            if not iface.isRunning():
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
        for iface in self._interfaces:
            iface.quit()
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

    # PLAY A Playlist or Index
    def play(self, arg=0):

        # Load playlist (if not index provided)
        if not isinstance(arg, int):
            self.load(arg)
            arg = 0

        # Play file at index
        error = False
        with self._lock:
            if arg >= 0 and arg < len(self._playlist):
                self._play(self._playlist[arg])
            else:
                print(self.nameP, "no file to play..")
                error = True
        if error:
            self.stop()

    # STOP Playback
    def stop(self):
        with self._lock:
            self._stop()
            self._currentIndex = -1

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
