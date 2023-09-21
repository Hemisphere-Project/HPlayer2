from ..module import Module
import threading
from time import sleep
from abc import ABC, abstractmethod

class BaseInterface(ABC, Module):

    def  __init__(self, hplayer, name="INTERFACE", color="blue"):
        super().__init__(hplayer, name, color)
        self.hplayer = hplayer

        # stopping flag
        self.stopped = threading.Event()
        self.stopped.set()

        # Listen thread
        self.recvThread = threading.Thread(target=self.listen)
        
        # Autobind to player
        hplayer.autoBind(self)


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
    def quit(self, join=True):
        if self.isRunning(): 
            self.log("stopping...")
            self.stopped.set()
        if join:
            self.recvThread.join()
            self.log("stopped")

	# is Running
    def isRunning(self, state=None):
        if state is not None:
            self.stopped.clear() if state else self.stopped.set()
        return not self.stopped.is_set()



        