from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
from time import sleep
from .base import BasePlayer
import mido

class MidiPlayer(BasePlayer):

    def __init__(self, name=None):
        super(MidiPlayer, self).__init__()

        if name:
            name = name.replace(" ", "_")
        else:
            import time
            name = 'midi-'+str(time.time())

        self.name = name
        self.nameP = colored("MIDI" ,'magenta')

        self._mido_thread = None
        self._midiFile = None
        self._runflag = threading.Event()


    ############
    ## private METHODS
    ############

    # MIDO playback THREAD
    def _mido_playback(self):

        print(self.nameP, mido.get_output_names())
        self._output = mido.open_output('Integra-7')

        self.trigger('player-ready')

        while self.isRunning():

            self._runflag.wait()
            try:
                msg = next(self._midiFile)
                sleep(msg.time)
                if not msg.is_meta and self._runflag.is_set():
                    self._output.send(msg)
            except StopIteration:
                self._midiFile = None
                self._status['isPaused'] = False
                self.trigger('end-file')
                self._runflag.clear()
            except:
                if self.isRunning():
                    print(self.nameP, 'ERROR:', sys.exc_info()[0])
                    self.isRunning(False)
                else:
                    break
    

        print(self.nameP, "mido thread stopped")
        self.isRunning(False)
        return


    ##########
    ## Inherited "abstract" METHODS overloads
    ##########

    #
    # Start the player:
    #   - instantiate mpv subprocess
    #   - connect IPC socket i/o
    #
    def _start(self):

        # Playback subprocess
        self._mido_thread = threading.Thread(target=self._mido_playback)
        self._mido_thread.start()


    #
    # Exit the player
    #   - stop subprocess
    #   - close IPC socket
    #
    def _quit(self):
        self.isRunning(False)
        self._runflag.set()

        if self._mido_thread:
            # print(self.nameP, "stopping process thread")
            self._mido_thread.join()

        print(self.nameP, "stopped")


    def _play(self, path):
        print(self.nameP, "play", path)
        self._runflag.clear()
        self._midiFile = mido.MidiFile(path)
        self._status['isPaused'] = False
        self._runflag.set()

    def _stop(self):
        self._runflag.clear()
        self._status['isPaused'] = False

    # def _pause(self):
    #     self._mpv_send('{ "command": ["set_property", "pause", true] }')
    #     self._status['isPaused'] = True

    # def _resume(self):
    #     self._mpv_send('{ "command": ["set_property", "pause", false] }')
    #     self._status['isPaused'] = False

    # def _seekTo(self, milli):
    #     self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "absolute"] }')
    #     # print(self.nameP, "seek to", milli/1000)

    # def _applyVolume(self):
    #     vol = self._settings['volume']
    #     if self._settings['mute']:
    #         vol = 0
    #     self._mpv_send('{ "command": ["set_property", "volume", '+str(vol)+'] }')
    #     print(self.nameP, "VOLUME to", vol)

