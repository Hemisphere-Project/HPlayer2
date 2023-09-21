from time import sleep
from .base import BaseOverlay
import copy
import queue
from .rpiopengles import rpiopengles

class RpifadeOverlay (BaseOverlay):

    queue = queue.Queue()
    nextFader = {'red': 0.0, 'green': 0.0, 'blue': 0.0, 'alpha': 0.0}
    currentFader = copy.deepcopy(nextFader)

    def __init__(self, hplayer):
        super().__init__(hplayer, 'Rpifade', 'cyan')
        self.workit = False


    # Queue processor
    def receive(self):

        texture = rpiopengles.colortexture()
        self.log("texture created")

        while self.isRunning():
            if not self.queue.empty():
                goalFader = self.queue.get()
                self.workit = True
                while self.workit:
                    self.workit = False
                    self.currentFader['red'] += self._diff( goalFader['red'], self.currentFader['red'])
                    self.currentFader['green'] += self._diff( goalFader['green'], self.currentFader['green'])
                    self.currentFader['blue'] += self._diff( goalFader['blue'], self.currentFader['blue'])
                    self.currentFader['alpha'] += self._diff( goalFader['alpha'], self.currentFader['alpha'])

                    self.log("fader", self.currentFader)
                    
                    texture.draw(   red=self.currentFader['red'],
                                    green=self.currentFader['green'],
                                    blue=self.currentFader['blue'],
                                    alpha=self.currentFader['alpha'])
                    sleep(0.05)

            sleep(0.1)

        self.isRunning(False)
        return

    def _diff(self, goal, current):
        diff = goal - current
        if diff != 0:
            self.workit = True
            if diff > 0:
                diff = min(0.1, diff)
            elif diff < 0:
                diff = max(-0.1, diff)
            return diff
        return 0

    # Add instruction
    def set(self, red=None, green=None, blue=None, alpha=None):
        if red != None:
            self.nextFader['red'] = red
        if green != None:
            self.nextFader['green'] = green
        if blue != None:
            self.nextFader['blue'] = blue
        if alpha != None:
            self.nextFader['alpha'] = alpha
        self.queue.put(copy.deepcopy(self.nextFader))
