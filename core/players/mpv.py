from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, os, json, select
from time import sleep
from .base import BasePlayer

class MpvPlayer(BasePlayer):

    def __init__(self, name=None):
        super(MpvPlayer, self).__init__()

        name = name.replace(" ", "_")
        if not name:
            import time
            name = time.time()

        self.name = name
        self.nameP = colored("MPV -" + name + "-",'magenta')
        self.nameP = colored("MPV" ,'magenta')

        self._mpv_procThread = None

        self._mpv_sock = None
        self._mpv_sock_connected = False
        self._mpv_recvThread = None

        self._mpv_socketpath = '/tmp/hplayer-' + name
        self._mpv_scale = 1


    ############
    ## public METHODS
    ############

    # Window scale (must be called before starting process)
    def scale(self, sc):
        self._mpv_scale = sc

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
            poll_result = poll_obj.poll(0)
            if poll_result:
                out = self._mpv_subproc.stdout.readline()
                if out.strip():
                    # print(self.nameP, "subproc says", out.strip())
                    pass
            else:
                sleep(0.1)          ## TODO turn into ASYNC !!


        if self._mpv_subproc.poll():
            self._mpv_subproc.terminate()
            if not self._mpv_subproc.poll():
                print(self.nameP, "process terminated")
            else:
                self._mpv_subproc.kill()
                print(self.nameP, "process killed")
        else:
            print(self.nameP, "process closed")

        self.isRunning(False)
        return


    # MPV ipc receive THREAD
    def _mpv_communicate(self):

        # Socket IPC to process
        self._mpv_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for retry in range(10, 0, -1):
            try:
                self._mpv_sock.connect(self._mpv_socketpath)
                self._mpv_sock.settimeout(0.1)
                print(self.nameP, "connected to player backend")
                self._mpv_sock_connected = True
                self.trigger('player-ready')
                break
            except socket.error as e:
                if retry == 1:
                    print (self.nameP, "socket error:", e)
                    self.isRunning(False)
                else:
                    # print (self.nameP, "retrying socket connection..")
                    sleep(0.2)

        if self._mpv_sock_connected:

            # Listener
            self._mpv_send('{ "command": ["observe_property", 1, "eof-reached"] }')
            self._mpv_send('{ "command": ["observe_property", 2, "core-idle"] }')
            self._mpv_send('{ "command": ["observe_property", 3, "time-pos"] }')

            # Receive
            while self.isRunning():

                # Listen socket
                try:
                    msg = self._mpv_sock.recv(4096)
                    assert len(msg) != 0, "socket disconnected"

                    # Message received
                    for event in msg.rstrip().split( b"\n" ):
                        try:
                            mpvsays = json.loads(event)
                        except:
                            #print(self.nameP, "IPC invalid json:", event)
                            pass

                        if 'name' in mpvsays:
                            if mpvsays['name'] == 'eof-reached' and mpvsays['data'] == True:
                                self._status['isPaused'] = False
                                self.trigger('end')
                                pass
                            elif mpvsays['name'] == 'core-idle':
                                self._status['isPlaying'] = not mpvsays['data']
                            elif mpvsays['name'] == 'time-pos':
                                if mpvsays['data']:
                                    self._status['time'] = round(float(mpvsays['data']),2)
                            else:
                                pass
                            #    print(self.nameP, "IPC event:", mpvsays)

                    # print(self.nameP, "IPC says:", msg.rstrip())

                # Timeout: retry
                except socket.timeout:
                    pass

                # Socket error: exit
                except (socket.error, AssertionError) as e:
                    if self.isRunning():
                        print(self.nameP, e)
                        self.isRunning(False)

        self._mpv_sock.close()
        self._mpv_sock_connected = False
        print(self.nameP, "socket closed")
        self.isRunning(False)
        return


    # MPV ipc send
    def _mpv_send(self, msg):
        if self._mpv_sock_connected:
            try:
                self._mpv_sock.send( (msg+'\n').encode() )
            except socket.error:
                print (self.nameP, "socket send error:", msg)
                self.isRunning(False)
        else:
            print(self.nameP, "socket not connected, can't send \""+msg+"\"")


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
                            [script_path+'/../../bin/mpv', '--input-ipc-server=' + self._mpv_socketpath + '',
                                '--idle=yes', '--no-osc', '--msg-level=ipc=v', '--quiet', '--fs','--keep-open'
                                ,'--window-scale=' + str(self._mpv_scale)
                                ,'--image-display-duration=3'
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
            # print(self.nameP, "stopping process thread")
            self._mpv_procThread.join()

        if self._mpv_recvThread:
            # print(self.nameP, "stopping socket thread")
            self._mpv_recvThread.join()

        print(self.nameP, "stopped")


    def _play(self, path):
        print(self.nameP, "play", path)
        # self._mpv_send('{ "command": ["stop"] }')
        self._mpv_send('{ "command": ["loadfile", "'+path+'"] }')
        self._mpv_send('{ "command": ["set_property", "pause", false] }')
        self._status['isPaused'] = False

    def _stop(self):
        self._mpv_send('{ "command": ["stop"] }')
        self._status['isPaused'] = False

    def _pause(self):
        self._mpv_send('{ "command": ["set_property", "pause", true] }')
        self._status['isPaused'] = True

    def _resume(self):
        self._mpv_send('{ "command": ["set_property", "pause", false] }')
        self._status['isPaused'] = False

    def _seekTo(self, milli):
        self._mpv_send('{ "command": ["seek", "'+str(milli/1000)+'", "absolute"] }')
        # print(self.nameP, "seek to", milli/1000)

    def _applyVolume(self):
        vol = self._settings['volume']
        if self._settings['mute']:
            vol = 0
        self._mpv_send('{ "command": ["set_property", "volume", '+str(vol)+'] }')
        print(self.nameP, "VOLUME to", vol)

    def _applyPan(self):
        left = self._settings['pan'][0]/100.0
        right = self._settings['pan'][1]/100.0
        self._mpv_send('{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')
        print(self.nameP, "PAN to", left, right, '{"command": ["set_property", "af", "lavfi=[pan=stereo|c0='+str(left)+'*c0|c1='+str(right)+'*c1]"]}')

    def _applyFlip(self):
        if not self._settings['flip']:
            # self._mpv_send('{ "command": ["vf", "add", "mirror"] }')
            pass
        else:
            # self._mpv_send('{ "command": ["vf", "del", "mirror"] }')
            pass
