from ..module import Module
import os
import threading, functools
from pathlib import Path

from core import overlays

class BasePlayer(Module):

    def __init__(self, hplayer, name):
        super().__init__(hplayer, name, 'magenta')
        self.hplayer = hplayer

        self._running = threading.Event()
        self._running.set()

        self.doLog = {
            'recv': False,
            'cmds': False
        }
        
        
        self.logQuietEvents.append('status')  # Do not log status events

        self._validExt = []

        self._events = {} 
        self._overlays = {}
        
        self._status = {
            'isReady':      False,
            'isPlaying':    False,
            'isPaused':     False,
            'media':        None,
            'time':         0,
            'duration':     0,
            'speed':        1.0
        }


    def addOverlay(self, olay, *argv):
        OverlayClass = overlays.getOverlay(olay)
        self._overlays[olay] = OverlayClass(self.hplayer, *argv)
        return self._overlays[olay]

    def getOverlay(self, name):
        if name in self._overlays.keys():
            return self._overlays[name]
        return None


    # CHECK EXT
    def validExt(self, filename):
        # self.log('testing', filename, 'against', self._validExt)
        if os.path.basename(filename).startswith('.'):
            return False
        if '*' in self._validExt:
            return True
        if filename.lower().split('.')[-1] in self._validExt:
            return True
        return False


    #
    # Player STATUS
    #

    # Status SET 
    def update(self, key, value):
        self._status[key] = value
        self.emit('status', key, value)  

    # SET/GET is running
    def isRunning(self, state=None):
        # SET (optionnal)
        if state is not None:
            self._running.set() if state else self._running.clear()
        # GET
        for olay in self._overlays.values():
            if not olay.isRunning():
                return False
        return self._running.is_set()

    # STATUS Set/Get
    def status(self, entry=None):
        s = self._status.copy()
        if entry:
            return s[entry]
        return s

    def isPlaying(self):
        return self._status['isPlaying'] or self._status['isPaused']

    def isPaused(self):
        return self._status['isPaused']

    def position(self):
        return self._status['time']

    #
    # Player CONTROLS
    #

    # START
    def start(self):
        for olay in self._overlays.values():
            olay.start()
        self.isRunning(True)
        self._start()

    # QUIT
    def quit(self):
        for olay in self._overlays.values():
            olay.quit()
        self._quit()
        self.isRunning(False)

    
    # Play Media
    def play(self, media, pause=False):
        self.update('isPaused', False)
        self._play(media, pause)
        self.update('media', media)
        self.update('time', 0)

    # STOP Playback
    def stop(self):
        self._stop()
        self.update('isPaused', False)
        self.update('media', None)
        self.update('time', 0)

    # PAUSE Playback
    def pause(self):
        self.update('isPaused', True)
        self._pause()

    # RESUME Playback
    def resume(self):
        self.update('isPaused', False)
        self._resume()

     # SEEK to position
    def seekTo(self, milli):
        self._seekTo(milli)

    # SKIP time
    def skip(self, milli):
        self._skip(milli)

    # SET speed
    def speed(self, s):
        if s != self._status['speed']:
            self.update('speed', s)
            self._speed(s)

    #
    # Player INTERNAL actions: Methods to overwrite !
    #

    def _start(self):
        self.log("start")

    def _quit(self):
        self.log("quit")

    def _play(self, path, pause=False):
        self.log("play", path)
        self.emit('playing', path)
        if pause: self._pause()

    def _stop(self):
        self.log("stop")
        self.emit('stopped')

    def _pause(self):
        self.log("pause")
        self.emit('paused')

    def _resume(self):
        self.log("resume")
        self.emit('resumed')

    def _seekTo(self, milli):
        self.log("seek to", milli)
        self.emit('seekedto', milli)

    def _skip(self, milli):
        self.log("skip", milli)
        self.emit('skipped', milli)

    def _applyVolume(self, volume):
        self.log("volume set to", volume)

    def _applyPan(self, pan):
        self.log("pan set to", pan)

    def _applyFlip(self, flip):
        self.log("screen flip", flip)

    def _applyOneLoop(self, oneloop):
        self.log("one loop", oneloop)
