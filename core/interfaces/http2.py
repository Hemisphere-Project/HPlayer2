from .base import BaseInterface
import socketio
import eventlet
from flask import Flask, render_template, session, request, send_from_directory, send_file, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from werkzeug.utils import secure_filename
import threading, os, time
import queue
from PIL import Image

from ..engine.network import get_allip, get_hostname
import socket

try:
    from zeroconf import ServiceInfo, Zeroconf 
    zero_enable = True
except:
    print("import error: zeroconf is missing")
    zero_enable = False

thread = None
thread_lock = threading.Lock()


class Http2Interface (BaseInterface):

    def  __init__(self, hplayer, port, confe={}):
        super(Http2Interface, self).__init__(hplayer, "HTTP2")
        self._port = port

        self.logQuietEvents.append('do-socketio')

        self.conf = {
            'name'      : hplayer.hostname(),
            'isRPi'     : hplayer.isRPi(),
            'playlist'  : True,
            'loop'      : True,
            'mute'      : True,
            'page'      : 'full'
        }
        self.conf.update(confe)


    # HTTP receiver THREAD
    def listen(self):
        # Advertize on ZeroConf
        if zero_enable:
            zeroconf = Zeroconf()
            info = ServiceInfo(
                "_http._tcp.local.",
                "HPlayer2._"+get_hostname()+"._http._tcp.local.",
                addresses=[socket.inet_aton(ip) for ip in get_allip()],
                port=self._port,
                properties={},
                server=get_hostname()+".local.",
            )
            zeroconf.register_service(info)

        # Start server
        self.log( "web interface on port", self._port)
        with ThreadedHTTPServer(self, self._port) as server:
            self.stopped.wait()

        # Unregister ZeroConf
        if zero_enable:
            zeroconf.unregister_service(info)
            zeroconf.close()


    # SEND socketio message to clients
    def send(self, event, message):
        self.emit('do-socketio', event, message)


