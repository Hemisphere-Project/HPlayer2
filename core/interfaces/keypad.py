from .base import BaseInterface
import importlib
from time import sleep
import os

LCD = None
_LCD_IMPORT_ERROR = None
try:
    LCD = importlib.import_module("Adafruit_CharLCD")
except ImportError as err:
    _LCD_IMPORT_ERROR = err


class MockLCD:
    """Mock LCD class for when hardware is not available"""
    def __init__(self, logger=None):
        self.logger = logger
        self.display = ["                ", "                "]  # 2 lines of 16 chars
        self.cursor_col = 0
        self.cursor_row = 0
        self.last_log_time = 0
        self.last_display = ["", ""]
        
    def set_color(self, r, g, b):
        pass
    
    def set_cursor(self, col, row):
        self.cursor_col = col
        self.cursor_row = row
    
    def write8(self, value, char_mode=True):
        if char_mode and self.cursor_row < 2:
            char = chr(value) if 32 <= value <= 126 else '?'
            # Replace character at cursor position
            line = list(self.display[self.cursor_row])
            if self.cursor_col < 16:
                line[self.cursor_col] = char
                self.display[self.cursor_row] = ''.join(line)
                self.cursor_col += 1
    
    def is_pressed(self, button):
        return False
    
    def create_char(self, location, pattern):
        pass
    
    def log_display(self):
        """Log the current display state periodically"""
        import time
        current_time = time.time()
        
        # Check if display changed
        display_changed = (self.display[0] != self.last_display[0] or 
                          self.display[1] != self.last_display[1])
        
        # Only log if something actually changed
        if display_changed:
            if self.logger:
                self.logger(f"[MockLCD] ╔════════════════╗")
                self.logger(f"[MockLCD] ║{self.display[0]}║")
                self.logger(f"[MockLCD] ║{self.display[1]}║")
                self.logger(f"[MockLCD] ╚════════════════╝")
            
            self.last_display = [self.display[0], self.display[1]]
            self.last_log_time = current_time


class KeypadInterface (BaseInterface):

    display = ["", ""]
    
    CHAR_WIFI   = '\x00'
    CHAR_PEERS  = '\x01'
    CHAR_VOL    = '\x02'
    CHAR_PLAY   = '\x03'
    CHAR_STOP   = '\x04'
    CHAR_LOVE   = '\x05'

    def __init__(self, hplayer):
        if _LCD_IMPORT_ERROR:
            raise RuntimeError("Adafruit_CharLCD is required for KeypadInterface") from _LCD_IMPORT_ERROR
        if LCD is None:
            raise RuntimeError("Adafruit_CharLCD is unavailable for KeypadInterface")
        super(KeypadInterface, self).__init__(hplayer, "KEYPAD")
        
        # Initialize buttons and LCD hardware
        self.buttons = None
        self.hardware_available = False
        
        # Try to initialize the LCD hardware
        try:
            self.lcd = LCD.Adafruit_CharLCDPlate()
            self.lcd.set_color(0, 0, 0)
            
            # Define buttons only when LCD is available
            self.buttons = ( (LCD.SELECT, 'select',     (1,1,1)),
                            (LCD.LEFT,   'left'  ,  (1,0,0)),
                            (LCD.UP,     'up'    ,  (0,0,1)),
                            (LCD.DOWN,   'down'  ,  (0,1,0)),
                            (LCD.RIGHT,  'right' ,  (1,0,1)) )
            
            # special chars # http://www.quinapalus.com/hd44780udg.html
            self.lcd.create_char(0, [0,0,28,6,27,13,21,0])      #  CHAR_WIFI
            self.lcd.create_char(1, [27,27,27,0,27,27,27,0])    #  CHAR_PEERS
            self.lcd.create_char(2, [2,3,2,2,14,30,12,0])       #  CHAR_VOL
            self.lcd.create_char(3, [0,8,12,14,12,8,0,0])       #  CHAR_PLAY
            self.lcd.create_char(4, [0,0,14,14,14,0,0,0])     #  CHAR_STOP
            self.lcd.create_char(5, [31,17,10,4,10,31,31,0])     #  CHAR_LOVE
            
            self.hardware_available = True
            self.log("LCD hardware initialized successfully")
            
        except (OSError, IOError) as err:
            # Hardware not available (I2C communication failed)
            self.lcd = MockLCD(logger=self.log)
            self.log(f"LCD hardware not available, running in disabled mode: {err}")
        except Exception as err:
            # Any other hardware initialization error
            self.lcd = MockLCD(logger=self.log)
            self.log(f"LCD initialization failed, running in disabled mode: {err}")

    def set_color(self, r, g, b):
        """Safe wrapper for LCD color setting"""
        self.lcd.set_color(r, g, b)

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
        if not self.hardware_available: 
            # For MockLCD, still update the display and log it
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
            # Trigger periodic logging
            self.lcd.log_display()
            return
            
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
        if not self.hardware_available:
            self.log("KEYPAD hardware not available, button input disabled (MockLCD display active)")
            # Keep the listener running for MockLCD display updates
            while self.isRunning():
                self.draw()  # Update the MockLCD display
                sleep(0.5)   # Update every 500ms for MockLCD
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

            if self.buttons:
                for btn in self.buttons:
                    processBtn(btn)
                
            self.draw()

            sleep(0.04)
        
        if self.hardware_available:
            self.lcd.set_color(0, 0, 0)
