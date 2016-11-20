from __future__ import print_function
from termcolor import colored
import threading
from time import sleep

class BaseInterface(object):

    def  __init__(self, player):

        self.name = "INTERFACE"
        self.nameP = colored(self.name,'blue')

        self.player = player

        # running flag
        self.running = threading.Event()

        # Receive thread
        self.recvThread = threading.Thread(target=self.receive)

    # receiver THREAD (dummy)
    def receive(self):
        while self.isRunning():
            sleep(1000)
        return

    # Stop
    def start(self):
        self.running.set()
        self.recvThread.start()
        return self

    # Stop
    def quit(self):
        self.isRunning(False)
        self.recvThread.join()
        print(self.nameP, "stopped")

	# is Running
    def isRunning(self, state=None):
        if state is not None:
            self.running.set() if state else self.running.clear()
        return self.running.is_set()
