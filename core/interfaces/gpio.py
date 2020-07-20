from .base import BaseInterface
import RPi.GPIO as GPIO

class GpioInterface (BaseInterface):

    def __init__(self, player, pins, debounce=50):
        super(GpioInterface, self).__init__(player, "GPIO")

        self._pins = pins
        
        self._state = {}
        self._debounce = {}
        self._ghost = {}
        
        for pin in self._pins:
            self._state[pin] = False
            self._ghost[pin] = True
            self._debounce[pin] = debounce
            
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pins, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Disable Ghost (ghost: when trigger on, simulate off if missing, and reverse)
    def disableGhost(self, pin):
        self._ghost[pin] = False

    def debouncePin(self, pin, debounce):
        self._debounce[pin] = debounce

    def readPin(self, pin):
        return GPIO.input(pin)

    # GPIO receiver THREAD
    def listen(self):
        self.log("starting GPIO listener")

        def clbck(pinz):
            # self.log("channel", pinz, "triggered", GPIO.input(pinz))
            if not GPIO.input(pinz):
                if self._ghost[pin] and self._state[pinz]:
                    self.player.trigger('gpio'+str(pinz)+'-off')
                self.player.trigger('gpio'+str(pinz)+'-on')
                self.player.trigger('gpio'+str(pinz), 1)
                self._state[pinz] = True
            else:
                if self._ghost[pin] and not self._state[pinz]:
                    self.player.trigger('gpio'+str(pinz)+'-on')
                self.player.trigger('gpio'+str(pinz)+'-off')
                self.player.trigger('gpio'+str(pinz), 0)
                self._state[pinz] = False

        for pin in self._pins:
            # self.log("channel", pin, "watched")
            if self._debounce[pin] > 0:
                GPIO.add_event_detect(pin, GPIO.BOTH, callback=clbck, bouncetime=self._debounce[pin])
            else:
                GPIO.add_event_detect(pin, GPIO.BOTH, callback=clbck)

        self.stopped.wait()
