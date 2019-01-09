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

    def __init__(self, player):
        super(KeypadInterface, self).__init__(player, "KEYPAD")

        try:
            self.lcd = LCD.Adafruit_CharLCDPlate()
            self.lcd.set_color(0, 0, 0)
        except:
            self.log("LCD Keypad not found ...")
            self.lcd = None


    def listen(self):
        if not self.lcd:
            return

        self.log("starting KEYPAD listener")

        display = {'line1': "", 'line2': ""}
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

            # Set Line 1 : MEDIA
            if not self.player.status()['media']: media = '-stop-'
            else: media = os.path.basename(self.player.status()['media'])[:-4]
            media = media.ljust(16, ' ')
            if media != display['line1']:
                display['line1'] = media
                self.lcd.set_cursor(0, 0)
                for char in media:
                    self.lcd.write8(ord(char), True)

            # Set Line 2 : VOLUME / TIME
            volumetime = 'VOLUME: '+str(self.player.settings()['volume'])
            if self.player.status()['time'] is not None:
                volumetime += "  \"" + str(int(self.player.status()['time']))
            volumetime = volumetime.ljust(16, ' ')
            if volumetime != display['line2']:
                display['line2'] = volumetime
                self.lcd.set_cursor(0, 1)
                for char in volumetime:
                    self.lcd.write8(ord(char), True)

            sleep(0.04)
