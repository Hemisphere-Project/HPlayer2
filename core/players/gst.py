from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
import time
from .base import BasePlayer
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst


class GstPlayer(BasePlayer):

    _gst_scale = 1          # % image scale
    _gst_imagetime = 5      # diaporama transition time (s)

    _thread_handle = None
    
    _state = Gst.State.NULL
    _seek_enabled = False
    _time = 0
    _duration = 0
    _file = None
    

    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)

        self._videoExt = ['mp4', 'm4v', 'mkv', 'avi', 'mov', 'flv', 'mpg', 'wmv', '3gp', 'webm']
        self._audioExt = ['mp3', 'aac', 'wma', 'wav', 'flac', 'aif', 'aiff', 'm4a', 'ogg', 'opus']
        self._imageExt = ['jpg', 'jpeg', 'gif', 'png', 'tif', 'tiff']

        self._validExt = self._videoExt + self._audioExt #+ self._imageExt
        
        Gst.init(None)
        


    ############
    ## public METHODS
    ############

    def scale(self, sc):
        self._gst_scale = sc

    def imagetime(self, it):
        self._gst_imagetime = it

    ############
    ## private METHODS
    ############    
    
    def _gst_on_message(self, bus, message):
        t = message.type
        
        if t == Gst.MessageType.EOS:
            self.update('isPaused', False)
            self.update('isPlaying', False)
            print('END')
            self.emit('media-end', self.status('media'))
            self._clear()
            
        elif t == Gst.MessageType.ERROR:
            self.playbin.set_state(Gst.State.NULL)
            err, debug = message.parse_error()
            print("Error: %s" % err, debug)
            print("- ENDED")
            self.stop()
            
        elif t == Gst.MessageType.DURATION_CHANGED:
            print("Duration changed")
            self._duration = 0
            
        elif t == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.playbin:
                print("Pipeline state changed from '{0:s}' to '{1:s}'".format(
                    Gst.Element.state_get_name(old_state),
                    Gst.Element.state_get_name(new_state)))

                if new_state == Gst.State.PLAYING:
                    self.emit('playing', self.status('media'))
                    # print("- PLAYING")

                    # we just moved to the playing state
                    query = Gst.Query.new_seeking(Gst.Format.TIME)
                    if self.playbin.query(query):
                        fmt, self._seek_enabled, start, end = query.parse_seeking()
                        
                self._state = new_state      
            
            
    def _gst_thread(self):
        try:
            bus = self.playbin.get_bus()
            self.log("thread ready")
            
            self.update('isReady', True)
            self.emit('ready')
            
            while self.isRunning():
                msg = bus.timed_pop_filtered(
                    100 * Gst.MSECOND,
                    (Gst.MessageType.STATE_CHANGED | Gst.MessageType.ERROR
                        | Gst.MessageType.EOS | Gst.MessageType.DURATION_CHANGED)
                )

                # parse message
                if msg:
                    self._gst_on_message(bus, msg)
                    
                else:
                    # we got no message. this means the timeout expired 
                    
                    # DURATION
                    if self._duration <= 0:
                        (ret, dur) = self.playbin.query_duration(Gst.Format.TIME)
                        if ret:
                            self.update('duration', round(float(dur/Gst.SECOND),2))

                    # POSITION
                    else:        
                        (ret, cur) = self.playbin.query_position(Gst.Format.TIME)
                        if ret:
                            self.update('time', round(float(cur/Gst.SECOND),2))
                            
        finally:
            self.isRunning(False)
        


    ##########
    ## Inherited "abstract" METHODS overloads
    ##########

    #
    # Start the player:
    #   - instantiate mpv subprocess
    #   - connect IPC socket i/o
    #
    def _start(self):

        self.playbin = Gst.ElementFactory.make("playbin", "player")
        self.playbin.set_property("video-sink", Gst.ElementFactory.make("kmssink", "videosink"))
        self.playbin.set_property("audio-sink", Gst.ElementFactory.make("autoaudiosink", "audiosink"))
        self.log("pipeline created")
        
        self._thread_handle = threading.Thread(target=self._gst_thread)
        self._thread_handle.start()
        
        self._clear()



    #
    # Exit the player
    #   - stop subprocess
    #   - close IPC socket
    #
    def _quit(self):
        self.isRunning(False)

        if  self._thread_handle:
            # self.log("stopping process thread")
            self._thread_handle.join()
        
        self.log("stopped")


    def _play(self, path):
        self.update('isPaused', False)
        if self._state != Gst.State.NULL:
            self.stop()
            
        self.playbin.set_property("uri", "file://" + path)
        self.playbin.set_state(Gst.State.PLAYING)
        print("* PLAYING", path)
    
    def _clear(self):
        self._seek_enabled = False
        self._time = 0
        self._duration = 0
        self._file = None
        self._state = Gst.State.NULL
        print("* CLEARED")

    def _stop(self, join=False):
        wasPlaying = self.status('isPlaying')
        self.update('isPaused', False)
        if self._state != Gst.State.NULL:
            self.playbin.set_state(Gst.State.NULL)
            while join:
                ret, state, pending = self.playbin.get_state(Gst.CLOCK_TIME_NONE)
                if state == Gst.State.NULL: 
                    break   # TODO: ice breaker !
            print("* STOPPED")
            self.emit('stopped', self.status('media'))
        self._clear()
        # if not wasPlaying:
        #     self.emit('stopped')    # already stopped, so manually trigger event

    def _pause(self):
        self.update('isPaused', True)
        self.playbin.set_state(Gst.State.PAUSED)
        self.emit('paused', self.status('media'))
        print("* PAUSED")

    def _resume(self):
        self.update('isPaused', False)
        self.playbin.set_state(Gst.State.PLAYING)
        print("* RESUMED")

    def _seekTo(self, milli):
        self.log("seek to", milli/1000, self._status['duration'])
        # TODO


    def _skip(self, milli):
        if self._status['time'] + milli/1000 < self._status['duration']:
            # TODO
            pass
        # self.log("seek to", milli/1000)

    def _speed(self, s):
        # TODO
        # self.log("speed to", s)
        pass

    def _applyVolume(self, volume):
        # TODO
        # self.log("VOLUME to", volume)
        pass

    def _applyPan(self, pan):
        if pan == 'mono':
            # TODO    
            self.log("MONO")    
        else:
            left = pan[0]/100.0
            right = pan[1]/100.0
            # TODO
            self.log("PAN to", left, right, '{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')
    
    def _applyFlip(self, flip):
        if flip:
            # TODO
            pass
        else:
            # TODO
            pass

    def _applyOneLoop(self, oneloop):
        # TODO
        pass