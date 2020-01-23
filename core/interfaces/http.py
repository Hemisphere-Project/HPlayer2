from .base import BaseInterface
from ..engine.network import get_allip, get_hostname
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import socket
import pprint

try:
    from zeroconf import ServiceInfo, Zeroconf 
    zero_enable = True
except:
    print("import error: zeroconf is missing")
    zero_enable = False

class HttpInterface (BaseInterface):

    def  __init__(self, hplayer, port):
        super().__init__(hplayer, "HTTP")
        self._port = port

    # HTTP receiver THREAD
    def listen(self):
        # Advertize on ZeroConf
        if zero_enable:
            zeroconf = Zeroconf()
            info = ServiceInfo(
                "_api-http._tcp.local.",
                "HPlayer2._"+get_hostname()+"._api-http._tcp.local.",
                addresses=[socket.inet_aton(ip) for ip in get_allip()],
                port=self._port,
                properties={},
                server=get_hostname()+".local.",
            )
            zeroconf.register_service(info)

        # Start server
        self.log( "listening on port", self._port)
        with ThreadedHTTPServer(self._port, BasicHTTPServerHandler(self)) as server:
            self.stopped.wait()

        # Unregister ZeroConf
        if zero_enable:
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
def BasicHTTPServerHandler(httpinterface):
    class CustomHandler(BaseHTTPRequestHandler, object):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.httpinterface = httpinterface

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

            # Pre-Format arguments
            #

            if command == 'loop':
                doLoop = 2
                if len(args) > 0:
                    if args[0] == 'all' or args[0] == 2:
                        doLoop = 2
                    elif args[0] == 'one' or args[0] == 1:
                        doLoop = 1
                    else:
                        doLoop = 0
                args[0] = doLoop

            # Emit event
            #

            self.httpinterface.emit(command, *args)

            # Inner commands
            #
            if command == 'status':
                statusTree = self.httpinterface.hplayer.status()
                status = pprint.pformat(statusTree, indent=4)
                self.wfile.write( status.encode() )
                return

            elif command == 'ping':
                self.wfile.write( ('pong').encode() )
                return

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
