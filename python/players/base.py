from __future__ import print_function
from termcolor import colored
import threading

class BasePlayer(object):

    running = threading.Event()
    running.set()

    def __init__(self, name):
        self.name = "DUMMY "+name
        self.nameP = colored(self.name,'magenta')

    def onMediaEnd(self, callback):
        self.onEndCllbck = callback

    def isRunning(self, state=None):
        if state is not None:
            self.running.set() if state else self.running.clear()
        return self.running.is_set()

    def quit(self):
        self.isRunning(False)

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
