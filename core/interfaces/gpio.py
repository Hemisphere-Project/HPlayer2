from .base import BaseInterface
import RPi.GPIO as GPIO

class GpioInterface (BaseInterface):

    def __init__(self, player, pins, debounce=50):
        super(GpioInterface, self).__init__(player, "GPIO")

        self._state = {}
        self._pins = pins
        self._debounce = debounce
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pins, GPIO.IN, pull_up_down=GPIO.PUD_UP)


    # GPIO receiver THREAD
    def listen(self):
        self.log("starting GPIO listener")

        def clbck(pinz):
            #self.log("channel", pinz, "triggered")
            if not GPIO.input(pinz):
                # if not self._state[pinz]:
                self.player.trigger('gpio'+str(pinz)+'-on')
                self.player.trigger('gpio'+str(pinz), 1)
                self._state[pinz] = True
            else:
                #if self._state[pinz]:
                self.player.trigger('gpio'+str(pinz)+'-off')
                self.player.trigger('gpio'+str(pinz), 0)
                self._state[pinz] = False

        for pin in self._pins:
            # self.log("channel", pin, "watched")
            self._state[pin] = False
            GPIO.add_event_detect(pin, GPIO.BOTH, callback=clbck, bouncetime=self._debounce)

        self.stopped.wait()
