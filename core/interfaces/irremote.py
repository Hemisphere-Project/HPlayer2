from .base import BaseInterface
from evdev import InputDevice, categorize, ecodes
from time import sleep
import sys

class IrremoteInterface (BaseInterface):

    def __init__(self, player):

        # Interface settings
        super(IrremoteInterface, self).__init__(player, "IRremote")

        self.remote = InputDevice("/dev/input/event0")
        self.remote.grab()


    # Remote receiver THREAD
    def listen(self):
        self.log("starting IRremote listener")

        while self.isRunning():
            event = self.remote.read_one()
            if event and event.type == ecodes.EV_KEY:

                if event.code == ecodes.KEY_VOLUMEUP:
                    if event.value == 1:
                        for i in range(5):
                            self.player.volume_inc()

                elif event.code == ecodes.KEY_VOLUMEDOWN:
                    if event.value == 1:
                        for i in range(5):
                            self.player.volume_dec()

                elif event.code == ecodes.KEY_MUTE:
                    if event.value == 1:
                        self.player.mute_toggle()

                elif event.code == ecodes.KEY_PLAYPAUSE:
                    if event.value == 1:
                        if self.player.isPlaying():
                            self.player.pause()
                        elif self.player.isPaused():
                            self.player.resume()
                        else:
                            self.player.play()

                elif event.code == ecodes.KEY_STOPCD:
                    if event.value == 1:
                        self.player.stop()

                elif event.code == ecodes.KEY_NEXTSONG:
                    if event.value == 1:
                        self.player.next()

                elif event.code == ecodes.KEY_PREVIOUSSONG:
                    if event.value == 1:
                        self.player.prev()


                else:
                    self.log("Unbinded event:", categorize(event))
            else:
                sleep(0.1)

        self.remote.ungrab()



    # # KEY PRESS event
    # def on_press(key):
    #     try:
    #         self.log('alphanumeric key {0} pressed'.format(key.char))
    #     except AttributeError:
    #         self.log('special key {0} pressed'.format(key))
    #
    #
    # # KEY RELEASE event
    # def on_release(key):
    #     self.log('{0} released'.format(key))
    #     if key == keyboard.Key.esc:
    #         # Stop listener
    #         return False
