from __future__ import print_function
from termcolor import colored
import os, threading

from players.base import BasePlayer
from players.mpv import MpvPlayer

from interfaces.osc import OscInterface

class PlayerAbstract:

    def __init__(self, name=None, player=None):

        self.name = name if name else 'unknown'
        self.nameP = colored('PLAYER '+self.name,'cyan')

        self.volume = 50
        self.mute = False
        self.loop = True
        self.random = False
        self.zoom = 100

        self.basepath = '~/media/'
        self.playlist = []
        self.currentIndex = -1

        self.lock = threading.Lock()

        # Real player
        if player == 'mpv':
            self.player = MpvPlayer(self.name, '/tmp/hplayer-'+self.name)
        else:
            self.player = BasePlayer(self.name)

        # Interfaces
        self.interfaces = []
        # for iface in interfaces:
        #     if iface == 'osc':
        #         self.interfaces.append( OscInterface(oscPortIN, oscPortOUT, player1) )
        #     else:
        #         print(self.nameP, 'unknown interface',iface)
        #
        #
        #     self.interfaces.append()

        self.player.onMediaEnd(self.next)


    def addInterface(self, iface, args=[]):

        if iface == 'osc':
            if len(args) < 2:
                print(self.nameP, 'OSC interface needs in and out port arguments')
            else:
                self.interfaces.append( OscInterface(args[0], args[1], self) )
        else:
            print(self.nameP, 'unknown interface',iface)


    def quit(self):
        for iface in self.interfaces:
            iface.quit()
        self.player.quit()


    def isRunning(self):
        for iface in self.interfaces:
            if not iface.isRunning():
                return False
        return self.player.isRunning()


    def load(self, playlist=None):

        if type(playlist) is str:
            playlist = [playlist]

        if not playlist:
            playlist = self.basepath

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
                self.player.play(self.playlist[index])
            else:
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
