from __future__ import print_function
from termcolor import colored
from time import sleep
from base import BaseInterface
import pprint
import cherrypy

class HttpInterface (BaseInterface):

    def  __init__(self, player, args):

        if len(args) < 1:
            print(self.nameP, 'HTTP interface needs a port')

        super(HttpInterface, self).__init__(player)

        self.name = "HTTP "+player.name
        self.nameP = colored(self.name, 'blue')

        class HelloWorld(object):

            def __init__(self, player):
                self.player = player

            @cherrypy.expose
            def index(self):
                return "Hello World!"

            @cherrypy.expose
            def play(self, media):
                self.player.play(str(media))
                return "play "+media

            @cherrypy.expose
            def stop(self):
                self.player.stop()
                return "stop"

            @cherrypy.expose
            def pause(self):
                self.player.pause()
                return "pause"

            @cherrypy.expose
            def resume(self):
                self.player.resume()
                return "resume"

            @cherrypy.expose
            def next(self):
                self.player.next()
                return "next"

            @cherrypy.expose
            def prev(self):
                self.player.prev()
                return "prev"

            @cherrypy.expose
            def loop(self):
                self.player.loop(True)
                return "loop"

            @cherrypy.expose
            def unloop(self):
                self.player.loop(False)
                return "unloop"

            @cherrypy.expose
            def volume(self, vol):
                self.player.volume(int(vol))
                return "volume "+vol

            @cherrypy.expose
            def mute(self):
                self.player.mute(True)
                return "mute"

            @cherrypy.expose
            def unmute(self):
                self.player.mute(False)
                return "unmute"

            @cherrypy.expose
            def status(self):
                return pprint.pformat(self.player._status, indent=4)

            @cherrypy.expose
            def event(self, *args, **kwargs):
                self.player.trigger(args[0])
                return u'Event {0} triggered with {1}'.format(args[0], kwargs)

        self.port = args[0]
        cherrypy.server.socket_port = self.port
        cherrypy.server.socket_host = '0.0.0.0'
        cherrypy.log.screen = False
        cherrypy.tree.mount(HelloWorld(player), "/", {'/':{}})

        self.start()

    # HTTP receiver THREAD
    def receive(self):

        print(self.nameP, "starting HTTP server on port", self.port)
        cherrypy.engine.start()

        while self.isRunning() and cherrypy.engine.state == cherrypy.engine.states.STARTED:
            sleep(0.1)

        cherrypy.engine.exit()
        cherrypy.server.stop()
        self.isRunning(False)
        return
