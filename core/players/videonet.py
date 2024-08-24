from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
from stupidArtnet import StupidArtnet
import numpy as np
import cv2 as cv
import time
from .base import BasePlayer

class VideonetPlayer(BasePlayer):

    # MATRIX
    _target_size = (36, 108)
    _target_ratio = _target_size[0] / _target_size[1]
    _screen_offset = (0, 0)

    # INTERNALS
    _last_frame_time = 0
    _frame_interval = 1/30.0
    _cap = None
    _capLock = threading.Lock()

    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)

        self._videoExt = ['mp4', 'm4v', 'mkv', 'avi', 'mov', 'flv', 'mpg', 'wmv', '3gp', 'webm']
        self._imageExt = ['jpg', 'jpeg', 'gif', 'png', 'tif', 'tiff']

        self._validExt = self._videoExt + self._imageExt

        self._thread = None	
        self._runflag = threading.Event()	

        # ARTNET
        self._output = StupidArtnet("192.168.1.12")


    ############
    ## private METHODS
    ############

    # Wait for next frame
    def _waitFrame(self):
        nextDueTime = self._last_frame_time + self._frame_interval * cv.getTickFrequency()
        remainingTime = int( (nextDueTime - cv.getTickCount()) * 1000 / cv.getTickFrequency() )
        
        # sleep for the remaining time
        if remainingTime > 3:
            # print(f"Sleeping for {remainingTime-3} ms")
            cv.waitKey(remainingTime-3)

        # busyloop for the remaining time
        # remainingTime = int( (nextDueTime - cv.getTickCount()) * 1000 / cv.getTickFrequency() )
        # print (f"Busylooping for {remainingTime} ms")
        while cv.getTickCount() < nextDueTime:
            continue

        # Late ?
        late_by = (cv.getTickCount() - nextDueTime) / cv.getTickFrequency()
        if late_by > 0.001 and self._last_frame_time > 0:
            self.log(f"WARNING: Late by { int(late_by*1000) } ms")


    # Resize Frame
    def _resizeFrame(self, frame):
        h, w, _ = frame.shape
        frame_ratio = w / h

        if frame_ratio > self._target_ratio:
            # crop horizontally
            new_w = int(h * self._target_ratio)
            offset = (w - new_w) // 2   
            frame = frame[:, offset:offset+new_w]
        else:
            # crop vertically
            new_h = int(w / self._target_ratio)
            offset = (h - new_h) // 2
            frame = frame[offset:offset+new_h, :]

        return cv.resize(frame, self._target_size, interpolation=cv.INTER_AREA)
    
    # artnet Frame
    def _frame2artnet(self, frame):
        # Crop and resize frame
        matrixO = self._resizeFrame(frame)

        # reverse Red and Blue before flatten (3rd dimension)
        matrix = cv.cvtColor(matrixO, cv.COLOR_BGR2RGB)

        # flip vertically even columns (ZigZag pattern)
        for i in range(1, matrix.shape[1], 2):
            matrix[:, i] = np.flip(matrix[:, i], axis=0)

        # rotate 90°
        matrix = np.rot90(matrix)

        # flip vertically
        matrix = np.flip(matrix, axis=0)

        # reshape (flatten) matrix to 1D array 
        artnet = np.reshape(matrix, (1,-1))[0]

        # split artnet into 510 byte universe (!! 512 crop last pixel !!)
        artnet = [artnet[i:i+510] for i in range(0, len(artnet), 510)]

        # fill up each universe with 0
        for i in range(len(artnet)):
            artnet[i] = np.pad(artnet[i], (0, 512 - len(artnet[i])))

        return artnet
    
    # draw artnet
    def _drawArtnet(self, artnet):
        for i in range(len(artnet)):
            self._output.set_universe(i)
            self._output.set(artnet[i])
            self._output.show()

    # draw black
    def _blackout(self):
        artnet = np.zeros(self._target_size[0]*self._target_size[1]*3, dtype=np.uint8)
        artnet = [artnet[i:i+510] for i in range(0, len(artnet), 510)]
        for i in range(len(artnet)):
            artnet[i] = np.pad(artnet[i], (0, 512 - len(artnet[i])))
        self._drawArtnet(artnet)


    # VNET THREAD
    def _vnet_thread(self):
        
        self.update('isReady', True)
        self.emit('ready')	
        self.emit('status', self.status())

        self.log("player ready")

        while self.isRunning():	
            
            if not self._cap or not self._runflag.isSet():     # not playing or paused           
                time.sleep(0.01)
            
            else:
                ret = None

                # read frame
                if self._cap.isOpened():
                    with self._capLock:
                        try:
                            ret, frame = self._cap.read()
                        except Exception as e:
                            ret = False
                        if not ret: self._cap.release()

                # media stopped
                if not ret:
                    self._stop()
                    continue

                artnet = self._frame2artnet(frame)

                if self._last_frame_time == 0:
                    self.update('isPlaying', True)
                    self.update('isPaused', False)
                    self.emit('playing')

                # wait for next frame
                self._waitFrame()
                
                # send artnet
                self._drawArtnet(artnet)

                self._last_frame_time = cv.getTickCount()
                self.update('time', round(self._cap.get(cv.CAP_PROP_POS_MSEC)/1000,2))

        self.isRunning(False)	
        return	        
        


    ##########
    ## Inherited "abstract" METHODS overloads
    ##########

    #
    # Start the player:
    #   - start thread
    #
    def _start(self):

        # Playback thread	
        self._thread = threading.Thread(target=self._vnet_thread)	
        self._thread.start()

    #
    # Exit the player
    #   - stop thread
    #
    def _quit(self):
        self._stop()
        self.isRunning(False)
        if self._thread:
            # self.log("stopping process thread")
            self._thread.join()
        self.log("done")


    def _play(self, path, pause=False):
        self._stop()
        self.log("play", path)

        # OPEN VIDEO
        with self._capLock:
            self._cap = cv.VideoCapture(path)
            fps = self._cap.get(cv.CAP_PROP_FPS)
            frame_count = int(self._cap.get(cv.CAP_PROP_FRAME_COUNT))

        self._frame_interval = 1.0/fps

        if pause: self._pause()
        else: self._resume()

        # print(f"PLAY {path} - FPS: {fps} - Frames: {frame_count} - DURATION: {frame_count/fps} sec")
        # print(f"Frame interval: { int(frame_interval*1000) } ms")

        self.update('duration', round(frame_count/fps,2))



    def _stop(self):
        self._blackout()
        if self._cap:
            end = False   
            with self._capLock:
                if self._cap.isOpened():
                    self._cap.release()
                else: 
                    end = True
                self._cap = None
            self._runflag.clear()
            self.update('isPlaying', False)
            self.update('isPaused', False)
            if end:
                self.emit('media-end')
            self.emit('stopped')

    def _pause(self):
        if self._runflag.isSet() and self._cap:
            self._runflag.clear()
            self.update('isPlaying', False)
            self.update('isPaused', True)
            self.emit('paused')

    def _resume(self):
        if self._cap:
            self._last_frame_time = 0
            self._runflag.set()
            self.update('isPlaying', True)
            self.update('isPaused', False)
            self.emit('playing')

    def _seekTo(self, milli):
        if self._cap:
            with self._capLock:
                self._cap.set(cv.CAP_PROP_POS_MSEC, milli)
                self._last_frame_time = 0
            self.log("seek to", milli/1000)

    def _skip(self, milli):
        if self._cap:
            with self._capLock:
                pos = self._cap.get(cv.CAP_PROP_POS_MSEC)
                self._cap.set(cv.CAP_PROP_POS_MSEC, pos + milli)
                self._last_frame_time = 0
            self.log("skip", milli/1000)



