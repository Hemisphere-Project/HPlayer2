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
        self.upload_folder = self.player.basepath[0]

        interface_path = os.path.dirname(os.path.realpath(__file__))
        www_path = os.path.join(interface_path, 'http2')

        app = Flask(__name__, template_folder=www_path)
        app.config['SECRET_KEY'] = 'secret!'
        socketio = SocketIO(app, async_mode='eventlet')


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
                return 'No file provided'

            file = request.files['file']

            if file.filename == '':
                return 'No file provided'

            if file and self.player.validExt(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(self.upload_folder, filename))
                fileslist_message()
                return 'ok'

            return 'No file provided'


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

        self.player.on(['settings-update'], settings_send)

        @socketio.on('connect')
        def client_connect():
            socketio.emit('settings', self.player.settings())
            global thread
            with thread_lock:
                if thread is None:
                    thread = socketio.start_background_task(target=background_thread)

        @socketio.on('play')
        def play_message(message=None):
            if message and message['path']:
                self.player.play(message['path'])
            else:
                self.player.play()

        @socketio.on('stop')
        def stop_message():
            self.player.stop()

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
        def loop_message():
            self.player.loop(True)

        @socketio.on('unloop')
        def unloop_message():
            self.player.loop(False)

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
                return d

            liste = path_to_dict(self.upload_folder)
            if 'nodes' in liste:
                socketio.emit('files', liste['nodes'] )
            else:
                socketio.emit('files', None )

        @socketio.on('filesdelete')
        def filesdelete_message(message=None):
            # print ('delete', message)
            if message:
                for e in message:
                    filename = secure_filename(e['text'])
                    os.remove(os.path.join(self.upload_folder, filename))

                fileslist_message()

        #
        #
        # @socketio.on('my_broadcast_event', namespace='/hplayer2')
        # def test_broadcast_message(message):
        #     session['receive_count'] = session.get('receive_count', 0) + 1
        #     emit('my_response',
        #          {'data': message['data'], 'count': session['receive_count']},
        #          broadcast=True)
        #
        #
        # @socketio.on('join', namespace='/test')
        # def join(message):
        #     join_room(message['room'])
        #     session['receive_count'] = session.get('receive_count', 0) + 1
        #     emit('my_response',
        #          {'data': 'In rooms: ' + ', '.join(rooms()),
        #           'count': session['receive_count']})
        #
        #
        # @socketio.on('my_ping', namespace='/test')
        # def ping_pong():
        #     emit('my_pong')


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
