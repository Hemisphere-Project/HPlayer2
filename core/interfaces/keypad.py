from .base import BaseInterface
import Adafruit_CharLCD as LCD
from time import sleep
import os


class KeypadInterface (BaseInterface):

    buttons = ( (LCD.SELECT, 'Select', (1,1,1)),
                (LCD.LEFT,   'Left'  , (1,0,0)),
                (LCD.UP,     'Up'    , (0,0,1)),
                (LCD.DOWN,   'Down'  , (0,1,0)),
                (LCD.RIGHT, 'Right' , (1,0,1)) )

    display = ["", ""]

    def __init__(self, player):
        super(KeypadInterface, self).__init__(player, "KEYPAD")

        self.lcd = LCD.Adafruit_CharLCDPlate()

        try:
            self.lcd = LCD.Adafruit_CharLCDPlate()
            self.lcd.set_color(0, 0, 0)
        except:
            self.log("LCD Keypad not found ...")
            self.lcd = None

    def update(self):
        lines = ["", ""]

        # Line 1 : MEDIA
        if not self.player.status()['media']: lines[0] = '-stop-'
        else: lines[0] = os.path.basename(self.player.status()['media'])[:-4]
        lines[0] = lines[0].ljust(16, ' ')[:16]

        # Line 2 : VOLUME / TIME
        lines[1] = 'VOLUME: '+str(self.player.settings()['volume'])
        if self.player.status()['time'] is not None:
            lines[1] += "  \"" + str(int(self.player.status()['time']))
        lines[1] = lines[1].ljust(16, ' ')[:16]

        return lines


    def draw(self):
        lines = self.update()
        if lines[0] != self.display[0]:
            self.display[0] = lines[0]
            self.lcd.set_cursor(0, 0)
            for char in lines[0]:
                self.lcd.write8(ord(char), True)
        if lines[1] != self.display[1]:
            self.display[1] = lines[1]
            self.lcd.set_cursor(0, 1)
            for char in lines[1]:
                self.lcd.write8(ord(char), True)

    def listen(self):
        if not self.lcd:
            return

        self.log("starting KEYPAD listener")

        pressed = dict.fromkeys(['UP', 'DOWN', 'RIGHT', 'LEFT', 'SEL'], 0)
        debounce = 5

        while self.isRunning():

            if self.lcd.is_pressed(LCD.UP) and pressed['UP'] == 0:
                self.player.trigger('keypad-up')
                pressed['UP'] = debounce
            elif pressed['UP'] > 0:
                pressed['UP']-=1

            if self.lcd.is_pressed(LCD.DOWN) and pressed['DOWN'] == 0:
                self.player.trigger('keypad-down')
                pressed['DOWN'] = debounce
            elif pressed['DOWN'] > 0:
                pressed['DOWN']-=1

            if self.lcd.is_pressed(LCD.RIGHT) and pressed['RIGHT'] == 0:
                self.player.trigger('keypad-right')
                pressed['RIGHT'] = debounce
            elif pressed['RIGHT'] > 0:
                pressed['RIGHT']-=1

            if self.lcd.is_pressed(LCD.LEFT) and pressed['LEFT'] == 0:
                self.player.trigger('keypad-left')
                pressed['LEFT'] = debounce
            elif pressed['LEFT'] > 0:
                pressed['LEFT']-=1

            if self.lcd.is_pressed(LCD.SELECT) and pressed['SEL'] == 0:
                self.player.trigger('keypad-select')
                pressed['SEL'] = debounce
            elif pressed['SEL'] > 0:
                pressed['SEL']-=1

            self.draw()

            sleep(0.04)
