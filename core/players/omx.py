from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
from omxplayer.player import OMXPlayer
import time
from .base import BasePlayer

class OmxPlayer(BasePlayer):


    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)

        self._validExt = ['mp4', 'm4v', 'mkv', 'avi', 'mov', 'flv', 'mpg', 'wmv', '3gp', 'mp3', 'aac', 'wma', 'wav', 'flac', 'aif', 'aiff', 'm4a', 'ogg', 'opus', 'webm', 'jpg', 'jpeg', 'gif', 'png', 'tif', 'tiff']

        self._thread = None	
        self._runflag = threading.Event()	
        self.player = None



    ############
    ## private METHODS
    ############

    # MPV THREAD
    def _mpv_thread(self):
        

        self.emit('ready')	
        self.emit('status', self.status())

        self.log("player ready")

        while self.isRunning():	

            self._runflag.wait(0.37)
            if self._runflag.isSet():
                self.update('time', round(self.player.position(),2))
                time.sleep(0.05)

        self.isRunning(False)	
        return	        
        
        
    def _onPlay(self, p):
        self.update('isPlaying', True)
        self.update('isPaused', False)
        self.emit('playing')
        self._runflag.set()
        self.log('play')

    def _onPause(self, p):
        self.update('isPlaying', False)
        self.update('isPaused', True)
        self.emit('paused')
        self._runflag.clear()
        self.log('pause')


    def _onExit(self, p, c):
        self.player._connection._bus.close()
        self.player._connection = None
        self.player = None
        self._runflag.clear()
        self.update('isPlaying', False)
        self.update('isPaused', False)
        self.emit('end')
        self.emit('stopped')
        self.log('stop')



    ##########
    ## Inherited "abstract" METHODS overloads
    ##########

    #
    # Start the player:
    #   - instantiate mpv subprocess
    #   - connect IPC socket i/o
    #
    def _start(self):

        # Playback thread	
        self._thread = threading.Thread(target=self._mpv_thread)	
        self._thread.start()


    #
    # Exit the player
    #   - stop subprocess
    #   - close IPC socket
    #
    def _quit(self):
        self.isRunning(False)
        if self._thread:
            # self.log("stopping process thread")
            self._thread.join()
        self.log("stopped")


    def _play(self, path):
        self.log("play", path)

        if self.player:
            self.player.quit()

        self.player = OMXPlayer(path, dbus_name='org.mpris.MediaPlayer2.omxplayer2')
        self.player.playEvent += self._onPlay
        self.player.pauseEvent += self._onPause
        # self.player.stopEvent += self._onStop
        self.player.exitEvent += self._onExit
        self.player.play()
        # self.player.set_video_pos(0,0,100,100)

        # self.update('duration', round(self.player.duration(),2))



    def _stop(self):
        if self.player:
            self.player.stop()

    def _pause(self):
        if self.player:
            self.player.pause()

    def _resume(self):
        if self.player:
            self.player.play()

    def _seekTo(self, milli):
        if self.player:
            self.player.set_position(milli/1000)
        # self.log("seek to", milli/1000)

    def _skip(self, milli):
        if self._status['time'] + milli/1000 < self._status['duration']:
            if self.player:
                self.player.seek(milli/1000)
        # self.log("skip", milli/1000)

    def _applyVolume(self, volume):
        if self.player:
            self.player.set_volume(volume/10.0)
        self.log("VOLUME to", volume)


