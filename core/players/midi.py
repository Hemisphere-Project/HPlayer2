from __future__ import print_function	
from termcolor import colored	
import socket, threading, subprocess, os, json, select, sys	
from time import sleep	
from .base import BasePlayer	
import mido	

class MidiPlayer(BasePlayer):	

   _validExt = ['mid']	


   def __init__(self, hplayer, name):	
      super(MidiPlayer, self).__init__(hplayer, name)	
      self._mido_thread = None	
      self._midiFile = None	
      self._runflag = threading.Event()	

   def log(self, *argv):	
      print(self.nameP, *argv)	

   ############	
   ## private METHODS	
   ############	

   # MIDO playback THREAD	
   def _mido_playback(self):	

      midiIfaces = mido.get_output_names()	

      self.log('interfaces detected:', midiIfaces)	
      # self._output = mido.open_output('Virtual Raw MIDI 1-0:VirMIDI 1-0 20:0')	

      for iface in midiIfaces:	
         if 'Virtual Raw MIDI' in iface:	
               self._output = mido.open_output(iface)	
               self.log('connecting to', iface)	
               break	

      self.emit('player-ready')	

      while self.isRunning():	

         self._runflag.wait()	
         try:	
            msg = next(self._midiFile)	

            if msg.is_meta:	
               # self.log('META', msg)	
               pass	
            else:	
               pausetime = msg.time	
               while pausetime > 0:	
                  if not self._status['isPlaying']: 	
                        break	
                  doSleep = min(0.01, pausetime)	
                  if not self._status['isPaused']: 	
                        pausetime -= doSleep	
                  sleep(doSleep)	

               if not self.isRunning(): break	

               if self._runflag.is_set() and self._status['isPlaying']:	
                  self.log(msg)	
                  self._output.send(msg)	

         except StopIteration:	
            self.stop()	
            self.emit('end')	

         except TypeError:	
            self.log('malformed message')	
         # except:	
         #     if self.isRunning():	
         #         self.log('ERROR:', sys.exc_info()[0])	
         #         self.isRunning(False)	
         #     else:	
         #         break	


      self.log("mido thread stopped")	
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
      self._stop()	
      self._runflag.set()	

      if self._mido_thread:	
         self.log("stopping process thread")	
         self._mido_thread.join()	
      self.log("done.")	


   def _play(self, path):	
      self.log("play", path)	
      self._runflag.clear()	
      self._midiFile = iter(mido.MidiFile(path))	
      self._status['isPlaying'] = True	
      self._status['isPaused'] = False	
      self._runflag.set()	

   def _stop(self):	
      self.log("stop")	
      self._runflag.clear()	
      self._midiFile = None	
      self._status['isPlaying'] = False	
      self._status['isPaused'] = False	

   # def _pause(self):	
   #     self._mpv_send('{ "command": ["set_property", "pause", true] }')	
   #     self._status['isPaused'] = True	

   # def _resume(self):	
   #     self._mpv_send('{ "command": ["set_property", "pause", false] }')	
   #     self._status['isPaused'] = False	

   # def _seekTo(self, milli):	
   #     self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "absolute"] }')	
   #     # self.log("seek to", milli/1000)	

   # def _applyVolume(self):	
   #     vol = self._settings['volume']	
   #     if self._settings['mute']:	
   #         vol = 0	
   #     self._mpv_send('{ "command": ["set_property", "volume", '+str(vol)+'] }')	
   #     self.log("VOLUME to", vol)	

