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

        display = {'new': "", 'last': ""}
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


            display['new'] = ""
            if self.player.status()['media'] is not None:
                display['new'] = os.path.basename(self.player.status()['media'])[:-4]
                if self.player.status()['time'] is not None:
                    display['new'] += "  \"" + str(int(self.player.status()['time']))
            else:
                display['new'] = "-stop-"
            display['new'] += "\n" + 'VOLUME: '+str(self.player.status()['volume'])

            if display['new'] != display['last']:
                self.lcd.clear()
                self.lcd.message( display['new'] )
                display['last'] = display['new']

            sleep(0.02)
