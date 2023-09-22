from ..module import Module
import threading
from time import sleep

class BaseOverlay(Module):

    def  __init__(self, hplayer, name="OVERLAY", color="cyan"):

        super().__init__(hplayer, name, color)
        self.hplayer = hplayer

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
        self.log("stopped")

	# is Running
    def isRunning(self, state=None):
        if state is not None:
            self.running.set() if state else self.running.clear()
        return self.running.is_set()
