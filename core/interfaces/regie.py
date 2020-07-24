from .base import BaseInterface
import socketio
import eventlet
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from flask import Flask, render_template, session, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from werkzeug.utils import secure_filename
import threading, os, time, queue
import logging, sys, json

from ..engine.network import get_allip, get_hostname
import socket

from zeroconf import ServiceInfo, Zeroconf 

thread = None
thread_lock = threading.Lock()

REGIE_PATH = '/opt/RPi-Regie'


class RegieInterface (BaseInterface):

    def  __init__(self, hplayer, port, datapath):
        super(RegieInterface, self).__init__(hplayer, "Regie")
        self._port = port
        self._datapath = datapath

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

        localRegie = os.path.isdir(REGIE_PATH)

        if localRegie:
            www_path = os.path.join(REGIE_PATH, 'web')
        else:
            www_path = os.path.join(interface_path, 'regie')

        app = Flask(__name__, template_folder=www_path)
        app.config['SECRET_KEY'] = 'secret!'
        socketio = SocketIO(app, cors_allowed_origins="*")


        #
        # FLASK Routing
        #
        @app.route('/')
        def index():
            # self.regieinterface.log('requesting index')
            return send_from_directory(www_path, 'index.html')
            
        @app.route('/<path:path>')
        def send_static(path):
            # self.regieinterface.log('requesting '+path)
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
            self.sendBuffer.put( ('data', {'fileTree': self.regieinterface.hplayer.files()}) )

        @self.regieinterface.hplayer.on('*.peer.*')
        def peer_send(ev, *args):
            args[0].update({'type': ev.split('.')[-1]})
            self.sendBuffer.put( ('dispo', args[0]) )


        # !!! TODO: stop zyre monitoring when every client are disconnected

        @socketio.on('connect')
        def client_connect():
            self.regieinterface.log('New Remote Regie connected')


        @socketio.on('save')
        def save(data):
            try:
                json.loads(data)
                with open( os.path.join(self.regieinterface._datapath, 'project.json'), 'w') as file:
                    file.write(data)
            except:
                e = str(sys.exc_info()[0])
                self.regieinterface.log('fail to save project: '+e+' '+data)


        @socketio.on('init')
        def init(data):

            # send project
            emit('data', self.projectData())

            # Start update broadcaster
            global thread
            with thread_lock:
                if thread is None:
                    thread = socketio.start_background_task(target=background_thread)

        @socketio.on('register')
        def register(data):
            # enable peer monitoring
            self.regieinterface.emit('peers.getlink')
            self.regieinterface.emit('peers.subscribe', ['status', 'settings'])


        @socketio.on('event')
        def event(data):
            self.regieinterface.emit('peers.triggers', data, 374)


        # prepare sub-thread
        self.server_thread = threading.Thread(target=lambda:socketio.run(app, host='0.0.0.0', port=port))
        self.server_thread.daemon = True

        # watchdog project.json
        self.watcher()


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


    def projectPath(self):
        return os.path.join(self.regieinterface._datapath, 'project.json')


    def projectData(self):
        data={
            'fullproject':  '{"pool":[], "project":[[]]}',
            'fileTree':     self.regieinterface.hplayer.files()
        }
            
        if os.path.isfile(self.projectPath()):
            with open( self.projectPath(), 'r') as file:
                data['fullproject'] = file.read()

        return data


    def watcher(self):

        def onchange(e):
            self.regieinterface.log('project updated ! pushing it...')
            self.sendBuffer.put( ('data', self.projectData()) )

        handler = PatternMatchingEventHandler("*/project.json", None, False, True)
        handler.on_any_event = onchange
        self.projectObserver = Observer()
        self.projectObserver.schedule(handler, os.path.dirname(self.projectPath()))
        try:
            self.projectObserver.start()
        except:
            self.regieinterface.log('project.json not found')