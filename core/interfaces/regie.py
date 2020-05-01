from .base import BaseInterface
import socketio
import eventlet
from flask import Flask, render_template, session, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from werkzeug.utils import secure_filename
import threading, os, time, queue
import logging

from ..engine.network import get_allip, get_hostname
import socket

from zeroconf import ServiceInfo, Zeroconf 

thread = None
thread_lock = threading.Lock()


class RegieInterface (BaseInterface):

    def  __init__(self, hplayer, port):
        super(RegieInterface, self).__init__(hplayer, "Regie")
        self._port = port

    # HTTP receiver THREAD
    def listen(self):

        # Advertize on ZeroConf
        zeroconf = Zeroconf()
        info = ServiceInfo(
            "_http._tcp.local.",
            "Regie._"+get_hostname()+"._http._tcp.local.",
            addresses=[socket.inet_aton(ip) for ip in get_allip()],
            port=self._port,
            properties={},
            server=get_hostname()+".local.",
        )
        zeroconf.register_service(info)

        # Start server
        self.log( "regie interface on port", self._port)
        with ThreadedHTTPServer(self, self._port) as server:
            self.stopped.wait()

        # Unregister ZeroConf
        zeroconf.unregister_service(info)
        zeroconf.close()


#
# Threaded HTTP Server
#
class ThreadedHTTPServer(object):
    def __init__(self, regieinterface, port):

        self.regieinterface = regieinterface

        interface_path = os.path.dirname(os.path.realpath(__file__))
        www_path = os.path.join(interface_path, 'regie')

        app = Flask(__name__, template_folder=www_path)
        app.config['SECRET_KEY'] = 'secret!'
        socketio = SocketIO(app, cors_allowed_origins="*")


        #
        # FLASK Routing
        #
        @app.route('/')
        def index():
            # return render_template('index.html', async_mode=socketio.async_mode)
            return send_from_directory(www_path, 'index.html')
            
        @app.route('/<path:path>')
        def send_static(path):
            return send_from_directory(www_path, path)


        #
        # SOCKETIO Routing
        #

        self.sendBuffer = queue.Queue()

        def background_thread():
            while True:
                try:
                    task = self.sendBuffer.get_nowait()
                    if len(task) > 1: socketio.emit(task[0], task[1])
                    else: socketio.emit(task[0], None)
                    self.sendBuffer.task_done()
                except queue.Empty:
                    socketio.sleep(0.1)


        @self.regieinterface.hplayer.on('files.dirlist-updated')
        def filetree_send(ev, *args):
            self.sendBuffer.put( ('fileTree', args[0]) )

        @self.regieinterface.hplayer.on('*.peer.*')
        def peer_send(ev, *args):
            args[0].update({'type': ev.split('.')[-1]})
            self.sendBuffer.put( ('dispo', args[0]) )


        # !!! TODO: stop zyre monitoring when every client are disconnected

        @socketio.on('connect')
        def client_connect():
            self.regieinterface.log('New Remote Regie connected')

        @socketio.on('init')
        def init(data):
            emit('fileTree', self.regieinterface.hplayer.files())
                        
            # Start update broadcaster
            global thread
            with thread_lock:
                if thread is None:
                    thread = socketio.start_background_task(target=background_thread)
            
            # enable peer monitoring
            self.regieinterface.emit('peers.getlink')
            self.regieinterface.emit('peers.subscribe', ['status', 'settings'])

        @socketio.on('event')
        def event(data):
            print('event', data)
            self.regieinterface.emit('peers.triggers', data, 150)


        # prepare sub-thread
        self.server_thread = threading.Thread(target=lambda:socketio.run(app, host='0.0.0.0', port=port))
        self.server_thread.daemon = True

    def start(self):
        self.server_thread.start()

    def stop(self):
        #self.server.stop()
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.stop()
