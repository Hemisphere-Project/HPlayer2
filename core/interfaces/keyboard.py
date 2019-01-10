from .base import BaseInterface
from evdev import InputDevice, categorize, ecodes
from time import sleep
import sys

class KeyboardInterface (BaseInterface):

    def __init__(self, player):

        # Interface settings
        super(KeyboardInterface, self).__init__(player, "Keyboard")

        try:
            self.remote = InputDevice("/dev/input/event0")
            self.remote.grab()
        except:
            self.log("Keyboard not found ...")
            self.remote = None

    # Remote receiver THREAD
    def listen(self):
        if not self.remote:
            return

        self.log("starting Keyboard listener")

        while self.isRunning():
            event = self.remote.read_one()
            if event and event.type == ecodes.EV_KEY:

                keycode = ecodes.KEY[event.code]
                keymode = ''

                # KEY Event 1
                if event.value == 1:
                    keymode = 'down'
                elif event.value == 2:
                    keymode = 'hold'
                elif event.value == 0:
                    keymode = 'up'

                self.player.trigger('key-'+keymode, event.code)
                self.player.trigger(keycode+'-'+keymode)

                # self.log("keyboard event:", categorize(event), event.value)
                # self.log("keyboard event:", categorize(event), event.value)

            elif not event:
            	sleep(0.1)

        self.remote.ungrab()


    def asIRremote(self):

        # Volume UP
        def volup():
            self.player.mute(False)
            self.player.volume_inc()
        self.player.on(['KEY_VOLUMEUP-down', 'KEY_VOLUMEUP-hold'], volup )

        # Volume DOWN
        def voldown():
            self.player.mute(False)
            self.player.volume_inc()
        self.player.on(['KEY_VOLUMEDOWN-down', 'KEY_VOLUMEDOWN-hold'], voldown )

        # Mute
        self.player.on(['KEY_MUTE-down'], self.player.mute_toggle )

        # Loop NO
        self.player.on(['KEY_COMMA-down'], lambda: self.player.loop(0) )

        # Loop ONE
        self.player.on(['KEY_A-down'], lambda: self.player.loop(1) )

        # Loop ALL
        self.player.on(['KEY_D-down'], lambda: self.player.loop(2) )

        def playpause():
            if self.player.isPlaying():
                self.player.pause()
            elif self.player.isPaused():
                self.player.resume()
            else:
                self.player.play()
        self.player.on(['KEY_PLAYPAUSE-down'], playpause)

        self.player.on(['KEY_STOPCD-down'], self.player.stop )
        self.player.on(['KEY_NEXTSONG-down'], self.player.next )
        self.player.on(['KEY_PREVIOUSSONG-down'], self.player.prev )


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
