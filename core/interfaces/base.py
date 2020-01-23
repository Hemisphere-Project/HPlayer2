from __future__ import print_function
from termcolor import colored
import threading
from time import sleep
from abc import ABC, abstractmethod
from pymitter import EventEmitter

class BaseInterface(ABC, EventEmitter):

    def  __init__(self, hplayer, name="INTERFACE", color="blue"):
        
        super().__init__(wildcard=True, delimiter=".")

        self.name = name
        self.nameP = colored(self.name, color)

        self.hplayer = hplayer

        # stopping flag
        self.stopped = threading.Event()
        self.stopped.set()

        # Listen thread
        self.recvThread = threading.Thread(target=self.listen)

    # Receiver THREAD (ABSTRACT)
    @abstractmethod
    def listen(self):
        self.stopped.wait()

    # Start
    def start(self):
        self.stopped.clear()
        self.recvThread.start()
        return self

    # Stop
    def quit(self):
        self.stopped.set()
        self.recvThread.join()
        self.log("stopped")

	# is Running
    def isRunning(self, state=None):
        if state is not None:
            self.stopped.clear() if state else self.running.set()
        return not self.stopped.is_set()

    # Log
    def log(self,  *argv):
        print(self.nameP, *argv)

    # Emit extended
    def emit(self, cmd, *args):
        self.hplayer.emit( self.name.lower() + '.' + cmd, *args )
        super().emit(cmd, *args)

        