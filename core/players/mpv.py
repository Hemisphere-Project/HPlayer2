from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
import time
from shutil import which
from .base import BasePlayer

class MpvPlayer(BasePlayer):

    _mpv_scale = 1          # % image scale
    _mpv_imagetime = 5      # diaporama transition time (s)
    
    _mpv_command = ['--idle=yes', '-v', '--no-osc', '--msg-level=ipc=v', '--quiet', '--fs','--keep-open' ,'--hr-seek=yes', '--ao=alsa' ]

    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)

        self._videoExt = ['mp4', 'm4v', 'mkv', 'avi', 'mov', 'flv', 'mpg', 'wmv', '3gp', 'webm']
        self._audioExt = ['mp3', 'aac', 'wma', 'wav', 'flac', 'aif', 'aiff', 'm4a', 'ogg', 'opus']
        self._imageExt = ['jpg', 'jpeg', 'gif', 'png', 'tif', 'tiff']

        self._validExt = self._videoExt + self._audioExt + self._imageExt
        

        self._mpv_procThread = None
        self._mpv_sock = None
        self._mpv_sock_connected = False
        self._mpv_recvThread = None
        self._mpv_socketpath = '/tmp/hplayer-' + name

        self._mpv_lockedout = 0


    ############
    ## public METHODS
    ############

    # Window scale (must be called before starting process)
    def scale(self, sc):
        self._mpv_scale = sc

    def imagetime(self, it):
        self._mpv_imagetime = it

    ############
    ## private METHODS
    ############

    # MPV Process THREAD
    def _mpv_watchprocess(self):

        # stdout watcher
        poll_obj = select.poll()
        poll_obj.register(self._mpv_subproc.stdout, select.POLLIN)

        # Watcher loop
        while not self._mpv_subproc.poll() and self.isRunning():
            poll_result = poll_obj.poll(0.5)
            if poll_result:
                out = self._mpv_subproc.stdout.readline()
                if out.strip():
                    # self.log("subproc says", out.strip())
                    pass
            # else:
            #     time.sleep(0.1)          ## TODO turn into ASYNC !!


        if self._mpv_subproc.poll():
            self._mpv_subproc.terminate()
            if not self._mpv_subproc.poll():
                self.log("process terminated")
            else:
                self._mpv_subproc.kill()
                self.log("process killed")
        else:
            self.log("process closed")

        self.isRunning(False)
        return


    # MPV ipc receive THREAD
    def _mpv_communicate(self):

        # Socket IPC to process
        self._mpv_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for retry in range(50, 0, -1):
            try:
                self._mpv_sock.connect(self._mpv_socketpath)
                self._mpv_sock.settimeout(0.2)
                self.log("connected to player backend")
                self._mpv_sock_connected = True
                self.update('isReady', True)
                self.emit('ready')
                break
            except socket.error as e:
                if retry == 1:
                    print (self.nameP, "socket error:", e)
                    self.isRunning(False)
                else:
                    print (self.nameP, "retrying socket connection..")
                    time.sleep(0.2)

        if self._mpv_sock_connected:

            # Listener
            self._mpv_send('{ "command": ["observe_property", 1, "idle"] }')
            self._mpv_send('{ "command": ["observe_property", 2, "core-idle"] }')
            self._mpv_send('{ "command": ["observe_property", 3, "time-pos"] }')
            self._mpv_send('{ "command": ["observe_property", 4, "duration"] }')
            self._mpv_send('{ "command": ["observe_property", 5, "eof-reached"] }')
            
            self.emit('status', self.status())

            # Receive
            while self.isRunning():
    
                # Listen socket
                try:
                    msg = self._mpv_sock.recv(4096)
                    assert len(msg) != 0, "socket disconnected"
                    # print(len(msg))

                    self.doLog['recv'] = False
                    self.doLog['cmds'] = False

                    if self.name == 'player2':
                        self.log("IPC says:", msg.rstrip())
                    
                    # Message received
                    for event in msg.rstrip().split( b"\n" ):
                        try:
                            mpvsays = json.loads(event)
                        except:
                            #self.log("IPC invalid json:", event)
                            pass
                        
                        if 'name' in mpvsays:
                            # print(mpvsays)
                            
                            if mpvsays['name'] == 'idle':
                                self.emit('idle')

                            elif mpvsays['name'] == 'core-idle':
                                self.update('isPlaying', not mpvsays['data'])

                                if self.status('isPlaying'): 
                                    self.emit('playing', self.status('media'))
                                    # self.log('play')

                                elif self.status('isPaused'): 
                                    self.emit('paused', self.status('media'))
                                    # self.log('pause')

                                else: 
                                    # print('STOP')
                                    self.emit('stopped', self.status('media'))    # DO NOT emit STOPPED HERE -> STOP SHOULD BE TRIGGERED AFTER MEDIA-END
                                    # self.log('stop')  # also Triggered with oneloop
                                    
                                self._mpv_lockedout = 0

                            elif mpvsays['name'] == 'time-pos':
                                if 'data' in mpvsays and mpvsays['data']:
                                    self.update('time', round(float(mpvsays['data']),2))

                            elif mpvsays['name'] == 'duration':
                                if 'data' in mpvsays and mpvsays['data']:
                                    self.update('duration', round(float(mpvsays['data']),2))

                            elif mpvsays['name'] == 'eof-reached':
                                if 'data' in mpvsays and mpvsays['data'] == True:
                                    self.update('isPaused', False)
                                    self.update('isPlaying', False)
                                    print('END')
                                    self.emit('media-end', self.status('media'))
                                    
                            else:
                                pass
                        
                        if 'name' in mpvsays and mpvsays['name'] == 'time-pos':
                            self._mpv_lockedout = 0
                            # print('#', end ="")

                        if self.doLog['recv']:
                            if 'name' not in mpvsays or mpvsays['name'] != 'time-pos':
                                self.log("IPC event:", mpvsays)

                        # print(self.status('media'))
                # Timeout: retry
                except socket.timeout:
                    # print('-', end ="")
                    if self.status('isPlaying'):
                        if not self.status('media').split('.')[-1].lower() in self._imageExt:
                            self.log('PLAYBACK LOCKED OUT', self._mpv_lockedout)
                            if self._mpv_lockedout == 0:
                                self._mpv_send('{ "command": ["set_property", "pause", false] }')
                            if self._mpv_lockedout == 1:
                                print("CRASH RELOAD FILE", self.status('media'))
                                self._mpv_send('{ "command": ["stop"] }')
                                time.sleep(0.5)
                                self._mpv_send('{"command": ["loadfile", "'+self.status('media')+'"]}')
                            self._mpv_lockedout += 1
                            if self._mpv_lockedout > 3:
                                print("CRASH STOP")
                                self._mpv_send('{ "command": ["stop"] }')
                                os.system('pkill mpv')
                                self.emit('hardreset')
                    pass

                # Socket error: exit
                except (socket.error, AssertionError) as e:
                    if self.isRunning():
                        self.log(e)
                        self.isRunning(False)

        self._mpv_sock.close()
        self._mpv_sock_connected = False
        self.log("socket closed")
        self.isRunning(False)
        return


    # MPV ipc send
    def _mpv_send(self, msg):
        if self._mpv_sock_connected:
            try:
                self._mpv_sock.send( (msg+'\n').encode() )
                if self.doLog['cmds']:
                    self.log("cmds:", msg)
            except socket.error:
                self.log("socket send error:", msg)
                self.isRunning(False)
        else:
            self.log("socket not connected, can't send \""+msg+"\"")


    ##########
    ## Inherited "abstract" METHODS overloads
    ##########

    #
    # Start the player:
    #   - instantiate mpv subprocess
    #   - connect IPC socket i/o
    #
    def _start(self):

        # create subprocess
        script_path = os.path.dirname(os.path.realpath(__file__))
        
        command = ['mpv', '--input-ipc-server=' + self._mpv_socketpath + '' ,'--window-scale=' + str(self._mpv_scale) ] + self._mpv_command
        
        # self.log("starting mpv with", command)

        # image time (0 = still image)
        if self._mpv_imagetime > 0:
            command.append('--image-display-duration=' + str(self._mpv_imagetime))
        else:
            command.append('--image-display-duration=inf')
        
        # Special command for RockPro64
        if os.path.exists('/usr/local/bin/rkmpv'):
            command[0] = 'rkmpv'
            
        # Local mpv
        elif which('mpv') is None:
            command[0] = os.path.dirname(os.path.realpath(__file__))+'/../../bin/mpv'
        
        self._mpv_subproc = subprocess.Popen(command,
                            stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr = subprocess.STDOUT,
                            bufsize = 1, universal_newlines = True)

        # Watch subprocess
        self._mpv_procThread = threading.Thread(target=self._mpv_watchprocess)
        self._mpv_procThread.start()

        # Socket IPC connect
        self._mpv_recvThread = threading.Thread(target=self._mpv_communicate)
        self._mpv_recvThread.start()

        # Wait for socket to be connected
        self.log("waiting for socket connection")
        while not self._mpv_sock_connected:
            time.sleep(0.1)
            if not self.isRunning():
                break

    #
    # Exit the player
    #   - stop subprocess
    #   - close IPC socket
    #
    def _quit(self):
        self.isRunning(False)

        if self._mpv_procThread:
            # self.log("stopping process thread")
            self._mpv_procThread.join()

        if self._mpv_recvThread:
            # self.log("stopping socket thread")
            self._mpv_recvThread.join()
        
        self.log("stopped")

    def _play(self, path, pause=False):
        event = "play"
        if pause: event += "pause"
        # self.log(event, path, time.time()*1000000)
        self._mpv_send('{ "command": ["stop"] }')
        
        self.update('isPaused', pause)
        self.log("isPaused", self.status('isPaused'))
        self._mpv_send('{ "command": ["loadfile", "'+path+'"] }')
        
        if pause:
            self._mpv_send('{ "command": ["set_property", "pause", true] }')
        else:
            self._mpv_send('{ "command": ["set_property", "pause", false] }')
        

    def _stop(self):
        wasPlaying = self.status('isPlaying')
        self._mpv_send('{ "command": ["stop"] }')
        # if not wasPlaying:
        #     self.emit('stopped')    # already stopped, so manually trigger event

    def _pause(self):
        self._mpv_send('{ "command": ["set_property", "pause", true] }')

    def _resume(self):
        self.log("resume")
        self._mpv_send('{ "command": ["set_property", "pause", false] }')

    def _seekTo(self, milli):
        self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "absolute", "keyframes"] }')
        self.log("seek to", milli/1000, self._status['duration'])


    def _skip(self, milli):
        if self._status['time'] + milli/1000 < self._status['duration']:
            self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "relative"] }')
        # self.log("seek to", milli/1000)

    def _speed(self, s):
        self._mpv_send('{ "command": ["set_property", "speed", '+str(s)+'] }')
        # self.log("speed to", s)

    def _applyVolume(self, volume):
        self._mpv_send('{ "command": ["set_property", "volume", '+str(volume)+'] }')
        # self.log("VOLUME to", volume)

    def _applyPan(self, pan):
        if pan == 'mono':
            self._mpv_send('{"command": ["set_property", "af", "lavfi=[pan=stereo|c0=.5*c0+.5*c1|c1=.5*c0+.5*c1]"]}')        
            self.log("MONO")    
        else:
            left = pan[0]/100.0
            right = pan[1]/100.0
            self._mpv_send('{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')
            self.log("PAN to", left, right, '{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')
    
    def _applyFlip(self, flip):
        if flip:
            self._mpv_send('{ "command": ["vf", "del", "mirror"] }')
            self._mpv_send('{ "command": ["vf", "add", "mirror"] }')
        else:
            self._mpv_send('{ "command": ["vf", "del", "mirror"] }')
            pass

    def _applyOneLoop(self, oneloop):
        self._mpv_send('{ "command": ["set_property", "loop", ' + ('"inf"' if oneloop else '"no"') +'] }')