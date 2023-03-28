from .base import BaseInterface
import RPi.GPIO as GPIO
from threading import Timer

class GpioInterface (BaseInterface):
    
    name = "GPIO"

    def __init__(self, hplayer, pins_watch=[], debounce=200, antispike=100, pullupdown='PUP'):
        super().__init__(hplayer, self.name)

        self._state = {}
        self._pinsIN = []
        self._pinsOUT = []
        self._antispike = antispike
        self._debounce = debounce
        self._pupdown = pullupdown
        self._antispikeTimer = None
        GPIO.setmode(GPIO.BCM)
        
        for pin in pins_watch:
            self.watch(pin)


    def postponedChange(self, pin, value):
        name = [p for p in self._pinsIN if p[0] == pin][0][1]
        
        if value:
            if self._state[pin]:
                self.emit(name+'-off')
            self.emit(name+'-on')
            self.emit(name, 1)
        else:
            if not self._state[pin]:
                self.emit(name+'-on')
            self.emit(name+'-off')
            self.emit(name, 0)
        
        self._state[pin] = value
        self._antispikeTimer = None


    def onchange(self, pin):
        value = not GPIO.input(pin) if self._pupdown == 'PUP' else GPIO.input(pin)      
        # print("-- channel", pin, "triggered", value)
        
        # An event was almost triggered: cancel it and forget it
        #
        if self._antispikeTimer:
            self._antispikeTimer.cancel()
            self._antispikeTimer = None
            if value == self._state[pin]:
                self.log('event aborted by antispike (', self._antispike, ' ms)')
                return
        
        if self._antispike > 0:
            # Postpone value change (prevent spike trigger)
            self._antispikeTimer = Timer(self._antispike/1000, self.postponedChange, (pin, value))
            self._antispikeTimer.start()
        else:
            self.postponedChange(pin, value)

    # GPIO receiver THREAD
    def listen(self):
        self.log("starting GPIO listener")
        self.stopped.wait()
        GPIO.cleanup()
        
        
    # GPIO set
    def set(self, pinz, state):
        
        if not isinstance(pinz, list): 
            pinz = [pinz]
        
        for pin in pinz:
            
            # Create name if missing
            if not isinstance(pin, tuple):
                pin = (pin, str(pin))
            
            # Can't set if already an INPUT 
            if self.isInput(pin):
                self.log("GPIO", pin, "is already set as INPUT only... can't set it!")
                return
            
            # Create pin if it does not exists yet
            if not self.isOutput(pin):
                self._pinsOUT.append(pin)
                GPIO.setup(pin[0], GPIO.OUT)            
                
            if (str(state).lower() == 'on' or str(state).lower() == 'up'):    state=True
            if (str(state).lower() == 'off' or str(state).lower() == 'down'): state=False
            GPIO.output(pin[0], state)
            self._state[pin[0]] = GPIO.input(pin[0])
        
    
    # GPIO get
    def get(self, pin):
        
        if isinstance(pin, tuple):   # Tuple provided: search only with pin N°
            pin = pin[0]
        if not isinstance(pin, int): # Name provided: find pin N°
            pin = [p[0] for p in self._pinsIN if p[1] == pin][0]
        
        # PIN never used, set as input (but without watcher)
        if not self.isInput(pin) and not self.isOutput(pin):        
            if self._pupdown == 'PUP':
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            elif self._pupdown == 'PDOWN':
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            else:
                GPIO.setup(pin, GPIO.IN)
        
        # PIN is Input
        if self.isInput(pin):
            self._state[pin] = not GPIO.input(pin) if self._pupdown == 'PUP' else GPIO.input(pin)
        else:
            self._state[pin] = GPIO.input(pin)
        return self._state[pin]
    
    
    
    def isInput(self, pin):
        if isinstance(pin, tuple):  # Tuple provided: search only with pin N°
            pin = pin[0]
        if isinstance(pin, int):
            return pin in [p[0] for p in self._pinsIN]  # Search by pin N°
        else:
            return pin in [p[1] for p in self._pinsIN]  # Search by pin Name
    
    
    def isOutput(self, pin):
        if isinstance(pin, tuple):  # Tuple provided: search only with pin N°
            pin = pin[0]
        if isinstance(pin, int):
            return pin in [p[0] for p in self._pinsOUT]  # Search by pin N°
        else:
            return pin in [p[1] for p in self._pinsOUT]  # Search by pin Name
    
    
    # GPIO watch: pin or tuple (pin, name)
    def watch(self, pin):
        
        # Create name if missing
        if not isinstance(pin, tuple):
            pin = (pin, str(pin))
        
        # Can't watch if already an OUTPUT 
        if self.isOutput(pin):
            self.log("GPIO", pin[0], "is already set as OUTPUT... can't watch it !")
            return
        
        if self.isInput(pin):
            self.log("GPIO", pin[0], "is already set as INPUT... can't watch it again !")
            return
        
        self._pinsIN.append(pin)
        if self._pupdown == 'PUP':
            GPIO.setup(pin[0], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        elif self._pupdown == 'PDOWN':
            GPIO.setup(pin[0], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        else:
            GPIO.setup(pin[0], GPIO.IN)
            
        self._state[pin[0]] = False
        GPIO.add_event_detect(pin[0], GPIO.BOTH, callback=self.onchange, bouncetime=self._debounce)