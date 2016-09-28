from __future__ import print_function
from termcolor import colored
import threading

class BasePlayer(object):

    stopEvent = threading.Event()

    def __init__(self):
        self.name = "Dummy IFACE"
        self.nameP = colored(self.name,'magenta')

    def onMediaEnd(self, callback):
        self.onEndCllbck = callback

    def quit(self):
        self.stopEvent.set()

    def isRunning(self):
        return not self.stopEvent.is_set()

    def validExt(self, file):
        return True

    def play(self, path):
        print(self.nameP, "play", path)

    def stop(self):
        print(self.nameP, "stop")

    def pause(self):
        print(self.nameP, "pause")

    def resume(self):
        print(self.nameP, "resume")

    def seekTo(self, milli):
        print(self.nameP, "seek to", milli)
