from __future__ import print_function
from termcolor import colored
from time import sleep
from .base import BaseOverlay
import copy
import queue
from .rpiopengles import rpiopengles

class RpifadeOverlay (BaseOverlay):

    queue = queue.Queue()
    nextFader = {'red': 0.0, 'green': 0.0, 'blue': 0.0, 'alpha': 0.0}
    currentFader = copy.deepcopy(nextFader)

    def __init__(self):
        super(RpifadeOverlay, self).__init__()

        self.name = "RPI Fade"
        self.nameP = colored(self.name,'cyan')
        # self.texture = rpiopengles.colortexture()
        self.start()

    # Queue processor
    def receive(self):

        texture = rpiopengles.colortexture()
        print(self.nameP, "texture created")

        while self.isRunning():
            if not self.queue.empty():
                goalFader = self.queue.get()
                workit = True
                while workit:
                    # print (self.currentFader)
                    workit = False
                    self.currentFader['red'] = goalFader['red']
                    self.currentFader['green'] = goalFader['green']
                    self.currentFader['blue'] = goalFader['blue']
                    diff =  goalFader['alpha'] - self.currentFader['alpha']
                    if diff != 0:
                        workit = True
                        if diff > 0:
                            diff = min(0.04, diff)
                        elif diff < 0:
                            diff = max(-0.04, diff)
                        self.currentFader['alpha'] += diff

                    texture.draw(   red=self.currentFader['red'],
                                    green=self.currentFader['green'],
                                    blue=self.currentFader['blue'],
                                    alpha=self.currentFader['alpha'])

                    if self.queue.empty(): sleep(0.05)
                    else: workit = False

            sleep(0.1)

        self.isRunning(False)
        return

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
