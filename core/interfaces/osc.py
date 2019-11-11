from .base import BaseInterface
from core.engine import network
import liblo
import random
from sys import getsizeof

from ..engine.network import get_allip
from zeroconf import IPVersion, ServiceInfo, Zeroconf       # https://github.com/jstasiak/python-zeroconf/
import socket

current_milli_time = lambda: int(round(time.time() * 1000))

def oscdump(path, args, types):
    print("OSC Received:", path, args)

class OscInterface (BaseInterface):

    def  __init__(self, player, in_port, out_port=0):
        super(OscInterface, self).__init__(player, "OSC")

        self._portIn = in_port
        self._portOut = out_port if out_port > 0 else in_port
        self.hostOut = network.get_broadcast()

        self.burstCounter = random.randint(1,10000)
        self.ethMac = network.get_ethmac()
        self.burstMem = {}


    # OSC sender
    def send(self, path, *args):
        target = liblo.Address("osc.udp://"+self.hostOut+":"+str(self._portOut))
        liblo.send(target, path, *args)
        # self.log("sent OSC", path, args ," to ","osc.udp://"+self.hostOut+":"+str(self._portOut))

    # OSC send BURST using stamp
    def sendBurst(self, path, *args):
        self.burstCounter += 1
        target = liblo.Address("osc.udp://"+self.hostOut+":"+str(self._portOut))
        for i in range(5):
            liblo.send(target, '/burst', self.ethMac, self.burstCounter, path, *args)

    # OSC receiver THREAD
    def listen(self):

        # OSC: Bind server
        try:
            oscServer = liblo.Server(self._portIn)
            self.log("input  = udp://*:"+str(self._portIn))
            self.log("output = udp://"+str(self.hostOut)+":"+str(self._portOut))

        except liblo.ServerError as e:
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
                target = liblo.Address("osc.udp://127.0.0.1:"+str(self._portIn))
                liblo.send(target, path, *args)

        @osc("/play")
        def play(path, args, types):
            self.player.loop(0)
            if args[0]: self.player.play(args[0])
            else: self.player.play()

        @osc("/playindex")
        def play(path, args, types):
            if args and len(args) >= 1: self.player.play(args[0])

        @osc("/playlist")
        def play(path, args, types):
            if args:
                if len(args) >= 1:
                    self.player.load(args[0])
                    if len(args) >= 2: self.player.play(args[1])
                    else: self.player.play()

        @osc("/playloop")
        def playloop(path, args, types):
            self.player.loop(1)
            if args[0]: self.player.play(args[0])
            else: self.player.play()

        @osc("/load")
        def load(path, args, types):
            if args and len(args) >= 1:
                self.player.load(args[0])

        @osc("/stop")
        def stop(path, args, types):
            self.player.stop()

        @osc("/pause")
        def pause():
            self.player.pause()

        @osc("/resume")
        def resume():
            self.player.resume()

        @osc("/next")
        def next(path, args, types):
            self.player.next()

        @osc("/prev")
        def prev(path, args, types):
            self.player.prev()

        @osc("/loop")
        def loop(path, args, types):
            self.player.loop(1)

        @osc("/unloop")
        def unloop(path, args, types):
            self.player.loop(0)

        @osc("/volume")
        def volume(path, args, types):
            if args and len(args) >= 1:
                self.player.volume(args[0])

        @osc("/mute")
        def mute(path, args, types):
            self.player.mute(True)

        @osc("/unmute")
        def unmute(path, args, types):
            self.player.mute(False)

        @osc("/pan")
        def pan(path, args, types):
            self.player.pab(args[0], args[1])

        @osc("/flip")
        def flip(path, args, types):
            self.player.flip(True)

        @osc("/unflip")
        def unflip(path, args, types):
            self.player.flip(False)

        #@osc("/status")
        #def getStatus(path, args, types):
        #    print('STATUS')
        #    pass

        @osc("/quit")
        def quit(path, args, types):
            self.stopped.set()

        @osc(None, None)
        def fallback(path, args, types, src):
            self.player.trigger(path, args)
            # self.log(path, args, "from", src.url)

        # Advertize on ZeroConf
        zeroconf = Zeroconf()
        info = ServiceInfo(
            "_osc._udp.local.",
            "HPlayer2 OSC input._osc._udp.local.",
            addresses=[socket.inet_aton(ip) for ip in get_allip()],
            port=self._portIn,
            properties={},
            server=socket.gethostname()+".local.",
        )
        zeroconf.register_service(info)
        if self._portOut != self._portIn:
            info2 = ServiceInfo(
                "_osc._udp.local.",
                "HPlayer2 OSC output._osc._udp.local.",
                addresses=[socket.inet_aton(ip) for ip in get_allip()],
                port=self._portOut,
                properties={},
                server=socket.gethostname()+".local.",
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
