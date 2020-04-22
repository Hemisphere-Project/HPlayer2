from .base import BaseInterface
import socketio
import eventlet
from flask import Flask, render_template, session, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from werkzeug.utils import secure_filename
import threading, os, time
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

        self.sendLock = threading.Lock()
        self.dataLock = threading.Lock()
        self.dataLock.acquire()

        self.sendEvent = None
        self.sendData = None

        def sendAsync(event, data):
            self.sendLock.acquire()
            self.sendEvent = event
            self.sendData = data
            self.dataLock.release()

        def background_thread():
            while True:
                while self.dataLock.locked():
                    socketio.sleep(0.1)

                self.dataLock.acquire()
                socketio.emit(self.sendEvent, self.sendData)
                self.sendLock.release()


        @self.regieinterface.hplayer.on('files.dirlist-updated')
        def filetree_send(*args):
            sendAsync('fileTree', args[0])

        @self.regieinterface.hplayer.on('*.peer.status')
        def peerstatus_send(*args):
            sendAsync('peer.status', args[0])


        @self.regieinterface.hplayer.on('*.peer.settings')
        def peersettings_send(*args):
            sendAsync('peer.settings', args[0])

        # !!! TODO: stop zyre monitoring when every client are disconnected

        @socketio.on('connect')
        def client_connect():
            emit('fileTree', self.regieinterface.hplayer.files())
            
            # enable peer monitoring
            self.regieinterface.emit('peers.subscribe', ['status', 'settings'])
            
            # Start update broadcaster
            global thread
            with thread_lock:
                if thread is None:
                    thread = socketio.start_background_task(target=background_thread)


        @socketio.on('PLAY')
        def play(data):
            print("PLAY", data)

        @socketio.on('PLAYSEQ')
        def playseq(data):
            print("PLAYSEQ", data)

        @socketio.on('MUTE')
        def mute(data):
            print("MUTE", data)

        @socketio.on('LOOP')
        def loop(data):
            print("LOOP", data)

        @socketio.on('PAUSE')
        def pause(data):
            print("PAUSE", data)

        @socketio.on('STOP')
        def stop(data):
            print("STOP", data)

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
