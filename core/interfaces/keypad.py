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
        pressed = dict.fromkeys(['UP', 'DOWN', 'RIGHT', 'LEFT', 'SEL'], False)

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
                self.player.stop()
                # else:
                #     self.player.load()
                #     self.player.play()
                pressed['SEL'] = 10
                # self.log("pressed SEL")
            elif pressed['SEL'] > 0:
                pressed['SEL']-=1
                # self.log("release SEL")

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
