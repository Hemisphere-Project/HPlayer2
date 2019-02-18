from .base import BaseInterface
import socketio
import eventlet
from flask import Flask, render_template, session, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from werkzeug.utils import secure_filename
import threading, os, time
import logging

thread = None
thread_lock = threading.Lock()


class Http2Interface (BaseInterface):

    def  __init__(self, player, port):
        super(Http2Interface, self).__init__(player, "HTTP")
        self._port = port
        self.player = player

    # HTTP receiver THREAD
    def listen(self):

        # Start server
        self.log( "listening on port", self._port)
        with ThreadedHTTPServer(self._port, self.player) as server:
            self.stopped.wait()


#
# Threaded HTTP Server
#
class ThreadedHTTPServer(object):
    def __init__(self, port, player):

        self.player = player

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
            return send_from_directory(www_path, 'index.html')

        @app.route('/upload', methods=['POST'])
        def files_upload():
            if 'file' not in request.files:
                return 'No file provided', 404

            file = request.files['file']

            if file.filename == '':
                return 'No filename provided', 404

            if file and self.player.validExt(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(self.player.basepath[0], filename)
                if os.path.exists(filepath):
                    prefix, ext = os.path.splitext(filepath)
                    filepath = prefix + '-' + ext
                file.save(filepath)
                fileslist_message()
                self.player.add(filepath)
                return 'ok'

            return 'No valid file provided', 404


        @app.route('/<path:path>')
        def send_static(path):
            return send_from_directory(www_path, path)


        #
        # SOCKETIO Routing
        #

        def background_thread():
            while True:
                socketio.emit('status', self.player.status())  # {'msg': 'yo', 'timestamp': time.gmtime()}
                socketio.sleep(0.1)

        def settings_send(arg):
            socketio.emit('settings', arg)

        def playlist_send(arg=None):
            socketio.emit('playlist', arg)

        self.player.on(['settings-update'], settings_send)
        self.player.on(['playlist-update'], playlist_send)

        @socketio.on('connect')
        def client_connect():
            socketio.emit('settings', self.player.settings())
            socketio.emit('name', self.player.name)
            global thread
            with thread_lock:
                if thread is None:
                    thread = socketio.start_background_task(target=background_thread)

        @socketio.on('play')
        def play_message(message=None):
            if message and 'path' in message:
                self.player.play(message['path'])
            elif message and 'index' in message:
                self.player.play(int(message['index']))
            else:
                self.player.play()

        @socketio.on('stop')
        def stop_message():
            self.player.stop()

        @socketio.on('clear')
        def clear_message():
            self.player.clear()

        @socketio.on('add')
        def add_message(path):
            self.player.add(path)

        @socketio.on('remove')
        def rm_message(index):
            self.player.remove(index)

        @socketio.on('pause')
        def pause_message():
            self.player.pause()

        @socketio.on('resume')
        def resume_message():
            self.player.resume()

        @socketio.on('next')
        def next_message():
            self.player.next()

        @socketio.on('prev')
        def prev_message():
            self.player.prev()

        @socketio.on('loop')
        def loop_message(mode=None):
            doLoop = 1
            if mode:
                if mode == 'all':
                    doLoop = 2
                elif mode == 'one':
                    doLoop = 1
                else:
                    doLoop = 0
            self.player.loop(doLoop)

        @socketio.on('unloop')
        def unloop_message():
            self.player.loop(0)

        @socketio.on('volume')
        def volume_message(message=None):
            if message:
                self.player.volume(int(message))

        @socketio.on('mute')
        def mute_message():
            self.player.mute(True)

        @socketio.on('unmute')
        def unmute_message():
            self.player.mute(False)

        @socketio.on('autoplay')
        def mute_message():
            self.player.autoplay(True)

        @socketio.on('notautoplay')
        def unmute_message():
            self.player.autoplay(False)

        @socketio.on('reboot')
        def reboot_message():
            os.system('reboot')

        @socketio.on('pan')
        def pan_message(message=None):
            if message and len(message) == 2:
                self.player.pan([int(message[0]), int(message[1])])

        @socketio.on('flip')
        def flip_message():
            self.player.flip(True)

        @socketio.on('unflip')
        def unflip_message():
            self.player.flip(False)

        @socketio.on('status')
        def status_message():
            pass

        @socketio.on('ping')
        def ping_message():
            socketio.send('pong')

        @socketio.on('event')
        def event_message(message=None):
            if message['event']:
                if message['data']:
                    self.player.trigger(message['event'], message['data'])
                else:
                    self.player.trigger(message['event'])

        @socketio.on('fileslist')
        def fileslist_message():
            def path_to_dict(path):
                d = {'text': os.path.basename(path),
                     'path': path}
                if os.path.isdir(path):
                    d['nodes'] = [path_to_dict(os.path.join(path,x)) for x in sorted(os.listdir(path))]
                    d['backColor'] = "#EEE"
                    d['selectable'] = False
                else:
                    d['selectable'] = True
                    d['text'] += ' <div class="media-edit float-right">';
                    d['text'] += '  <span class="badge badge-success" onClick="playlistAdd(\''+path+'\'); event.stopPropagation();"> <i class="fas fa-plus"></i> </span>';
                    # d['text'] += '  <span class="badge badge-danger ml-2"><i class="far fa-trash-alt"></i> </span>';
                    d['text'] += ' </div>';
                return d

            liste = []
            for bp in self.player.basepath:
                liste.append(path_to_dict(bp))

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
                    for basepath in self.player.basepath:
                        if e.startswith(basepath):
                            os.remove(e)
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
