from .base import BaseInterface

import time
import serial
from serial.tools import list_ports
from queue import Queue, Empty, Full


class SerialBase(BaseInterface):
    """
    Generic hotplug serial transport.
    - port discovery: list_ports.grep(filter) regex, or literal device path if filter starts with '/'
    - connect with optional arduino DTR reset dance
    - RX: newline-framed lines -> self.onLine(line)
    - TX: thread-safe self.send(line) queue, drained by the listen thread
    - auto reconnect on broken link / unplug
    Subclasses implement onLine() and may override onConnect / onDisconnect / tick()
    """

    def  __init__(self, hplayer, name, filter="", baud=115200, dtrReset=False, maxRetry=0, scanInterval=3.0):
        super().__init__(hplayer, name)
        self.filter = filter
        self.baud = baud
        self.dtrReset = dtrReset
        self.maxRetry = maxRetry
        self.scanInterval = scanInterval

        self.port = None
        self.serial = None
        self._txQueue = Queue(100)

    #
    # overridables
    #

    def onLine(self, line):
        pass

    def onConnect(self):
        pass

    def onDisconnect(self):
        pass

    def tick(self):     # called every pump iteration while connected (~10Hz on idle link)
        pass

    #
    # public
    #

    def connected(self):
        return self.serial is not None

    def send(self, line):   # thread-safe, drop-oldest on overflow
        try:
            self._txQueue.put_nowait(line)
        except Full:
            try:
                self._txQueue.get_nowait()
                self._txQueue.put_nowait(line)
            except (Empty, Full):
                pass
            self.log("TX queue overflow, dropping oldest")

    #
    # internals
    #

    def _sleep(self, duration):     # interruptible by quit()
        end = time.time() + duration
        while time.time() < end and self.isRunning():
            time.sleep(0.1)

    def _clearTx(self):
        while True:
            try:
                self._txQueue.get_nowait()
            except Empty:
                break

    def _drainTx(self):
        while True:
            try:
                msg = self._txQueue.get_nowait()
            except Empty:
                break
            self.serial.write((msg + '\n').encode('utf-8'))
            time.sleep(0.002)   # pace bursts: small MCUs drop RX on buffer overflow

    def _dropLink(self):
        try:
            if self.serial:
                self.serial.close()
        except Exception:
            pass
        self.serial = None
        self.port = None
        self.emit('disconnected')
        try:
            self.onDisconnect()
        except Exception as e:
            self.log("onDisconnect error:", e)

    # SERIAL pump THREAD
    def listen(self):

        retryCount = 0
        noDeviceLogged = False
        connectFailLogged = False

        while self.isRunning():

            # find port
            if not self.port:
                if self.filter.startswith('/'):
                    self.port = self.filter
                else:
                    retryCount += 1
                    if self.maxRetry == 0 or retryCount <= self.maxRetry:
                        for dev in list_ports.grep(self.filter):
                            self.port = dev.device
                            break
                        if self.port:
                            continue
                        if not noDeviceLogged:
                            self.log("no device found.. waiting for hotplug")
                            noDeviceLogged = True
                    elif not noDeviceLogged:
                        self.log("no device found after", self.maxRetry, "retries.. giving up")
                        noDeviceLogged = True
                    self._sleep(self.scanInterval)

            # connect to serial
            elif not self.serial:
                try:
                    if self.dtrReset:
                        # dummy connection to receive all the watchdog gibberish (unplug + replug) and properly reset the arduino
                        try:
                            with serial.Serial(self.port) as s:
                                s.setDTR(False)
                                time.sleep(1)
                                s.flushInput()
                                s.setDTR(True)
                                time.sleep(0.5)
                        except (OSError, serial.SerialException) as e:
                            self.log("DTR reset skipped:", e)   # ptys / bridges without modem lines
                    self.serial = serial.Serial(self.port, self.baud, timeout=.1)
                except Exception as e:
                    if not connectFailLogged:
                        self.log("connection failed on", self.port, ":", e)
                        connectFailLogged = True
                    self.port = None
                    self.serial = None
                    self._sleep(self.scanInterval)
                    continue

                self.log("connected to", self.port, "!")
                noDeviceLogged = False
                connectFailLogged = False
                self._clearTx()
                self.emit('connected')
                try:
                    self.onConnect()
                except Exception as e:
                    self.log("onConnect error:", e)

            # pump: read lines / periodic tick / write queue
            else:
                try:
                    data = self.serial.readline()
                    if data:
                        line = data.decode('utf-8', errors='replace').strip('\r\n')
                        if line:
                            try:
                                self.onLine(line)
                            except Exception as e:
                                self.log("onLine error:", e, "|", line)
                    try:
                        self.tick()
                    except Exception as e:
                        self.log("tick error:", e)
                    self._drainTx()
                except (serial.SerialException, OSError):
                    self.log("broken link..")
                    self._dropLink()
                    self._sleep(0.5)

        # closing: best effort flush then close
        if self.serial:
            try:
                self._drainTx()
                self.serial.close()
            except Exception:
                pass
