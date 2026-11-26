from .base import BaseInterface
from core.engine import network
import random, time
from sys import getsizeof
from threading import Thread

try:
    from pythonosc import udp_client, dispatcher, osc_server
    OSC_DEPENDENCIES_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    OSC_DEPENDENCIES_AVAILABLE = False
    udp_client = dispatcher = osc_server = None

from core.engine import mdns
from core.engine.network import get_hostname

current_milli_time = lambda: int(round(time.time() * 1000))

def oscdump(address, *args):
    print("OSC Received:", address, args)

class OscInterface(BaseInterface):

    def __init__(self, hplayer, in_port, out_port=0, hostOut=None):
        super(OscInterface, self).__init__(hplayer, "OSC")
        if not OSC_DEPENDENCIES_AVAILABLE:
            raise RuntimeError("python-osc module not available; OSC interface disabled")

        self._portIn = in_port
        self._portOut = out_port if out_port > 0 else in_port
        
        if not hostOut:
            self.hostOut = network.get_broadcast()
        else:
            self.hostOut = hostOut

        self.burstCounter = random.randint(1, 10000)
        self.ethMac = network.get_ethmac()
        self.burstMem = {}

        self.client = udp_client.SimpleUDPClient(self.hostOut, self._portOut)

    def send(self, path, *args):
        self.client.send_message(path, args)

    def sendBurst(self, path, *args):
        self.burstCounter += 1
        for i in range(5):
            self.client.send_message('/burst', [self.ethMac, self.burstCounter, path] + list(args))

    def listen(self):
        disp = dispatcher.Dispatcher()
        disp.set_default_handler(self.fallback)
        disp.map("/burst", self.burst)

        server = osc_server.ThreadingOSCUDPServer(("0.0.0.0", self._portIn), disp)
        self.log("input  = udp://*:" + str(self._portIn))
        self.log("output = udp://" + str(self.hostOut) + ":" + str(self._portOut))

        # Advertise on ZeroConf — never fatal (a name taken on the LAN is renamed, see mdns)
        services = [("_osc._udp.local.", "OSC input._" + get_hostname(), self._portIn)]
        if self._portOut != self._portIn:
            services.append(("_osc._udp.local.", "OSC output._" + get_hostname(), self._portOut))
        advert = mdns.advertise(services, self.log)

        server_thread = Thread(target=server.serve_forever)
        server_thread.start()

        while self.isRunning():
            time.sleep(0.1)

        server.shutdown()
        server_thread.join()

        mdns.withdraw(advert)

    def burst(self, address, *args):
        if len(args) < 2:
            return
        mac = args[0]
        stamp = args[1]
        if mac not in self.burstMem or self.burstMem[mac] != stamp:
            self.burstMem[mac] = stamp
            path = args[2]
            payload = args[3:]
            self.fallback(path, *payload)

    def fallback(self, address, *args):
        self.emit(address[1:], *args)



