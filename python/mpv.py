from __future__ import print_function
from termcolor import colored
import socket
import threading

class MpvInterface:

    def __init__(self, socketPath):

        self.name = "MPV"
        self.nameP = colored(self.name,'magenta')
        self.stopEvent = threading.Event()

        # Connect to Socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(socketPath)
            self.sock.settimeout(0.1)
            print(self.nameP, "connected to MPV at", socketPath)

        except socket.error, msg:
            print (self.nameP, msg)
            self.stopEvent.set()

        # MPV Receive thread
        self.recvThread = threading.Thread(target=self.receive)
        self.recvThread.start()

    # MPV Receive ipc THREAD
    def receive(self):

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
                self.stop()

        return


    # MPV Send ipc
    def send(self, msg):
        self.sock.send(msg+'\n')

    # Stop
    def stop(self):
        self.stopEvent.set()
        if self.recvThread.isAlive():
            self.recvThread.join()
        self.sock.close()
        print(self.nameP, "stopped")

    def isRunning(self):
        return not self.stopEvent.is_set()
