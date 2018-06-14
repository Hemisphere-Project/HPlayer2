from __future__ import print_function

from termcolor import colored
from time import sleep
import sys

from evdev import InputDevice, categorize, ecodes

from base import BaseInterface


class IrremoteInterface (BaseInterface):

    def __init__(self, player, args):

        # Interface settings
        super(IrremoteInterface, self).__init__(player)
        self.name = "IRremote "+player.name
        self.nameP = colored(self.name,'blue')

        self.remote = InputDevice("/dev/input/event0")
        self.remote.grab()

        self.start()

    # Remote receiver THREAD
    def receive(self):
        print(self.nameP, "starting IRremote listener")

        while self.isRunning():
            event = self.remote.read_one()
            if event and event.type == ecodes.EV_KEY:

                if event.code == ecodes.KEY_VOLUMEUP:
                    if event.value == 1:
                        self.player.volume_inc()

                elif event.code == ecodes.KEY_VOLUMEDOWN:
                    if event.value == 1:
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
                    print(self.nameP, "Unbinded event:", categorize(event))
            else:
                sleep(0.1)

        self.remote.ungrab()

        self.isRunning(False)
        return

    # KEY PRESS event
    def on_press(key):
        try:
            print(self.nameP, 'alphanumeric key {0} pressed'.format(key.char))
        except AttributeError:
            print(self.nameP, 'special key {0} pressed'.format(key))

    # KEY RELEASE event
    def on_release(key):
        print(self.nameP, '{0} released'.format(key))
        if key == keyboard.Key.esc:
            # Stop listener
            return False
