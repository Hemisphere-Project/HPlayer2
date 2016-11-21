from __future__ import print_function
from termcolor import colored
from time import sleep
from interfaces.base import BaseInterface
import cherrypy

class HttpInterface (BaseInterface):

    def  __init__(self, player):

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
            def event(self, *args, **kwargs):
                self.player.trigger(args[0])
                return u'It is me again at {0} with {1}'.format(args, kwargs)

        cherrypy.server.socket_port = 8080
        cherrypy.server.socket_host = '0.0.0.0'
        #cherrypy.server.socket_host = optional hostname
        cherrypy.tree.mount(HelloWorld(player), "/", None)

        #
        # @app.route("/")
        # def hello():
        #     return "Hello World!"
        #
        # @app.route("/play", methods='POST')
        # def play():
        #     media = request.form['media']
        #     self.player.play(media)
        #     return "play "+media
        #
        # @app.route("/stop", methods='POST')
        # def stop(path, args, types):
        #     self.player.stop()
        #
        # @app.route("/pause", methods='POST')
        # def pause():
        #     self.player.pause()
        #
        # @app.route("/resume", methods='POST')
        # def resume():
        #     self.player.resume()
        #
        # @app.route("/quit", methods='POST')
        # def quit(path, args, types):
        #     self.isRunning(False)

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
