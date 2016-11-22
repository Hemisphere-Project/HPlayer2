from __future__ import print_function
from termcolor import colored
from time import sleep
from interfaces.base import BaseInterface
import RPi.GPIO as GPIO

DEBOUNCE = 200

class GpioInterface (BaseInterface):

    def  __init__(self, player, pins):

        super(GpioInterface, self).__init__(player)

        self.name = "GPIO "+player.name
        self.nameP = colored(self.name,'blue')

        self.pins = pins
        GPIO.setmode(GPIO.BCM)
        for pin in pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down = GPIO.PUD_UP)

        self.start()


    # HTTP receiver THREAD
    def receive(self):

        print(self.nameP, "starting GPIO listener")
        GPIO.add_event_detect(24, GPIO.FALLING, callback=lambda:self.player.trigger('gpio'+str(24)), bouncetime=DEBOUNCE)

        while self.isRunning():
            sleep(0.1)

        self.isRunning(False)
        return
