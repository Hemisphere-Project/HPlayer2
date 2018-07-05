from __future__ import print_function
from termcolor import colored
from time import sleep
from base import BaseInterface
import pprint

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class HttpInterface (BaseInterface):

    def  __init__(self, player, args):

        if len(args) < 1:
            print(self.nameP, 'HTTP interface needs a port')

        super(HttpInterface, self).__init__(player)

        self.name = "HTTP "+player.name
        self.nameP = colored(self.name, 'blue')

        self.port = args[0]

        self.start()

    # HTTP receiver THREAD
    def receive(self):

        print(self.nameP, "starting HTTP server on port", self.port)

        httpd = HTTPServer(('', self.port), MakeHandlerClass(self.player))
        httpd.serve_forever()

        self.isRunning(False)
        return


def MakeHandlerClass(player):
    class CustomHandler(BaseHTTPRequestHandler, object):
        def __init__(self, *args, **kwargs):
            self.player = player
            super(CustomHandler, self).__init__(*args, **kwargs)

        def _set_headers(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

        def do_GET(self):
            self._set_headers()
            args = self.path.split('/')
            args.pop(0)

            if len(args) == 0 or args[0] == '':
                self.wfile.write("<html><body><h1>Hello World!</h1></body></html>")
                return

            command = args.pop(0)

            if command == 'play':
                if len(args) > 0:
                    self.player.play(str(args[0]))
                else:
                    self.player.play()

            elif command == 'stop':
                self.player.stop()

            elif command == 'pause':
                self.player.pause()

            elif command == 'resume':
                self.player.resume()

            elif command == 'next':
                self.player.next()

            elif command == 'prev':
                self.player.prev()

            elif command == 'loop':
                self.player.loop(True)

            elif command == 'unloop':
                self.player.loop(False)

            elif command == 'volume':
                if len(args) > 0:
                    self.player.volume(int(args[0]))

            elif command == 'mute':
                self.player.mute(True)

            elif command == 'unmute':
                self.player.mute(False)

            elif command == 'status':
                statusTree = self.player._status
                while len(args) > 0:
                	key = args.pop(0)
                	status = None
                	if key in statusTree:
                		statusTree = statusTree[key]
                status = pprint.pformat(statusTree, indent=4)
                self.wfile.write(status)
                return

            elif command == 'ping':
                self.wfile.write('pong') 
                return

            elif command == 'event':
                if len(args) > 1:
                    self.player.trigger(args[0], arg[1:])
                elif len(args) > 0:
                    self.player.trigger(args[0])

            self.wfile.write("<html><body><h1>Command: "+command+" - Args: "+','.join(args)+"</h1></body></html>")
            # print("GET", self.path)


        def do_HEAD(self):
            self._set_headers()

        def do_POST(self):
             # Doesn't do anything with posted data
            content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
            post_data = self.rfile.read(content_length) # <--- Gets the data itself
            print("POST", self.path)
            print("DATA", post_data)
            self._set_headers()
            self.wfile.write("<html><body><h1>POST!</h1></body></html>")

        def log_message(self, format, *args):
            # QUIET LOG
            return

    return CustomHandler
