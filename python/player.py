from __future__ import print_function
from termcolor import colored
import os, threading

from players.base import BasePlayer
from players.mpv import MpvPlayer

from interfaces.osc import OscInterface
from interfaces.http import HttpInterface
from interfaces.gpio import GpioInterface

class PlayerAbstract:

    def __init__(self, name=None, player=None, basepath=None):

        self.name = name if name else 'unknown'
        self.nameP = colored('PLAYER '+self.name,'cyan')

        self.volume = 50
        self.mute = False
        self.loop = True
        self.random = False
        self.zoom = 100

        self.basepath = basepath if basepath else '~/media/'
        self.playlist = []
        self.currentIndex = -1

        self.lock = threading.Lock()

        # Real player
        if player == 'mpv':
            self.player = MpvPlayer(self.name, '/var/tmp/hplayer-'+self.name)
        else:
            self.player = BasePlayer(self.name)

        # Interfaces
        self.interfaces = []

        # play the whole directory
        self.player.on('end', self.next)

        print(self.nameP, "started - basepath:", self.basepath)


    def addInterface(self, iface, args=[]):

        if iface == 'osc':
            if len(args) < 2:
                print(self.nameP, 'OSC interface needs in and out port arguments')
            else:
                self.interfaces.append( OscInterface(self, args[0], args[1]) )
                return self.interfaces[-1]

        elif iface == 'http':
            if len(args) < 1:
                print(self.nameP, 'HTTP interface needs port')
            else:
                self.interfaces.append( HttpInterface(self, args) )
                return self.interfaces[-1]

        elif iface == 'gpio':
            if len(args) < 1:
                print(self.nameP, 'GPIO interface needs pinouts')
            else:
                self.interfaces.append( GpioInterface(self, args) )
                return self.interfaces[-1]

        else:
            print(self.nameP, 'unknown interface',iface)


    def quit(self):
        for iface in self.interfaces:
            iface.quit()
        self.player.quit()

    def on(self, event, callback):
        self.player.on(event, callback)

    def trigger(self, event):
        self.player.trigger(event)

    def isRunning(self):
        for iface in self.interfaces:
            if not iface.isRunning():
                return False
        return self.player.isRunning()


    def load(self, playlist=None):

        if not playlist:
            playlist = self.basepath

        if not type(playlist) is list:
            playlist = [playlist]

        newlist = []
        for entry in playlist:
            if os.path.isfile(entry):
                if self.player.validExt(entry):
                    newlist.append(entry)
            elif os.path.isdir(entry):                  #TODO recursive digg into subdirs
                for subentry in os.listdir(entry):
                    if self.player.validExt(entry):
                        newlist.append(entry)
            elif os.path.isfile(self.basepath+entry):
                if self.player.validExt(entry):
                    newlist.append(self.basepath+entry)
            else:
                print(self.nameP, "can't find", entry, "- skipping..")

        with self.lock:
            self.playlist = newlist
            self.currentIndex = -1


    def play(self, arg=None):
        if arg:
            self.load(arg)
        self.play_index(0)


    def play_index(self, index):
        error = False
        with self.lock:
            if index >= 0 and index < len(self.playlist):
                self.player.play(self.playlist[index])
            else:
                print(self.nameP, "no file to play..")
                error = True

        if error:
            self.stop()


    def stop(self):
        with self.lock:
            self.player.stop()
            self.currentIndex = -1


    def pause(self):
        self.player.pause()


    def resume(self):
        self.player.resume()


    def next(self):
        with self.lock:
            self.currentIndex += 1
            if self.currentIndex >= len(self.playlist) and self.loop:
                self.currentIndex = 0
            self.play_index(self.currentIndex)


    def seekTo(self, milli):
        self.player.seekTo(milli)

    def status(self):
        return self.player.status()

    def isPlaying(self):
        return self.player.status()['isPlaying']