#
# Threaded HTTP Server
#
class ThreadedHTTPServer(object):
    def __init__(self, http2interface, port):

        self.http2interface = http2interface

        interface_path = os.path.dirname(os.path.realpath(__file__))
        www_path = os.path.join(interface_path, 'http2')

        app = Flask(__name__, template_folder=www_path)
        app.config['SECRET_KEY'] = 'secret!'
        socketio = SocketIO(app)

        #
        # FLASK Routing
        #
        @app.route('/')
        def index():
            # return render_template('index.html', async_mode=socketio.async_mode)
            # return send_from_directory(www_path, 'full.html')
            return redirect(url_for(self.http2interface.conf['page']), code=303)
        
        @app.route('/full')
        def full():
            return send_from_directory(www_path, 'full.html')
            
        @app.route('/simple')
        def simple():
            return send_from_directory(www_path, 'simple.html')
        
        @app.route('/mini')
        def mini():
            return send_from_directory(www_path, 'mini.html')

        @app.route('/filedownload', methods=['GET'])
        def filedownload():
            path = request.args.get('path')
            print(path)
            return send_file(path, as_attachment=True)

        @app.route('/upload', methods=['POST'])
        def files_upload():
            if 'file' not in request.files:
                return 'No file provided', 404

            file = request.files['file']

            # path = request.

            if file.filename == '':
                return 'No filename provided', 404

            if file and self.http2interface.hplayer.files.validExt(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(self.http2interface.hplayer.files.root_paths[0], filename)
                if os.path.exists(filepath):
                    prefix, ext = os.path.splitext(filepath)
                    filepath = prefix + '-' + ext
                file.save(filepath)
                
                try:
                    im = Image.load(filepath)
                    im.verify() #I perform also verify, don't know if he sees other types o defects
                    im.close() #reload is necessary in my case
                    im = Image.open(filepath)
                    im.thumbnail((1920, 1080), Image.ANTIALIAS)
                    im.save(filepath)
                except IOError:
                    print("cannot resize", filepath)
                except:
                    pass

                fileslist_message()
                self.http2interface.emit('file-uploaded', filepath)
                # self.http2interface.hplayer.add(filepath)
                return 'ok'

            return 'No valid file provided', 404


        @app.route('/<path:path>')
        def send_static(path):
            return send_from_directory(www_path, path)


        #
        # SOCKETIO Routing
        #
        
        self.sendQueue = queue.SimpleQueue()

        def background_thread():
            while True:
                socketio.emit('status', self.http2interface.hplayer.players()[0].status())  # {'msg': 'yo', 'timestamp': time.gmtime()}
                
                while not self.sendQueue.empty():
                    cmd = self.sendQueue.get_nowait()
                    socketio.emit(cmd[0], cmd[1])

                socketio.sleep(0.1)

        @self.http2interface.hplayer.on('settings.updated')
        @self.http2interface.hplayer.on('playlist.updated')
        def settings_send(ev, *args):
            self.sendQueue.put([ev] + list(args))

        @self.http2interface.on('do-socketio')
        def remote_send(ev, *args):
            self.sendQueue.put(args)


        @socketio.on('connect')
        def client_connect():
            socketio.emit('config',             self.http2interface.conf)
            socketio.emit('settings.updated',   self.http2interface.hplayer.settings())
            socketio.emit('playlist.updated',   self.http2interface.hplayer.playlist())
            global thread
            with thread_lock:
                if thread is None:
                    thread = socketio.start_background_task(target=background_thread)


        @socketio.on('reboot')
        def reboot_message():
            os.system('reboot')


        @socketio.on('restart')
        def restart_message():
            self.http2interface.emit('hardreset')


        @socketio.on('ping')
        def ping_message():
            socketio.send('pong')


        @socketio.on('event')
        def event_message(message=None):
            if message['event']:
                if 'data' in message:
                    self.http2interface.emit(message['event'], message['data'])
                else:
                    self.http2interface.emit(message['event'])


        @socketio.on('fileslist')
        def fileslist_message():
            def path_to_dict(path):
                if os.path.basename(path).startswith('.'):
                    return None
                d = {'text': os.path.basename(path),
                     'path': path}
                if os.path.isdir(path):
                    n = filter (None, [path_to_dict(os.path.join(path,x)) for x in sorted(os.listdir(path))])
                    d['nodes'] = [x for x in n if x is not None]
                    d['backColor'] = "#EEE"
                    d['selectable'] = False
                else:
                    d['selectable'] = True
                    d['text'] += ' <div class="media-edit float-right">'
                    d['text'] += '  <span class="badge badge-success ml-2"  onClick="mediaDownload(\''+path+'\'); event.stopPropagation();"> <i class="fas fa-download"></i> </span>';
                    d['text'] += '  <span class="badge badge-warning ml-2"  onClick="mediaEdit(\''+path+'\'); event.stopPropagation();" ><i class="far fa-edit"></i> </span>'
                    d['text'] += '  <span class="badge badge-danger ml-2"  onClick="mediaRemove(\''+path+'\'); event.stopPropagation();" ><i class="far fa-trash-alt"></i> </span>';
                    d['text'] += ' </div>';
                return d

            liste = []
            for bp in self.http2interface.hplayer.files.root_paths:
                br = path_to_dict(bp)
                if br is not None:
                    # print(br)
                    liste.append(br)

            if len(liste) > 0 and 'nodes' in liste[0]:
                socketio.emit('files', liste )
            else:
                socketio.emit('files', None )


        @socketio.on('filesdelete')
        def filesdelete_message(message=None):
            # print ('delete', message)
            if message:
                for e in message:
                    e = e.replace('/..', '')
                    for basepath in self.http2interface.hplayer.files.root_paths:
                        if e.startswith(basepath):
                            os.remove(e)
                fileslist_message()


        @socketio.on('filerename')
        def filerename_message(old, new):
            old = old.replace('/..', '')
            new = new.replace('/..', '')
            self.http2interface.log('file rename', old, new)

            check = False
            for basepath in self.http2interface.hplayer.files.root_paths:
                if old.startswith(basepath):
                    check = True
            if not check: return

            check = True
            for basepath in self.http2interface.hplayer.files.root_paths:
                if new.startswith(basepath):
                    check = True
            if not check: return

            if not os.path.exists(old): return
            
            os.rename(old, new) 
            fileslist_message()


        @socketio.on('connect', namespace='/test')
        def test_connect():
            pass


        @socketio.on('disconnect', namespace='/test')
        def test_disconnect():
            print('Client disconnected', request.sid)


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
