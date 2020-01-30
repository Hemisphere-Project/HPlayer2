from ..module import Module
import os
import threading, functools
from pathlib import Path

from core import overlays

class BasePlayer(Module):

    _running = threading.Event()
    _running.set()

    name = "Base Player"
    settingspath = None

    doLog = {
        'cmds':     False
    }

    _validExt = []

    _events = {} 
    _overlays = {}
    _status = {
        'isPlaying':    False,
        'isPaused':     False,
        'media':        None,
        'time':         0
    }


    def __init__(self, hplayer, name):
        super().__init__(hplayer, name, 'magenta')

        hplayer.settings.on('volume',       self._applyVolume)
        hplayer.settings.on('mute',         self._applyVolume)
        hplayer.settings.on('pan',          self._applyPan)
        hplayer.settings.on('audiomode',    self._applyPan)
        hplayer.settings.on('flip',         self._applyFlip)

        hplayer.playlist.on('end',          self.stop)                      # Playlist end -> stop
        self.on('end',                      hplayer.playlist.onMediaEnd)    # Media end -> trig playlist


    def addOverlay(self, olay, args=[]):
        OverlayClass = overlays.getOverlay(olay)
        self._overlays[olay] = OverlayClass()
        return self._overlays[olay]

    def getOverlay(self, name):
        if name in self._overlays.keys():
            return self._overlays[name]
        return None


    # CHECK EXT
    def validExt(self, filename):
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

    # STATUS Get
    def status(self):
        return self._status.copy()

    def isPlaying(self):
        return self._status['isPlaying']

    def isPaused(self):
        return self._status['isPaused']

    #
    # Player CONTROLS
    #

    # START
    def start(self):
        # for olay in self._overlays.values():
        #     olay.start()
        self.isRunning(True)
        self._start()

    # QUIT
    def quit(self):
        # for olay in self._overlays.values():
        #     olay.quit()
        self._quit()
        self.isRunning(False)

    
    # Play Media
    def play(self, media):
        self._play(media)
        self._status['media'] = media
        self._status['time'] = 0
        self.emit('playing', media)

    # STOP Playback
    def stop(self):
        self._stop()
        self._status['media'] = None
        self._status['time'] = 0
        self.emit('stopped')

    # PAUSE Playback
    def pause(self):
        self._pause()
        self.emit('paused')

    # RESUME Playback
    def resume(self):
        self._resume()
        self.emit('resumed')

     # SEEK to position
    def seekTo(self, milli):
        self._seekTo(milli)
        self.emit('seekedto', milli)

    #
    # Player INTERNAL actions: Methods to overwrite !
    #

    def _start(self):
        self.log("start")

    def _quit(self):
        self.log("quit")

    def _play(self, path):
        self._status['isPlaying'] = True
        self.log("play", path)

    def _stop(self):
        self._status['isPlaying'] = False
        self.log("stop")

    def _pause(self):
        self._status['isPaused'] = True
        self.log("pause")

    def _resume(self):
        self._status['isPaused'] = False
        self.log("resume")

    def _seekTo(self, milli):
        self.log("seek to", milli)

    def _applyVolume(self, volume, settings):
        if not settings['mute']:
            self.log("volume set to", volume)
        else:
            self.log("volume muted")

    def _applyPan(self, pan, settings):
        if settings['audiomode'] == 'mono':
            self.log("audio mode is mono")
        else:
            self.log("pan set to", pan)

    def _applyFlip(self, flip, settings):
        if flip:
            self.log("screen flipped")
        else:
            self.log("screen not flipped")
