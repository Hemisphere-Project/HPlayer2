from __future__ import print_function

from termcolor import colored
from time import sleep
import os

import Adafruit_CharLCD as LCD

from base import BaseInterface


class KeypadInterface (BaseInterface):

    state = {}

    buttons = ( (LCD.SELECT, 'Select', (1,1,1)),
                (LCD.LEFT,   'Left'  , (1,0,0)),
                (LCD.UP,     'Up'    , (0,0,1)),
                (LCD.DOWN,   'Down'  , (0,1,0)),
                (LCD.RIGHT, 'Right' , (1,0,1)) )

    def __init__(self, player, args):
# else:
                #     self.player.load()
                #     self.
        super(KeypadInterface, self).__init__(player)

        self.name = "KEYPAD "+player.name
        self.nameP = colored(self.name,'blue')

        self.lcd = LCD.Adafruit_CharLCDPlate()
        self.lcd.set_color(0, 0, 0)

        self.start()
# else:
                #     self.player.load()
                #     self.
    # GPIO receiver THREAD
    def receive(self):
        print(self.nameP, "starting KEYPAD listener")

        display = ""
        display_l = ""

        pressed = dict()
        pressed['UP'] = False
        pressed['DOWN'] = False
        pressed['RIGHT'] = False
        pressed['LEFT'] = False
        pressed['SEL'] = False

        while self.isRunning():
            if self.lcd.is_pressed(LCD.UP):
                self.player.volume_inc()

            if self.lcd.is_pressed(LCD.DOWN):
                self.player.volume_dec()

            if self.lcd.is_pressed(LCD.RIGHT) and pressed['RIGHT'] == 0:
                self.player.next()
                pressed['RIGHT'] = 8
            elif pressed['RIGHT'] > 0:
                pressed['RIGHT']-=1

            if self.lcd.is_pressed(LCD.LEFT) and pressed['LEFT'] == 0:
                self.player.prev()
                pressed['LEFT'] = 8
            elif pressed['LEFT'] > 0:
                pressed['LEFT']-=1

            if self.lcd.is_pressed(LCD.SELECT) and pressed['SEL'] == 0:
                if self.player.isPlaying():
                    self.player.stop()
                # else:
                #     self.player.load()
                #     self.player.play()
                pressed['SEL'] = 10
                # print(self.nameP, "pressed SEL")
            elif pressed['SEL'] > 0:
                pressed['SEL']-=1
                # print(self.nameP, "release SEL")


            display = ""
            if self.player.isPlaying() and self.player.status()['media']:
                display = os.path.basename(self.player.status()['media'])[:-4]
                display += "  \"" + str(int(self.player.status()['time']))
            else:
                display = "-stop-"
            display += "\n" + 'VOLUME: '+str(self.player.status()['volume'])

            if display != display_l:
                self.lcd.clear()
                self.lcd.message( display )
                display_l = display

            sleep(0.05)

        self.isRunning(False)
        return
