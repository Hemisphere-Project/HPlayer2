from .base import BaseInterface
from evdev import InputDevice, categorize, ecodes
from watchdog.observers import Observer                 # python3-watchdog ?
from watchdog.events import FileSystemEventHandler
import sys, subprocess
import time

millis = lambda: int(round(time.time() * 1000))

class KeyboardInterface (BaseInterface):

    def __init__(self, hplayer):

        # Interface settings
        super(KeyboardInterface, self).__init__(hplayer, "Keyboard")

        # keyboard connection watchdog
        event_handler = FileSystemEventHandler()
        event_handler.on_created = self.bind
        event_handler.on_deleted = self.unbind
        self.observer = Observer()
        self.observer.schedule(event_handler, '/dev/input/', recursive=False)
        self.observer.start()
        self.remote = None

        self.holdDebounce = 5

        self.bind(self.detect())
        

    # Find Keyboard
    def detect(self):
        kbd = subprocess.Popen("ls -la /dev/input/by-id/ | grep event-kbd | awk -F \"/\" '{print $NF}' ", shell=True, stdout=subprocess.PIPE).stdout.read().decode("utf-8").strip()
        if kbd:
            return '/dev/input/'+kbd
        else:
            return None

    # Bind to interface
    def bind(self, iface):
        if iface and not isinstance(iface, str):
            iface = iface.src_path
        if iface != self.detect(): return

        try:
            self.remote = InputDevice(iface)
            self.remote.grab()
            self.log("Keyboard connected ...")
        except:
            e = sys.exc_info()[0]
            self.remote = None
            self.log("Keyboard not found ...", e)

    def unbind(self, iface):
        if not isinstance(iface, str):
            iface = iface.src_path
        if iface != self.detect(): return
        self.remote = None
        self.log("Keyboard disconnected ...")

    # Remote receiver THREAD
    def listen(self):

        self.log("starting Keyboard listener")
        self.lastHold = 0

        while self.isRunning():
            if not self.remote:
                time.sleep(0.5)
                continue

            try:
                event = self.remote.read_one()
                if event and event.type == ecodes.EV_KEY:

                    keycode = ecodes.KEY[event.code]
                    keymode = ''

                    # KEY Event 1
                    if event.value == 1:
                        keymode = 'down'
                    elif event.value == 2:
                        if millis() - self.lastHold > self.holdDebounce:
                            keymode = 'hold'
                            self.lastHold = millis()
                    elif event.value == 0:
                        keymode = 'up'

                    # self.emit('key-'+keymode, event.code)
                    if keymode:
                        self.emit(keycode+'-'+keymode)

                    # self.log("keyboard event:", categorize(event), event.code, event.value)
                    # self.log("keyboard event:", keycode+'-'+keymode)

                elif not event:
                	time.sleep(0.05)

            except:
                time.sleep(0.5)

        if self.remote:
            self.remote.ungrab()


    # def asIRremote(self):

    #     # Volume UP
    #     @self.on('KEY_VOLUMEUP-down')
    #     @self.on('KEY_VOLUMEUP-hold')
    #     def volup():
    #         self.hplayer.mute(False)
    #         self.hplayer.volume_inc()

    #     # Volume DOWN
    #     def voldown():
    #         self.hplayer.mute(False)
    #         self.hplayer.volume_inc()
    #     self.hplayer.on(['KEY_VOLUMEDOWN-down', 'KEY_VOLUMEDOWN-hold'], voldown )

    #     # Mute
    #     self.hplayer.on(['KEY_MUTE-down'], self.hplayer.mute_toggle )

    #     # Loop NO
    #     self.hplayer.on(['KEY_COMMA-down'], lambda: self.hplayer.loop(0) )

    #     # Loop ONE
    #     self.hplayer.on(['KEY_A-down'], lambda: self.hplayer.loop(1) )

    #     # Loop ALL
    #     self.hplayer.on(['KEY_D-down'], lambda: self.hplayer.loop(2) )

    #     def playpause():
    #         if self.hplayer.isPlaying():
    #             self.hplayer.pause()
    #         elif self.hplayer.isPaused():
    #             self.hplayer.resume()
    #         else:
    #             self.hplayer.play()
    #     self.hplayer.on(['KEY_PLAYPAUSE-down'], playpause)

    #     self.hplayer.on(['KEY_STOPCD-down'], self.hplayer.stop )
    #     self.hplayer.on(['KEY_NEXTSONG-down'], self.hplayer.next )
    #     self.hplayer.on(['KEY_PREVIOUSSONG-down'], self.hplayer.prev )


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
