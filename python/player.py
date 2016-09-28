from __future__ import print_function
from termcolor import colored
import os
import threading
from players.base import BasePlayer
from players.mpv import MpvPlayer

class PlayerAbstract:

    def __init__(self, name=None, playerType=None):

        self.name = name if name else 'J0nny'
        self.volume = 50
        self.mute = False
        self.loop = True
        self.random = False
        self.zoom = 100

        self.basepath = '~/media/'
        self.playlist = []
        self.currentIndex = -1

        self.lock = threading.Lock()
        if playerType == 'mpv':
            self.playerIFACE = MpvPlayer('/tmp/hplayer-'+self.name)
        else:
            self.playerIFACE = BasePlayer()

        self.playerIFACE.onMediaEnd(self.next)


    def quit(self):
        self.playerIFACE.quit()


    def isRunning(self):
        return self.playerIFACE.isRunning()


    def load(self, playlist=None):

        if type(playlist) is str:
            playlist = [playlist]

        if not playlist:
            playlist = self.basepath

        newlist = []
        for entry in playlist:
            if os.path.isfile(entry):
                if self.playerIFACE.validExt(entry):
                    newlist.append(entry)
            elif os.path.isdir(entry):                  #TODO recursive digg into subdirs
                for subentry in os.listdir(entry):
                    if self.playerIFACE.validExt(entry):
                        newlist.append(entry)
            elif os.path.isfile(self.basepath+entry):
                if self.playerIFACE.validExt(entry):
                    newlist.append(self.basepath+entry)

        with self.lock:
            self.playlist = newlist
            self.currentIndex = -1


    def play(self, arg=None):
        if arg:
            self.load(arg)
        self.play_index(0)


    def play_index(self, index):
        with self.lock:
            if index >= 0 and index < len(self.playlist):
                self.playerIFACE.play(self.playlist[index])
            else:
                self.stop()


    def stop(self):
        with self.lock:
            self.playerIFACE.stop()
            self.currentIndex = -1


    def pause(self):
        self.playerIFACE.pause()


    def resume(self):
        self.playerIFACE.resume()


    def next(self):
        with self.lock:
            self.currentIndex += 1
            if self.currentIndex >= len(self.playlist) and self.loop:
                self.currentIndex = 0
            self.play_index(self.currentIndex)


    def seekTo(self, milli):
        self.playerIFACE.seekTo(milli)
