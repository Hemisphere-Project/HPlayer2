from __future__ import print_function
from termcolor import colored
import socket
import threading
from base import BasePlayer

class MpvPlayer(BasePlayer):

    def __init__(self, socketPath):

        self.name = "MPV"
        self.nameP = colored(self.name,'magenta')

        # Connect to Socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(socketPath)
            self.sock.settimeout(0.1)
            print(self.nameP, "connected to MPV at", socketPath)

        except socket.error, msg:
            print (self.nameP, msg)
            self.quit()

        # MPV Receive thread
        self.recvThread = threading.Thread(target=self._receive)
        self.recvThread.start()

    # MPV Receive ipc THREAD
    def _receive(self):

        # Receive
        while not self.stopEvent.is_set():

            # Listen socket
            try:
                msg = self.sock.recv(4096)
                assert len(msg) != 0, "Connection closed"

                # Message received
                print(self.nameP, "says:", msg.rstrip())

            # Timeout: retry
            except socket.timeout:
                pass

            # Socket error: exit
            except (socket.error, AssertionError) as e:
                print(self.nameP, "Socket Error:",e)
                self._quit()

        return


    # MPV Send ipc
    def _send(self, msg):
        self.sock.send(msg+'\n')

    # Quit
    def quit(self):
        super(MpvPlayer, self).quit()
        if hasattr(self, 'recvThread'):
            if self.recvThread.isAlive():
                self.recvThread.join()
        self.sock.close()
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
