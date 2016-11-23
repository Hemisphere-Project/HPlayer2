from __future__ import print_function
from termcolor import colored
from time import sleep
from interfaces.base import BaseInterface
import RPi.GPIO as GPIO

DEBOUNCE = 50

class GpioInterface (BaseInterface):

    state = {}

    def  __init__(self, player, pins):

        super(GpioInterface, self).__init__(player)

        self.name = "GPIO "+player.name
        self.nameP = colored(self.name,'blue')

        self.pins = pins
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pins, GPIO.IN, pull_up_down = GPIO.PUD_UP)

        self.start()


    # HTTP receiver THREAD
    def receive(self):

        print(self.nameP, "starting GPIO listener")

        def clbck(pin):
            #print(self.nameP, "channel", channel, "triggered")
            if not GPIO.input(pin):
                if not self.state[pin]:
                    self.player.trigger('gpio'+str(pin))
                self.state[pin] = True
            else:
                self.state[pin] = False

        for pin in self.pins:
            #print(self.nameP, "channel", pin, "watched")
            self.state[pin] = False
            GPIO.add_event_detect(pin, GPIO.BOTH, callback=clbck, bouncetime=DEBOUNCE)

        while self.isRunning():
            sleep(0.1)

        self.isRunning(False)
        return
