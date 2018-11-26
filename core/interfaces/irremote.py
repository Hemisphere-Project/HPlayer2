from .base import BaseInterface
from evdev import InputDevice, categorize, ecodes
from time import sleep
import sys

class IrremoteInterface (BaseInterface):

    def __init__(self, player):

        # Interface settings
        super(IrremoteInterface, self).__init__(player, "IRremote")

        try:
            self.remote = InputDevice("/dev/input/event0")
            self.remote.grab()
        except:
            self.log("IR Remote dongle not found ...")
            self.remote = None

    # Remote receiver THREAD
    def listen(self):
        if not self.remote:
            return

        self.log("starting IRremote listener")

        while self.isRunning():
            event = self.remote.read_one()
            if event and event.type == ecodes.EV_KEY:

                # Volume UP
                if event.code == ecodes.KEY_VOLUMEUP:
                    if event.value == 1 or event.value == 2:
                        self.player.mute(False)
                        self.player.volume_inc()

                # Volume DOWN
                elif event.code == ecodes.KEY_VOLUMEDOWN:
                    if event.value == 1 or event.value == 2:
                        self.player.mute(False)
                        self.player.volume_dec()

                # Mute
                elif event.code == ecodes.KEY_MUTE:
                    if event.value == 1:
                        self.player.mute_toggle()

                # Loop NO
                elif event.code == ecodes.KEY_COMMA:
                    if event.value == 1:
                        self.player.loop(0)

                # Loop ONE
                elif event.code == ecodes.KEY_A:
                    if event.value == 1:
                        self.player.loop(1)

                # Loop ALL
                elif event.code == ecodes.KEY_D:
                    if event.value == 1:
                        self.player.loop(2)

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


                # self.log("unknown event:", categorize(event), event.value)

            elif not event:
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
