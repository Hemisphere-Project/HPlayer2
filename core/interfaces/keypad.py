from .base import BaseInterface
import Adafruit_CharLCD as LCD
from time import sleep
import os


class KeypadInterface (BaseInterface):

    buttons = ( (LCD.SELECT, 'select',     (1,1,1)),
                (LCD.LEFT,   'left'  ,  (1,0,0)),
                (LCD.UP,     'up'    ,  (0,0,1)),
                (LCD.DOWN,   'down'  ,  (0,1,0)),
                (LCD.RIGHT,  'right' ,  (1,0,1)) )

    display = ["", ""]
    
    CHAR_WIFI   = '\x00'
    CHAR_PEERS  = '\x01'
    CHAR_VOL    = '\x02'
    CHAR_PLAY   = '\x03'
    CHAR_STOP   = '\x04'
    CHAR_LOVE   = '\x05'

    def __init__(self, hplayer):
        super(KeypadInterface, self).__init__(hplayer, "KEYPAD")
        try:
            self.lcd = LCD.Adafruit_CharLCDPlate()
            self.lcd.set_color(0, 0, 0)
        except:
            self.log("LCD Keypad not found ...")
            self.lcd = None
            return
        
        self.lcd.set_color(0, 0, 0)
        
        # special chars # http://www.quinapalus.com/hd44780udg.html
        self.lcd.create_char(0, [0,0,28,6,27,13,21,0])      #  CHAR_WIFI
        self.lcd.create_char(1, [27,27,27,0,27,27,27,0])    #  CHAR_PEERS
        self.lcd.create_char(2, [2,3,2,2,14,30,12,0])       #  CHAR_VOL
        self.lcd.create_char(3, [0,8,12,14,12,8,0,0])       #  CHAR_PLAY
        self.lcd.create_char(4, [0,0,14,14,14,0,0,0])     #  CHAR_STOP
        self.lcd.create_char(5, [31,17,10,4,10,31,31,0])     #  CHAR_LOVE

    def update(self):
        lines = ["", ""]

        # Line 1 : MEDIA
        if not self.hplayer.statusPlayers()[0]['media']: lines[0] = '-stop-'
        else: lines[0] = os.path.basename(self.hplayer.statusPlayers()[0]['media'])[:-4]
        lines[0] = lines[0].ljust(16, ' ')[:16]

        # Line 2 : VOLUME / TIME
        lines[1] = 'VOLUME: '+str(self.hplayer.settings()['volume'])
        if self.hplayer.statusPlayers()[0]['time'] is not None:
            lines[1] += "  \"" + str(int(self.hplayer.statusPlayers()[0]['time']))
        lines[1] = lines[1].ljust(16, ' ')[:16]

        return lines


    def draw(self, forced=None):
        if not self.lcd: return
        lines = self.update() if not forced else forced
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

        pressed = {}
        
        def processBtn(btn):
            if not btn[1] in pressed:
                pressed[btn[1]] = 0
            
            if self.lcd.is_pressed(btn[0]):
                if pressed[btn[1]] == 0:
                    self.emit(btn[1])
                    pressed[btn[1]] = 5    
                elif pressed[btn[1]] == 1:
                    self.emit(btn[1]+'-hold')
                else:
                    pressed[btn[1]] -= 1
            else:
                if pressed[btn[1]] > 0:
                    self.emit(btn[1]+'-release')        
                pressed[btn[1]] = 0
                

        while self.isRunning():

            for btn in self.buttons:
                processBtn(btn)
                
            self.draw()

            sleep(0.04)
        
        self.lcd.set_color(0, 0, 0)
