from .base import BaseInterface

import time
import serial
from serial.tools import list_ports



class TelecoInterface (BaseInterface):

    def  __init__(self, hplayer):
        super().__init__(hplayer, "Teleco")
        self.port = None
        self.serial = None
        self.filter = "Leonardo"
        

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
                    time.sleep(5)
            
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
                    data = self.serial.readline()[:-2].decode("utf-8") #the last bit gets rid of the new-line chars
                    if data:
                        self.emit(data)
                        self.serial.write( ("2 1  "+data+"\n").encode() )
                except:
                    self.log("broken link..")
                    self.serial = None
