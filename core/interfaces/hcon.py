from .gpio import GpioInterface
import RPi.GPIO as GPIO

class HconInterface (GpioInterface):
    
    hpins = [(5,  'T1'), 
             (6,  'T2'), 
             (13, 'T3'), 
             (19, 'T4'), 
             (26, 'T5'), 
             (17, 'SW1'), 
             (27, 'SW2'), 
             (22, 'SW3')]
    

    def __init__(self, hplayer, pins_watch=[], debounce=1):
        
        self.name = "Hcon"
        
        pins_input=[(17, 'SW1'), 
                    (27, 'SW2'), 
                    (22, 'SW3')]
        
        for inPin in pins_watch:
            for p in self.hpins:
                if inPin == p[0] or inPin == p[1]:
                    pins_input.append( p )
                    break
        
        pins_input = list(set([i for i in pins_input]))  # de-duplicate
        
        super().__init__( hplayer, pins_input, debounce, pullupdown='PUP' )

    
    # GPIO set
    def set(self, pinz, state):
        
        if not isinstance(pinz, list): 
            pinz = [pinz]
        
        pin_set=[]
        for pin in pinz:
            if isinstance(pin, tuple):
                pin_set.append(pin)
            else:
                for p in self.hpins:
                    if pin == p[0] or pin == p[1]:
                        pin_set.append( p )
                        break
            
        super().set(pin_set, state)
    
    
    # GPIO get
    def get(self, pin):
        if isinstance(pin, str):
            for p in self.hpins:
                if pin == p[1]:
                    pin = p[0]
                    break
            
        super().get(pin)