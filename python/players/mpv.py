from __future__ import print_function
from termcolor import colored
import socket, threading, subprocess, time
from base import BasePlayer

class MpvPlayer(BasePlayer):

    def __init__(self, name, socketPath):

        self.name = "MPV "+name
        self.nameP = colored(self.name,'magenta')

        # Subprocess
        self.process = subprocess.Popen(
                            ['mpv', '--input-ipc-server='+socketPath+'', '--idle=yes', '--no-osc', '--script=lua/welcome.lua', '--msg-level=ipc=v'],
                            stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                            bufsize = 1, universal_newlines = True)

        # Subprocess stdout Thread
        self.procThread = threading.Thread(target=self._read)
        self.procThread.start()

        # Socket IPC to process
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for retry in xrange(10, 0, -1):
            try:
                self.sock.connect(socketPath)
                self.sock.settimeout(0.1)
                print(self.nameP, "connected to MPV at", socketPath)
                break
            except socket.error, msg:
                if retry == 1:
                    print (self.nameP, msg)
                    self.isRunning(False)
                else:
                    time.sleep(0.1)

        # Socket Receive thread
        self.recvThread = threading.Thread(target=self._receive)
        self.recvThread.start()


    # MPV Process stdout THREAD
    def _read(self):

        while not self.process.poll():
            out = self.process.stdout.readline()
            if out.strip():
                #print(self.nameP, "subproc says", out.strip())
                pass

        self.isRunning(False)
        return


    # MPV ipc receive THREAD
    def _receive(self):

        # Receive
        while self.isRunning():

            # Listen socket
            try:
                msg = self.sock.recv(4096)
                assert len(msg) != 0, "disconnected from MPV process"

                # Message received
                #print(self.nameP, "IPC says:", msg.rstrip())

            # Timeout: retry
            except socket.timeout:
                pass

            # Socket error: exit
            except (socket.error, AssertionError) as e:
                if self.isRunning():
                    print(self.nameP, e)
                    self.isRunning(False)

        return


    # MPV ipc send
    def _send(self, msg):
        self.sock.send(msg+'\n')

    ########################
    # OVERLOAD Base Player #
    ########################

    # Quit
    def quit(self):
        self.isRunning(False)
        self.sock.close()
        if not self.process.poll():
            self.process.terminate()
        self.procThread.join()
        self.recvThread.join()
        print(self.nameP, "stopped")

    def validExt(self, file):
        return True

    def play(self, path):
        self._send('{ "command": ["loadfile", "'+path+'"] }')

    def stop(self):
        self._send('{ "command": ["stop"] }')

    def pause(self):
        self._send('{ "command": ["set_property", "pause", true] }')

    def resume(self):
        self._send('{ "command": ["set_property", "pause", false] }')

    def seekTo(self, milli):
        print(self.nameP, "seek to", milli)
