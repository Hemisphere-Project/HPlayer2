from .base import BaseInterface
from time import sleep
import socket, bluetooth, sys

class BtserialInterface (BaseInterface):

    def __init__(self, hplayer, _device):
        super().__init__(hplayer, "BTSERIAL")
        self.device_name = _device
        self.device_addr = None
        self.isConnected = False
        self.sock = None

    def connect(self):
        if self.isConnected:
            return True
        try:
            self.sock = bluetooth.BluetoothSocket( bluetooth.RFCOMM )
            self.sock.connect((self.device_addr, 1))
            self.sock.settimeout(0.5)
            self.isConnected = True
            self.log("connected to ", self.device_name)
            self.send("Yo Rasta?")
            return True
        except:
            e = sys.exc_info()[0]
            self.log('Error while connecting to ', self.device_name, ':', e)
            self.isConnected = False
            return False   
    
    def send(self, topic, data=''):
        if self.isConnected:
            try:
                self.sock.send(topic+" "+data+"\n")
                self.log("send", topic, data)
            except bluetooth.BluetoothError as e:
                self.isConnected = False
                self.log("failed to send ", topic, data, ':', e)
        else:
            self.log("not connected, failed to send ", topic, data)


    # BTSERIAL loop
    def listen(self):

        
        # SCAN devices to find ADDR
        self.log("looking for ", self.device_name)
        while True:
            try:
                nearby_devices = bluetooth.discover_devices()
                for bdaddr in nearby_devices:
                    if bluetooth.lookup_name( bdaddr ) == self.device_name:
                        self.device_addr = bdaddr
                        break
                if self.device_addr: 
                    self.log("found ", self.device_name, "at", self.device_addr)
                    break
                else:
                    self.log("can't find ", self.device_name, ", retrying...")
                    sleep(0.5)
            except:
                self.log("BT error...")
                for i in range(2):
                    sleep(0.5)
                    if not self.isRunning(): 
                        return
                

        # LOOP
        while self.isRunning():

            # # CONNECT device
            while not self.connect():
                self.log("can't connect to ", self.device_name, ", retrying...")
                for i in range(5):
                    sleep(0.5)
                    if not self.isRunning(): 
                        return

            # READ
            try:
                data = self.sock.recv(4096).decode("utf-8").split(' ')
                if len(data) == 1: 
                    self.emit(data[0])
                else:
                    self.emit(data[0], *data[1:])
            except bluetooth.BluetoothError as e:
                if str(e) == 'timed out': pass
                else: 
                    self.log("broken link..:", e)
                    self.isConnected = False
                

