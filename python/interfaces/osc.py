from __future__ import print_function
from termcolor import colored
from base import BaseInterface
import liblo


class OscInterface (BaseInterface):

    def  __init__(self, player, args):

        if len(args) < 2:
            print(self.nameP, 'OSC interface needs in and out port arguments')
            return

        super(OscInterface, self).__init__(player)

        self.name = "OSC "+player.name
        self.nameP = colored(self.name,'blue')

        self.portIn = args[0]
        self.portOut = args[1]
        self.hostOut = "127.0.0.1"

        self.start()

    # OSC sender
    def send(self, path, *args):
        target = liblo.Address("osc.udp://"+self.hostOut+":"+str(self.portOut))
        liblo.send(target, path, *args)

    # OSC receiver THREAD
    def receive(self):

        # OSC: Bind server
        try:
            oscServer = liblo.Server(self.portIn)
            print(self.nameP, "binded to OSC port", self.portIn)

        except liblo.ServerError, e:
            print(self.nameP,  "OSC Error:", e)
            self.isRunning(False)

        # OSC trigger decorator
        def osc(path, argsTypes=None):
            def handler(func):
                if self.isRunning():
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

        @osc("/status")
        def getStatus(path, args, types):
            print('STATUS')
            pass

        @osc("/quit")
        def quit(path, args, types):
            self.isRunning(False)

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
