from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
import time
from .base import BasePlayer

class MpvPlayer(BasePlayer):

    _mpv_scale = 1          # % image scale
    _mpv_imagetime = 5      # diaporama transition time (s)

    def __init__(self, hplayer, name):
        super().__init__(hplayer, name)

        self._validExt = ['mp4', 'm4v', 'mkv', 'avi', 'mov', 'flv', 'mpg', 'wmv', '3gp', 'mp3', 'aac', 'wma', 'wav', 'flac', 'aif', 'aiff', 'm4a', 'ogg', 'opus', 'webm', 'jpg', 'jpeg', 'gif', 'png', 'tif', 'tiff']

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
        for retry in range(10, 0, -1):
            try:
                self._mpv_sock.connect(self._mpv_socketpath)
                self._mpv_sock.settimeout(0.5)
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
                    # print (self.nameP, "retrying socket connection..")
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

                    # self.log("IPC says:", msg.rstrip())
                    
                    # Message received
                    for event in msg.rstrip().split( b"\n" ):
                        try:
                            mpvsays = json.loads(event)
                        except:
                            #self.log("IPC invalid json:", event)
                            pass
                        
                        if 'name' in mpvsays:

                            if mpvsays['name'] == 'idle':
                                self.emit('idle')

                            elif mpvsays['name'] == 'core-idle':
                                self.update('isPlaying', not mpvsays['data'])

                                if self.status('isPlaying'): 
                                    self.emit('playing', self.status('media'))
                                    # self.log('play')

                                elif self.status('isPaused'): 
                                    self.emit('paused')
                                    # self.log('pause')

                                else: 
                                    self.emit('stopped')
                                    # self.log('stop')
                                    
                                self._mpv_lockedout = 0

                            elif mpvsays['name'] == 'time-pos':
                                if mpvsays['data']:
                                    self.update('time', round(float(mpvsays['data']),2))

                            elif mpvsays['name'] == 'duration':
                                if mpvsays['data']:
                                    self.update('duration', round(float(mpvsays['data']),2))

                            elif mpvsays['name'] == 'eof-reached' and mpvsays['data'] == True:
                                self.update('isPaused', False)
                                self.update('isPlaying', False)
                                self.emit('end')
                                    
                            else:
                                pass
                        
                        if 'name' in mpvsays and mpvsays['name'] == 'time-pos':
                            self._mpv_lockedout = 0
                            # print('#', end ="")

                        if self.doLog['recv']:
                            if 'name' not in mpvsays or mpvsays['name'] != 'time-pos':
                                self.log("IPC event:", mpvsays)


                # Timeout: retry
                except socket.timeout:
                    # print('-', end ="")
                    if self.status('isPlaying'):
                        self.log('PLAYBACK LOCKED OUT', self._mpv_lockedout)
                        self._mpv_send('{ "command": ["set_property", "pause", false] }')
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
        self._mpv_subproc = subprocess.Popen(
                            ['mpv', '--input-ipc-server=' + self._mpv_socketpath + '',
                                '--idle=yes', '-v', '--no-osc', '--msg-level=ipc=v', '--quiet', '--fs','--keep-open'
                                ,'--window-scale=' + str(self._mpv_scale)
                                ,'--image-display-duration=' + str(self._mpv_imagetime)
                                #,'--force-window=yes'
                                ],
                            stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr = subprocess.STDOUT,
                            bufsize = 1, universal_newlines = True)

        # Watch subprocess
        self._mpv_procThread = threading.Thread(target=self._mpv_watchprocess)
        self._mpv_procThread.start()

        # Socket IPC connect
        self._mpv_recvThread = threading.Thread(target=self._mpv_communicate)
        self._mpv_recvThread.start()


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


    def _play(self, path):
        # self.log("play", path)
        self.update('isPaused', False)
        # self._mpv_send('{ "command": ["stop"] }')
        self._mpv_send('{ "command": ["loadfile", "'+path+'"] }')
        self._mpv_send('{ "command": ["set_property", "pause", false] }')

    def _stop(self):
        self.update('isPaused', False)
        self._mpv_send('{ "command": ["stop"] }')
        if not self.status('isPlaying'):
            self.emit('stopped')    # already stopped, so manually trigger event

    def _pause(self):
        self.update('isPaused', True)
        self._mpv_send('{ "command": ["set_property", "pause", true] }')

    def _resume(self):
        self.update('isPaused', False)
        self._mpv_send('{ "command": ["set_property", "pause", false] }')

    def _seekTo(self, milli):
        self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "absolute"] }')
        # self.log("seek to", milli/1000)

    def _skip(self, milli):
        if self._status['time'] + milli/1000 < self._status['duration']:
            self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "relative"] }')
        # self.log("seek to", milli/1000)

    def _applyVolume(self, volume):
        self._mpv_send('{ "command": ["set_property", "volume", '+str(volume)+'] }')
        self.log("VOLUME to", volume)

    def _applyPan(self, pan):
        if pan == 'mono':
            self._mpv_send('{"command": ["set_property", "af", "lavfi=[pan=stereo|c0=.5*c0+.5*c1|c1=.5*c0+.5*c1]"]}')            
        else:
            left = pan[0]/100.0
            right = pan[1]/100.0
            self._mpv_send('{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')
            self.log("PAN to", left, right, '{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')
    
    def _applyFlip(self, flip):
        if flip:
            # self._mpv_send('{ "command": ["vf", "add", "mirror"] }')
            pass
        else:
            # self._mpv_send('{ "command": ["vf", "del", "mirror"] }')
            pass
