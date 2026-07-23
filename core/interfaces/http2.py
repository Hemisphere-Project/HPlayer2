from .base import BaseInterface
import importlib
import threading
import os
import time
import shutil
import subprocess
import queue

Flask = None
Request = None
request = None
send_from_directory = None
send_file = None
redirect = None
url_for = None
SocketIO = None
emit = None
join_room = None
leave_room = None
close_room = None
rooms = None
disconnect = None
secure_filename = None
ServiceInfo = None
Zeroconf = None
zero_enable = False

_HTTP2_IMPORT_ERRORS = []

try:
    _flask = importlib.import_module("flask")
    Flask = getattr(_flask, "Flask", None)
    Request = getattr(_flask, "Request", None)
    request = getattr(_flask, "request", None)
    send_from_directory = getattr(_flask, "send_from_directory", None)
    send_file = getattr(_flask, "send_file", None)
    redirect = getattr(_flask, "redirect", None)
    url_for = getattr(_flask, "url_for", None)
except ImportError as err:
    _HTTP2_IMPORT_ERRORS.append(("flask", err))

try:
    _socketio = importlib.import_module("flask_socketio")
    SocketIO = getattr(_socketio, "SocketIO", None)
    emit = getattr(_socketio, "emit", None)
    join_room = getattr(_socketio, "join_room", None)
    leave_room = getattr(_socketio, "leave_room", None)
    close_room = getattr(_socketio, "close_room", None)
    rooms = getattr(_socketio, "rooms", None)
    disconnect = getattr(_socketio, "disconnect", None)
except ImportError as err:
    _HTTP2_IMPORT_ERRORS.append(("flask-socketio", err))

try:
    secure_filename = importlib.import_module("werkzeug.utils").secure_filename
except ImportError as err:
    _HTTP2_IMPORT_ERRORS.append(("werkzeug", err))

try:
    _zeroconf = importlib.import_module("zeroconf")
    ServiceInfo = getattr(_zeroconf, "ServiceInfo", None)
    Zeroconf = getattr(_zeroconf, "Zeroconf", None)
    zero_enable = ServiceInfo is not None and Zeroconf is not None
except ImportError:
    zero_enable = False

from ..engine.network import get_allip, get_hostname
import socket

thread = None
thread_lock = threading.Lock()


