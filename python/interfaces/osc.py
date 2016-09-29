from __future__ import print_function
from termcolor import colored
import liblo
import threading

class OscInterface:

    running = threading.Event()
    running.set()

    def  __init__(self, portIn, portOut, player):

        self.name = "OSC "+player.name
        self.nameP = colored(self.name,'blue')

        self.portIn = portIn
        self.portOut = portOut
        self.player = player

        # OSC Server thread
        self.recvThread = threading.Thread(target=self.receive)
        self.recvThread.start()


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
            self.player.play(args[0])

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
            self.player.stop()

        @osc("/pause")
        def pause():
            self.player.pause()

        @osc("/resume")
        def resume():
            self.player.resume()

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
            self.isRunning(False)

        @osc(None, None)
        def fallback(path, args, types, src):
            print (nameP, "unknown message", path, "from", src.url)
            for a, t in zip(args, types):
                print (nameP, "argument of type", t, ":", a)

        # loop and dispatch messages every 100ms
        while self.isRunning():
            oscServer.recv(100)

        return

    # Stop
    def quit(self):
        self.isRunning(False)
        self.recvThread.join()
        print(self.nameP, "stopped")

    def isRunning(self, state=None):
        if state is not None:
            self.running.set() if state else self.running.clear()
        return self.running.is_set()
