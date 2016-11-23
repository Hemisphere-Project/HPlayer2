from __future__ import print_function
from termcolor import colored
from time import sleep
from interfaces.base import BaseInterface
import cherrypy

class HttpInterface (BaseInterface):

    def  __init__(self, player, params):

        super(HttpInterface, self).__init__(player)

        self.name = "HTTP "+player.name
        self.nameP = colored(self.name,'blue')

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
            def event(self, *args, **kwargs):
                self.player.trigger(args[0])
                return u'Event {0} triggered with {1}'.format(args[0], kwargs)

        cherrypy.server.socket_port = params[0]
        cherrypy.server.socket_host = '0.0.0.0'
        cherrypy.log.screen = False
        cherrypy.tree.mount(HelloWorld(player), "/", {'/':{}})

        self.start()


    # HTTP receiver THREAD
    def receive(self):

        print(self.nameP, "starting HTTP server")
        cherrypy.engine.start()

        while self.isRunning() and cherrypy.engine.state == cherrypy.engine.states.STARTED:
            sleep(0.1)

        cherrypy.engine.exit()
        cherrypy.server.stop()
        self.isRunning(False)
        return
