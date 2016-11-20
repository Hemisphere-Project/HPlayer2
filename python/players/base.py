from __future__ import print_function
from termcolor import colored
import threading

class BasePlayer(object):

    running = threading.Event()
    running.set()

    _status = {
        'isPlaying': False,
        'isPaused': False
    }

    _events = {}

    def __init__(self, name):
        self.name = "DUMMY "+name
        self.nameP = colored(self.name,'magenta')


    def on(self, event, callback):
        if callback:
            self._events[event] = callback

    def trigger(self, event):
        if event in self._events:
            print(self.nameP, event)
            self._events[event]()

    def isRunning(self, state=None):
        if state is not None:
            self.running.set() if state else self.running.clear()
        return self.running.is_set()

    def quit(self):
        self.isRunning(False)

    def validExt(self, file):
        return True

    def status(self):
        return self._status.copy()

    def play(self, path):
        self._status['isPlaying'] = True
        print(self.nameP, "play", path)

    def stop(self):
        self._status['isPlaying'] = False
        print(self.nameP, "stop")

    def pause(self):
        print(self.nameP, "pause")

    def resume(self):
        print(self.nameP, "resume")

    def seekTo(self, milli):
        print(self.nameP, "seek to", milli)
