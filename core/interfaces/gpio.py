from __future__ import print_function

from termcolor import colored
from time import sleep

import RPi.GPIO as GPIO

from base import BaseInterface

DEBOUNCE = 50

class GpioInterface (BaseInterface):

    state = {}

    def __init__(self, player, args):

        if len(args) < 1:
            print(self.nameP, 'GPIO interface needs pinouts')

        super(GpioInterface, self).__init__(player)

        self.name = "GPIO "+player.name
        self.nameP = colored(self.name,'blue')

        self.pins = args
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(args, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.start()

    # GPIO receiver THREAD
    def receive(self):
        print(self.nameP, "starting GPIO listener")

        def clbck(pinz):
            # print(self.nameP, "channel", channel, "triggered")
            if not GPIO.input(pinz):
                if not self.state[pinz]:
                    self.player.trigger('gpio'+str(pin))
                self.state[pinz] = True
            else:
                self.state[pinz] = False

        for pin in self.pins:
            # print(self.nameP, "channel", pin, "watched")
            self.state[pin] = False
            GPIO.add_event_detect(pin, GPIO.BOTH, callback=clbck, bouncetime=DEBOUNCE)

        while self.isRunning():
            sleep(0.1)

        self.isRunning(False)
        return
