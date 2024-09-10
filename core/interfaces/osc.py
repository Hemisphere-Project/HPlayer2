from .base import BaseInterface
from core.engine import network
import pyliblo3
import random, time
from sys import getsizeof
import socket

from ..engine.network import get_allip, get_hostname
from zeroconf import ServiceInfo, Zeroconf

current_milli_time = lambda: int(round(time.time() * 1000))

def oscdump(path, args, types):
    print("OSC Received:", path, args)

class OscInterface (BaseInterface):

    def  __init__(self, hplayer, in_port, out_port=0):
        super(OscInterface, self).__init__(hplayer, "OSC")

        self._portIn = in_port
        self._portOut = out_port if out_port > 0 else in_port
        self.hostOut = network.get_broadcast()

        self.burstCounter = random.randint(1,10000)
        self.ethMac = network.get_ethmac()
        self.burstMem = {}


    # OSC sender
    def send(self, path, *args):
        target = pyliblo3.Address("osc.udp://"+self.hostOut+":"+str(self._portOut))
        pyliblo3.send(target, path, *args)
        # self.log("sent OSC", path, args ," to ","osc.udp://"+self.hostOut+":"+str(self._portOut))

    # OSC send BURST using stamp
    def sendBurst(self, path, *args):
        self.burstCounter += 1
        target = pyliblo3.Address("osc.udp://"+self.hostOut+":"+str(self._portOut))
        for i in range(5):
            pyliblo3.send(target, '/burst', self.ethMac, self.burstCounter, path, *args)

    # OSC receiver THREAD
    def listen(self):

        # OSC: Bind server
        try:
            oscServer = pyliblo3.Server(self._portIn)
            self.log("input  = udp://*:"+str(self._portIn))
            self.log("output = udp://"+str(self.hostOut)+":"+str(self._portOut))

        except pyliblo3.ServerError as e:
            self.log( "OSC Error:", e)
            self.stopped.set()


        # OSC trigger decorator
        def osc(path, argsTypes=None):
            def handler(func):
                if self.isRunning():
                    # oscServer.add_method(path, argsTypes, oscdump)
                    oscServer.add_method(path, argsTypes, func)
                return func
            return handler

        @osc("/burst")
        def burst(path, args, types):
            if len(args) < 2: return
            mac = args.pop(0)
            stamp = args.pop(0)
            if not mac in self.burstMem or self.burstMem[mac] != stamp:
                self.burstMem[mac] = stamp
                path = args.pop(0)
                types = types[2:]
                # print("relaying bursted frame", path, args, types)
                target = pyliblo3.Address("osc.udp://127.0.0.1:"+str(self._portIn))
                pyliblo3.send(target, path, *args)

        @osc(None, None)
        def fallback(path, args, types, src):
            self.emit(path[1:], *args)

        # Advertize on ZeroConf
        zeroconf = Zeroconf()
        info = ServiceInfo(
            "_osc._udp.local.",
            "OSC input._"+get_hostname()+"._osc._udp.local.",
            addresses=[socket.inet_aton(ip) for ip in get_allip()],
            port=self._portIn,
            properties={},
            server=get_hostname()+".local.",
        )
        zeroconf.register_service(info)
        if self._portOut != self._portIn:
            info2 = ServiceInfo(
                "_osc._udp.local.",
                "OSC output._"+get_hostname()+"._osc._udp.local.",
                addresses=[socket.inet_aton(ip) for ip in get_allip()],
                port=self._portOut,
                properties={},
                server=get_hostname()+".local.",
            )
            zeroconf.register_service(info2)

        # loop and dispatch messages every 100ms
        while self.isRunning():
            oscServer.recv(100)

        # Unregister ZeroConf
        zeroconf.unregister_service(info)
        if self._portOut != self._portIn:
            zeroconf.unregister_service(info2)
        zeroconf.close()

        return
