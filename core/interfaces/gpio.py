from .base import BaseInterface
import RPi.GPIO as GPIO

class GpioInterface (BaseInterface):

    def __init__(self, hplayer, pins_watch=[], debounce=50, pullupdown='PUP'):
        super().__init__(hplayer, "GPIO")

        self._state = {}
        self._pinsIN = []
        self._pinsOUT = []
        self._debounce = debounce
        self._pupdown = pullupdown
        GPIO.setmode(GPIO.BCM)
        
        for pin in pins_watch:
            self.watch(pin)

    def onchange(self, pin):
        #self.log("channel", pin, "triggered")
        value = not GPIO.input(pin) if self._pupdown == 'PUP' else GPIO.input(pin)       
        if value:
            if self._state[pin]:
                self.emit(str(pin)+'-off')
            self.emit(str(pin)+'-on')
            self.emit(str(pin), 1)
            self._state[pin] = True
        else:
            if not self._state[pin]:
                self.emit(str(pin)+'-on')
            self.emit(str(pin)+'-off')
            self.emit(str(pin), 0)
            self._state[pin] = False


    # GPIO receiver THREAD
    def listen(self):
        self.log("starting GPIO listener")
        self.stopped.wait()
        GPIO.cleanup()
        
        
    # GPIO set
    def set(self, pin, state):
        
        # Can't set if already an INPUT 
        if pin in self._pinsIN:
            self.log("GPIO", pin, "is already set as INPUT only... can't set it!")
            return
        
        # Create pin if it does not exists yet
        if pin not in self._pinsOUT:
            self._pinsOUT.append(pin)
            GPIO.setup(pin, GPIO.OUT)            
            
        if (str(state).lower() == 'on' or str(state).lower() == 'up'):    state=True
        if (str(state).lower() == 'off' or str(state).lower() == 'down'): state=False
        GPIO.output(pin, state)
        self._state[pin] = GPIO.input(pin)
        
    
    # GPIO get
    def get(self, pin):
        
        # PIN never used, set as input (but without watcher)
        if pin not in self._pinsIN and pin not in self._pinsOUT:        
            if self._pupdown == 'PUP':
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            elif self._pupdown == 'PDOWN':
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            else:
                GPIO.setup(pin, GPIO.IN)
        
        # PIN is Input
        if pin in self._pinsIN:
            self._state[pin] = not GPIO.input(pin) if self._pupdown == 'PUP' else GPIO.input(pin)
        else:
            self._state[pin] = GPIO.input(pin)
        return self._state[pin]
    
    
    # GPIO watch
    def watch(self, pin):
        
        # Can't watch if already an OUTPUT 
        if pin in self._pinsOUT:
            self.log("GPIO", pin, "is already set as OUTPUT... can't watch it !")
            return
        
        if pin in self._pinsIN:
            self.log("GPIO", pin, "is already set as INPUT... can't watch it again !")
            return
        
        self._pinsIN.append(pin)
        if self._pupdown == 'PUP':
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        elif self._pupdown == 'PDOWN':
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        else:
            GPIO.setup(pin, GPIO.IN)
            
        self._state[pin] = False
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=self.onchange, bouncetime=self._debounce)