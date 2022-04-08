from .base import BaseInterface
from time import sleep

class TickerInterface (BaseInterface):

    def __init__(self, hplayer, bpm, event='tick'):
        super().__init__(hplayer, "Ticker")
        self._bpm = bpm
        self._event = event
        self._count = 0

    # receiver THREAD
    def listen(self):
        self.log("starting Ticker")
        while self.isRunning():
            sleep(60/self._bpm)
            self._count += 1
            self.emit(self._event, self._count)

    # BPM set
    def setBPM(self, bpm):
        self._bpm = bpm
        