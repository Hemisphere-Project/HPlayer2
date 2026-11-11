from .base import BaseInterface

import os
import time
import threading
from queue import Queue, Empty, Full

# pyserial is optional at import time so the module tree stays importable
# on partial installs; instantiating any SerialBase interface requires it
try:
    import serial
    from serial.tools import list_ports
    _SERIAL_IMPORT_ERROR = None
except ImportError as err:
    serial = None
    list_ports = None
    _SERIAL_IMPORT_ERROR = err


class SerialBase(BaseInterface):
    """
    Generic hotplug serial transport.
    - port discovery: list_ports.grep(filter) regex, or literal device path if filter starts with '/'
    - connect with optional arduino DTR reset dance
    - RX: newline-framed lines -> self.onLine(line)
    - TX: thread-safe self.send(line) queue, drained by the listen thread
    - auto reconnect on broken link / unplug
    - one reader per tty: a scan skips a port another interface of this process holds
    - rejectPort(): a subclass that recognises a foreign device (several modules share
      a VID:PID, e.g. 303a:1001) drops it and re-scans excluding it until it is unplugged
    Subclasses implement onLine() and may override onConnect / onDisconnect / tick()
    """

    # realpath(port) -> interface holding it, across every SerialBase of the process:
    # two readers on one tty split its lines between them and both starve
    _claims = {}
    _claimsLock = threading.Lock()

    def  __init__(self, hplayer, name, filter="", baud=115200, dtrReset=False, maxRetry=0, scanInterval=3.0):
        if _SERIAL_IMPORT_ERROR:
            raise RuntimeError("pyserial is required for " + name) from _SERIAL_IMPORT_ERROR
        super().__init__(hplayer, name)
        self.filter = filter
        self.baud = baud
        self.dtrReset = dtrReset
        self.maxRetry = maxRetry
        self.scanInterval = scanInterval

        self.port = None
        self.serial = None
        self._matchedFilter = None      # filter the current port was matched with
        self._portId = None             # identity of the device the current port was matched on
        self._rejected = {}             # port -> identity of the device rejectPort() refused there
        self._rejectReason = None       # set by rejectPort(), acted on by the pump
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

    def rejectPort(self, reason):
        """the connected device is not ours (a same-id module): the pump drops it and the
        scan skips it until it leaves the bus or comes back as a new plug-in.
        No-op on a literal device path: that filter names the port on purpose."""
        if self.port and not self._rejectReason and not self.filter.startswith('/'):
            self._rejectReason = reason

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

    @staticmethod
    def _identity(dev):
        # hwid alone survives an unplug/replug between two scans; the device node's
        # inode does not (devtmpfs creates a fresh node per plug-in)
        try:
            ino = os.stat(dev.device).st_ino
        except OSError:
            ino = None
        return (dev.hwid, ino)

    def _pick(self):
        """first port matching the filter that we have not rejected and that no
        other interface holds; claims it"""
        found = [(dev.device, self._identity(dev)) for dev in list_ports.grep(self.filter)]
        # a rejected device that left the bus, or came back as a new plug-in, gets a fresh look
        self._rejected = {p: i for p, i in self._rejected.items() if (p, i) in found}
        with SerialBase._claimsLock:
            for port, ident in found:
                if port in self._rejected:
                    continue
                key = os.path.realpath(port)
                if SerialBase._claims.get(key, self) is not self:
                    continue
                SerialBase._claims[key] = self
                self._portId = ident
                return port
        return None

    def _release(self):
        with SerialBase._claimsLock:
            for key in [k for k, owner in SerialBase._claims.items() if owner is self]:
                del SerialBase._claims[key]

    def _forgetPort(self):
        self.port = None
        self._release()

    def _dropLink(self):
        try:
            if self.serial:
                self.serial.close()
        except Exception:
            pass
        self.serial = None
        self._forgetPort()
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

            # the subclass recognised a foreign device on this port (rejectPort)
            # -> drop it and re-scan excluding it
            if self._rejectReason:
                if self.port:
                    self.log(self.port, "is not ours:", self._rejectReason,
                             "-> re-scan excluding it")
                    self._rejected[self.port] = self._portId
                    retryCount = 0
                    noDeviceLogged = False
                    if self.serial:
                        self._dropLink()
                    else:
                        self._forgetPort()
                self._rejectReason = None

            # filter changed (settings.load beaten by the first scan, or live
            # edit) -> forget the port matched under the old filter and re-scan
            if self.port and self.filter != self._matchedFilter:
                self.log("filter changed -> re-scan")
                retryCount = 0
                noDeviceLogged = False
                if self.serial:
                    self._dropLink()
                else:
                    self._forgetPort()

            # find port
            if not self.port:
                self._matchedFilter = self.filter
                if self.filter.startswith('/'):
                    self.port = self.filter
                else:
                    retryCount += 1
                    if self.maxRetry == 0 or retryCount <= self.maxRetry:
                        self.port = self._pick()
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
                    self.serial = None
                    self._forgetPort()
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
        self._release()
