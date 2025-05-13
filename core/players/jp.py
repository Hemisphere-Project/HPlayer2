from just_playback import Playback
import threading
import time
from .base import BasePlayer

class JpPlayer(BasePlayer):

    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)
        
        self._validExt = ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a']  # Supported audio formats
        self.playback = None
        self._position_thread = None
        self._run_flag = threading.Event()

    ############
    ## Internal Thread & Callbacks
    ############
    
    def _position_updater(self):
        lastDuration = 0
        lastTime = -1
        
        """Thread to monitor playback position and status"""
        while self.isRunning() and self.playback and self.playback.active:
            try:
                # Detect end of media
                if not self.playback.playing and not self.playback.paused:
                    self._handle_media_end()
                    break
                
                # Update current time
                current_pos = self.playback.curr_pos
                if current_pos != lastTime:
                    self.update('time', round(current_pos, 2))
                    lastTime = current_pos
                
                # Update duration if available
                if self.playback.duration:
                    if self.playback.duration != lastDuration:
                        lastDuration = self.playback.duration
                        self.update('duration', round(lastDuration, 2))
                
                time.sleep(0.1)
                
            except Exception as e:
                self.log("Position updater error:", str(e))
                self.playback.stop()
                self._handle_media_end()
                break

    def _handle_media_end(self):
        """Handle end of playback"""
        self.update('isPlaying', False)
        self.update('isPaused', False)
        self.emit('media-end', self.status('media'))
        self.emit('stopped', self.status('media'))
        self.playback = None

    ##########
    ## BasePlayer Abstract Methods Implementation
    ##########

    def _start(self):
        """Initialize playback system"""
        self._run_flag.set()
        self.update('isReady', True)
        self.emit('ready')

    def _quit(self):
        """Clean up resources"""
        self._run_flag.clear()
        if self.playback:
            self.playback.stop()
        if self._position_thread:
            self._position_thread.join()
        self.playback = None

    def _play(self, path, pause=False):
        """Start playing a file"""
        try:
            if self.playback:
                self.playback.stop()
                
            self.playback = Playback()
            self.playback.load_file(path)
            
            # Start position monitoring thread
            self._position_thread = threading.Thread(target=self._position_updater)
            self._position_thread.daemon = True
            self._position_thread.start()
            
            if pause:
                self.playback.pause()
                self.update('isPaused', True)
                self.emit('paused', self.status('media'))
            else:
                self.playback.play()
                self.update('isPlaying', True)
                self.update('isPaused', False)
                self.emit('playing', self.status('media'))
                
            self.update('media', path)
            self.update('time', 0)
            
        except Exception as e:
            self.log("Play error:", str(e))
            self._handle_media_end()

    def _stop(self):
        """Stop playback"""
        if self.playback:
            self.playback.stop()
            self._handle_media_end()

    def _pause(self):
        """Pause playback"""
        if self.playback and self.playback.playing:
            self.playback.pause()
            self.update('isPlaying', False)
            self.update('isPaused', True)
            self.emit('paused', self.status('media'))

    def _resume(self):
        """Resume playback"""
        if self.playback and self.playback.paused:
            self.playback.resume()
            self.update('isPlaying', True)
            self.update('isPaused', False)
            self.emit('resumed', self.status('media'))

    def _seekTo(self, milli):
        """Seek to specific position"""
        if self.playback and self.playback.duration:
            seconds = milli / 1000
            self.playback.seek(seconds)
            self.update('time', round(seconds, 2))

    def _skip(self, milli):
        """Skip time relative to current position"""
        if self.playback:
            new_pos = self.playback.curr_pos + (milli / 1000)
            self.playback.seek(new_pos)
            self.update('time', round(new_pos, 2))

    def _speed(self, s):
        """Set playback speed"""
        if self.playback:
            try:
                self.playback.set_rate(s)
            except NotImplementedError:
                self.log("Speed change not supported for this file type")

    # Additional audio-specific controls
    def _applyVolume(self, volume):
        """Set volume (0.0-1.0)"""
        if self.playback:
            self.playback.set_volume(volume)