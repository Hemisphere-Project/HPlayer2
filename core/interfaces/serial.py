from .base import BaseInterface

import time
import serial
from serial.tools import list_ports



class SerialInterface (BaseInterface):

    def  __init__(self, hplayer, filter=""):
        super(SerialInterface, self).__init__(hplayer, "Serial")
        self.port = None
        self.serial = None
        self.filter = filter
        

    # SERIAL receiver THREAD
    def listen(self):

        while self.isRunning():

            # find port
            if not self.port:
                for dev in list_ports.grep(self.filter):
                    self.port = dev.device
                    break
                if not self.port:
                    self.log("no device found.. retrying")
                    for i in range(10):
                        sleep(0.5)
                        if not self.isRunning(): 
                            return
            
            # connect to serial
            elif not self.serial:
                try:
                    self.serial = serial.Serial(self.port, 115200, timeout=.1)
                    self.log("connected to", self.port, "!")
                except:
                    self.log("connection failed on", self.port)
                    self.port = None
                    

            # read
            else:
                try:
                    data = self.serial.readline()[:-2] #the last bit gets rid of the new-line chars
                    if data: 
                        self.emit(data.decode("utf-8"))
                except:
                    self.log("broken link..")
                    self.serial = None
