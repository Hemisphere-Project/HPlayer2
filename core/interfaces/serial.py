from .base import BaseInterface

import importlib
import time

serial = None
list_ports = None
_SERIAL_IMPORT_ERROR = None

try:
    serial = importlib.import_module("serial")
    list_ports = importlib.import_module("serial.tools.list_ports")
except ImportError as err:
    _SERIAL_IMPORT_ERROR = err



class SerialInterface (BaseInterface):

    def  __init__(self, hplayer, filter="", maxRetry=0):
        if _SERIAL_IMPORT_ERROR:
            raise RuntimeError("pyserial is required for SerialInterface") from _SERIAL_IMPORT_ERROR
        if serial is None or list_ports is None:
            raise RuntimeError("pyserial is unavailable for SerialInterface")
        super(SerialInterface, self).__init__(hplayer, "Serial")
        self.port = None
        self.serial = None
        self.filter = filter
        self.maxRetry = maxRetry
        
    # SERIAL receiver THREAD
    def listen(self):

        retryCount = 0
        while self.isRunning():

            # find port
            if not self.port:
                retryCount += 1 
                if self.maxRetry == 0 or retryCount <= self.maxRetry:
                    self.log([dev.device+' '+dev.name+' '+dev.description for dev in list_ports.grep('')])
                    for dev in list_ports.grep(self.filter):
                        self.port = dev.device
                        break
                    if self.port: continue
                    self.log("no device found.. retrying")
                for i in range(10):
                    time.sleep(0.5)
                    if not self.isRunning(): 
                        return
            
            # connect to serial
            elif not self.serial:
                try:
                    # Reset 
                    self.serial = serial.Serial(self.port) # dummy connection to receive all the watchdog gibberish (unplug + replug) and properly reset the arduino
                    with self.serial:
                        self.serial.setDTR(False)   # reset flag
                        time.sleep(1)
                        self.serial.flushInput()
                        self.serial.setDTR(True)
                        time.sleep(0.5)
                    
                    # Connect
                    self.serial = serial.Serial(self.port, 115200, timeout=.1)
                    self.log("connected to", self.port, "!")
                    self.emit('connected')

                except:
                    self.log("connection failed on", self.port)
                    self.emit('disconnected')
                    self.port = None
                    self.serial = None
                    time.sleep(0.5)
                    

            # read
            else:
                try:
                    data = self.serial.readline()[:-2] #the last bit gets rid of the new-line chars
                    if data: 
                        data = data.decode("utf-8").split(' ')
                        data[0] = data[0].lower()
                        if data[0][0] == '/':  # Serial message must start with a slash 
                            data[0] = data[0][1:]
                            data[0].replace('/','.')
                            self.emit(data[0], *data[1:])
                except Exception as e:
                    print(e)
                    self.log("broken link..")
                    self.serial = None
                    time.sleep(0.5)

    # Serial SEND
    def send(self, msg):
        if not self.serial: 
            self.log("no serial connection")
            return
        self.serial.write( (msg+'\n').encode() )
        self.log("send >", msg)