class Http2Interface (BaseInterface):

    def  __init__(self, hplayer, port, confe={}):
        if _HTTP2_IMPORT_ERRORS:
            missing = ", ".join(name for name, _ in _HTTP2_IMPORT_ERRORS)
            raise RuntimeError(f"Http2Interface requires optional packages: {missing}")
        required = [Flask, Request, request, send_from_directory, send_file, redirect, url_for, SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect, secure_filename]
        if any(dep is None for dep in required):
            raise RuntimeError("Http2Interface dependencies are unavailable")
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

        # Unregister ZeroConf — bounded: unregister/close can hang on a
        # busy mdns stack, and this thread is non-daemon (a hang here
        # held the whole process until systemd's 90s SIGKILL).
        if zero_enable:
            def _bye():
                zeroconf.unregister_service(info)
                zeroconf.close()
            t = threading.Thread(target=_bye, daemon=True)
            t.start()
            t.join(3.0)


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

        http2interface = self.http2interface

        def upload_target(filename):
            filepath = os.path.join(http2interface.hplayer.files.root_paths[0],
                                    secure_filename(filename))
            # don't clobber a media already in the parc: clip.mp4 -> clip-2.mp4
            prefix, ext = os.path.splitext(filepath)
            n = 1
            while os.path.exists(filepath):
                n += 1
                filepath = prefix + '-' + str(n) + ext
            return filepath

        class UploadStreamingRequest(Request):
            """Write uploaded media straight to the media directory.

            Werkzeug spools every part above 500KB to a temp file, which
            file.save() then copies over: the whole media is written to the SD
            card twice and read back once. Handing the parser its destination
            makes it a single write.

            It lands on a hidden .part file (invisible to both the playlist and
            the web file tree) and is renamed into place only once complete, so
            an upload cut off mid-way -- a wifi drop, a closed tab -- never
            leaves a truncated media behind for a player to pick up.
            """

            def _get_file_stream(self, total_content_length, content_type,
                                 filename=None, content_length=None):
                self.upload_path = None
                self.upload_part = None
                if not filename or not http2interface.hplayer.files.validExt(filename):
                    # unusable anyway: spool it and let the route reject it
                    return super()._get_file_stream(total_content_length, content_type,
                                                    filename, content_length)

                self.upload_path = upload_target(filename)
                self.upload_part = os.path.join(
                                        os.path.dirname(self.upload_path),
                                        '.' + os.path.basename(self.upload_path) + '.part')
                return open(self.upload_part, 'wb+')

        app.request_class = UploadStreamingRequest

        @app.teardown_request
        def drop_partial_upload(exc):
            # upload interrupted: the route never got to rename it into place
            part = getattr(request, 'upload_part', None)
            if part and os.path.exists(part):
                try:
                    os.remove(part)
                    http2interface.log('dropped partial upload', part)
                except OSError:
                    pass

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

            filepath = getattr(request, 'upload_path', None)
            partpath = getattr(request, 'upload_part', None)

            if file and filepath:
                # streamed to partpath by UploadStreamingRequest: publish it
                file.close()
                os.replace(partpath, filepath)

                # the media list is otherwise refreshed off watchdog events,
                # whose types vary with the installed watchdog version: ask for
                # it explicitly rather than hope the right event fires
                self.http2interface.hplayer.files.refresh()

                fileslist_message()
                self.http2interface.emit('file-uploaded', filepath)
                # self.http2interface.hplayer.add(filepath)
                return 'ok'

            return 'No valid file provided', 404

        @app.route('/uploadraw/<path:filename>', methods=['PUT'])
        def files_upload_raw(filename):
            # werkzeug 1.0's multipart parser tops out ~1.2MB/s on a Pi3 core
            # (100MB = 83s of pure boundary scanning, whatever the link). A raw
            # PUT body reads at SD speed. Same .part staging as /upload above;
            # the web uploader is rerouted here by an ajaxPrefilter shim.
            if not self.http2interface.hplayer.files.validExt(filename):
                return 'No valid file provided', 404

            filepath = upload_target(filename)
            partpath = os.path.join(os.path.dirname(filepath),
                                    '.' + os.path.basename(filepath) + '.part')
            try:
                with open(partpath, 'wb') as out:
                    while True:
                        chunk = request.stream.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                    out.flush()
                    os.fsync(out.fileno())   # a power cut must never publish a truncated media
                os.replace(partpath, filepath)
            except Exception:
                try:
                    os.remove(partpath)
                except OSError:
                    pass
                raise

            self.http2interface.hplayer.files.refresh()
            fileslist_message()
            self.http2interface.emit('file-uploaded', filepath)
            return 'ok'


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
            reboot_cmd = shutil.which('reboot')
            if reboot_cmd:
                subprocess.run([reboot_cmd], check=False)
            else:
                self.http2interface.log('reboot requested but command is unavailable')


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
            def has_conduite(mediapath):
                # a real conduite = the .dmx sidecar exists with at least one
                # cue/def line (blank + # comment lines don't count)
                side = os.path.splitext(mediapath)[0] + '.dmx'
                try:
                    with open(side) as fd:
                        for line in fd:
                            s = line.strip()
                            if s and not s.startswith('#'):
                                return True
                except OSError:
                    pass
                return False

            def path_to_dict(path):
                if os.path.basename(path).startswith('.'):
                    return None
                if path.lower().endswith('.dmx'):
                    return None                     # sidecar: reached via the media's DMX chip, not listed
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
                    # blue chip when a conduite exists, light chip when none yet (click to create)
                    _dmxcls = 'badge-info' if has_conduite(path) else 'badge-light'
                    d['text'] += '  <span class="badge '+_dmxcls+' ml-2"  onClick="dmxEdit(\''+path+'\'); event.stopPropagation();" title="edit DMX conduite">DMX</span>';
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
