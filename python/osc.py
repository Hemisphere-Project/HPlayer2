from __future__ import print_function
from termcolor import colored
import liblo
import threading

class OscInterface:

    def  __init__(self, portIn, portOut, player):

        self.name = "OSC"
        self.nameP = colored(self.name,'blue')
        self.stopEvent = threading.Event()

        self.portIn = portIn
        self.portOut = portOut

        # OSC Server thread
        self.recvThread = threading.Thread(target=self.receive, args=(player,))
        self.recvThread.start()


    # OSC receiver THREAD
    def receive(self, player):

        # OSC: Bind server
        try:
            oscServer = liblo.Server(self.portIn)
            print(self.nameP, "binded to OSC port", self.portIn)

        except liblo.ServerError, e:
            print(self.nameP,  "OSC Error:", e)
            self.stop()

        # OSC trigger decorator
        def osc(path, argsTypes=None):
            def handler(func):
                oscServer.add_method(path, argsTypes, func)
                return func
            return handler


        @osc("/play")
        def play(path, args, types):
            player.send('{ "command": ["loadfile", "'+args[0]+'"] }\n')

        @osc("/playloop")
        def playloop(path, args, types):
            # TODO
            pass

        @osc("/load")
        def load(path, args, types):
            # TODO
            pass

        @osc("/add")
        def add(path, args, types):
            # TODO
            pass

        @osc("/stop")
        def stop(path, args, types):
            player.send('{ "command": ["stop"] }')

        @osc("/pause")
        def pause():
            player.send('{ "command": ["set_property", "pause", true] }')

        @osc("/resume")
        def resume():
            player.send('{ "command": ["set_property", "pause", false] }')

        @osc("/next")
        def next(path, args, types):
            # TODO
            pass

        @osc("/prev")
        def prev(path, args, types):
            # TODO
            pass

        @osc("/loop")
        def loop(path, args, types):
            # TODO
            pass

        @osc("/unloop")
        def unloop(path, args, types):
            # TODO
            pass

        @osc("/volume")
        def volume(path, args, types):
            # TODO
            pass

        @osc("/mute")
        def mute(path, args, types):
            # TODO
            pass

        @osc("/unmute")
        def unmute(path, args, types):
            # TODO
            pass

        @osc("/zoom")
        def zoom(path, args, types):
            # TODO
            pass

        @osc("/info")
        def info(path, args, types):
            # TODO
            pass

        @osc("/host")
        def host(path, args, types):
            # TODO
            pass

        @osc("/getStatus")
        def getStatus(path, args, types):
            # TODO
            pass

        @osc("/quit")
        def quit(path, args, types):
            self.stop()

        @osc(None, None)
        def fallback(path, args, types, src):
            print (nameP, "unknown message", path, "from", src.url)
            for a, t in zip(args, types):
                print (nameP, "argument of type", t, ":", a)

        # loop and dispatch messages every 100ms
        while not self.stopEvent.is_set():
            oscServer.recv(100)

        return

    # Stop
    def stop(self):
        self.stopEvent.set()
        if self.recvThread.isAlive():
            self.recvThread.join()
        print(self.nameP, "stopped")

    def isRunning(self):
        return not self.stopEvent.is_set()
