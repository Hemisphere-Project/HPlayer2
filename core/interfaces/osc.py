from .base import BaseInterface
import liblo

def oscdump(path, args, types):
    print("OSC Received:", path, args)

class OscInterface (BaseInterface):

    def  __init__(self, player, in_port, out_port):
        super(OscInterface, self).__init__(player, "OSC")

        self._portIn = in_port
        self._portOut = out_port
        self.hostOut = '127.0.0.1'


    # OSC sender
    def send(self, path, *args):
        target = liblo.Address("osc.udp://"+self.hostOut+":"+str(self._portOut))
        liblo.send(target, path, *args)
        self.log("sent OSC", path, args ," to ","osc.udp://"+self.hostOut+":"+str(self._portOut))

    # OSC receiver THREAD
    def listen(self):

        # OSC: Bind server
        try:
            oscServer = liblo.Server(self._portIn)
            self.log("sending to", self.hostOut, "on port", self._portIn)
            self.log("receiving on port", self._portIn)

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


        @osc("/play")
        def play(path, args, types):
            self.player.loop(False)
            if args[0]: self.player.play(args[0])
            else: self.player.play()

        @osc("/playloop")
        def playloop(path, args, types):
            self.player.loop(True)
            if args[0]: self.player.play(args[0])
            else: self.player.play()

        @osc("/load")
        def load(path, args, types):
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
            self.player.loop(True)

        @osc("/unloop")
        def unloop(path, args, types):
            self.player.loop(False)

        @osc("/volume")
        def volume(path, args, types):
            self.player.volume(args[0])

        @osc("/mute")
        def mute(path, args, types):
            self.player.mute(True)

        @osc("/unmute")
        def unmute(path, args, types):
            self.player.mute(False)

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
            #print (nameP, "unknown message", path, "from", src.url)
            #for a, t in zip(args, types):
                #print (nameP, "argument of type", t, ":", a)

        # loop and dispatch messages every 100ms
        while self.isRunning():
            oscServer.recv(100)

        return
