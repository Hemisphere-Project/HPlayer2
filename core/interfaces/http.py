from .base import BaseInterface
from ..engine.network import get_allip
from http.server import BaseHTTPRequestHandler, HTTPServer
from zeroconf import IPVersion, ServiceInfo, Zeroconf       # https://github.com/jstasiak/python-zeroconf/
import threading
import socket


class HttpInterface (BaseInterface):

    def  __init__(self, player, port):
        super(HttpInterface, self).__init__(player, "HTTP")
        self._port = port

    # HTTP receiver THREAD
    def listen(self):
        # Advertize on ZeroConf
        zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        info = ServiceInfo(
            "_http._tcp.local.",
            "HPlayer2 HTTP api._http._tcp.local.",
            addresses=[socket.inet_aton(ip) for ip in get_allip()],
            port=self._port,
            properties={},
            server=socket.gethostname()+".local.",
        )
        zeroconf.register_service(info)

        # Start server
        self.log( "listening on port", self._port)
        with ThreadedHTTPServer(self._port, BasicHTTPServerHandler(self.player)) as server:
            self.stopped.wait()

        # Unregister ZeroConf
        zeroconf.unregister_service(info)
        zeroconf.close()


#
# Threaded HTTP Server
#
class ThreadedHTTPServer(object):
    def __init__(self, port, handler):
        self.server = HTTPServer(('', port), handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True

    def start(self):
        self.server_thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.stop()

#
# Request Handler
#
def BasicHTTPServerHandler(player):
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
                self.wfile.write( ("<html><body><h1>Hello World!</h1><p>HPlayer2 API endpoint</p></body></html>").encode() )
                return

            command = args.pop(0)

            if command == 'play':
                if len(args) > 0:
                    self.player.play(str(args[0]))
                else:
                    self.player.play()

            elif command == 'playindex':
                if len(args) > 0:
                    self.player.play(int(args[0]))

            elif command == 'playlist':
                if len(args) > 0:
                    self.player.load(args[0])
                    if len(args) > 1: self.player.play(args[1])
                    else: self.player.play()

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
                doLoop = 2
                if len(args) > 0:
                    if args[0] == 'all':
                        doLoop = 2
                    elif args[0] == 'one':
                        doLoop = 1
                    else:
                        doLoop = 0
                self.player.loop(doLoop)

            elif command == 'unloop':
                self.player.loop(0)

            elif command == 'volume':
                if len(args) > 0:
                    self.player.volume(int(args[0]))

            elif command == 'mute':
                self.player.mute(True)

            elif command == 'unmute':
                self.player.mute(False)

            elif command == 'pan':
                if len(args) > 1:
                    self.player.pan(int(args[0]), int(args[1]))

            elif command == 'flip':
                self.player.flip(True)

            elif command == 'unflip':
                self.player.flip(False)

            elif command == 'status':
                statusTree = self.player._status
                while len(args) > 0:
                	key = args.pop(0)
                	status = None
                	if key in statusTree:
                		statusTree = statusTree[key]
                status = pprint.pformat(statusTree, indent=4)
                self.wfile.write( status.encode() )
                return

            elif command == 'ping':
                self.wfile.write( ('pong').encode() )
                return

            elif command == 'event':
                if len(args) > 1:
                    self.player.trigger(args[0], arg[1:])
                elif len(args) > 0:
                    self.player.trigger(args[0])

            #self.wfile.write( ("<html><body><h1>Command: "+command+" - Args: "+','.join(args)+"</h1></body></html>").encode() )
            self.wfile.write( ("").encode() )
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
            self.wfile.write( ("<html><body><h1>POST!</h1></body></html>").encode() )

        def log_message(self, format, *args):
            # QUIET LOG
            return

    return CustomHandler
