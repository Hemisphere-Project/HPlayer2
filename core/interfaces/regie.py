from .base import BaseInterface
import eventlet
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from flask import Flask, render_template, session, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from werkzeug.utils import secure_filename
import threading, os, time, queue
import logging, sys, json
import urllib.request

from ..engine.network import get_allip, get_hostname
import socket

from zeroconf import ServiceInfo, Zeroconf 

thread = None
thread_lock = threading.Lock()

REGIE_PATH1 = '/opt/RPi-Regie'
REGIE_PATH2 = '/data/RPi-Regie'

# NDI sources for the grid's media picker (backport of master's regie.py, 2026-09-11, IMA-Niort).
# HNdi input nodes (the x86 kmini players) expose the NDI sources they see on http://<node>:8791
# (hndi.conf api_bind = 0.0.0.0). This Régie — served from casa, which runs no HNdi — asks:
#   - the hosts listed in /boot/ndi-nodes.txt (one per line, host[:port]), if that file exists;
#   - else itself and EVERY active Zyre peer (a Pi refuses the connection in a millisecond, a
#     mini answers) — zero configuration, follows the fleet as it changes.
# The union of names is pushed to the pages as {'ndiSources': [...]} whenever it changes; a
# pick becomes a `<source>.ndi` file in the scene folder (see the 'ndifile' handler) — an
# ordinary synced media that every player, 2025 Pi or 2026 mini, dispatches unchanged.
NDI_API_PORT = 8791
NDI_POLL_S = 5
NDI_NODES_FILE = '/boot/ndi-nodes.txt'


class RegieInterface (BaseInterface):

    def  __init__(self, hplayer, port, datapath):
        super(RegieInterface, self).__init__(hplayer, "Regie")
        self._port = port
        self._datapath = datapath
        self._server = None
        self._ndi_sources = []      # names seen by the HNdi nodes of the fleet ([] = none)



    # HTTP receiver THREAD
    def listen(self):

        try:
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
        except Exception as e:
            self.log("Error while registering Zeroconf service:", e)

        # Start server
        self.log( "regie interface on port", self._port)
        with ThreadedHTTPServer(self, self._port) as server:
            self._server = server
            # keep the NDI source list fresh while serving (no node anywhere → stays empty)
            while not self.stopped.wait(NDI_POLL_S):
                self.pollNdiSources()

        self._server = None
        
        # Unregister ZeroConf
        zeroconf.unregister_service(info)
        zeroconf.close()
        
        
    def ndiNodes(self):
        """base URLs of the HNdi APIs to ask: /boot/ndi-nodes.txt if present, else self + active peers"""
        hosts = []
        try:
            with open(NDI_NODES_FILE) as fd:
                hosts = [l.strip() for l in fd if l.strip() and not l.strip().startswith('#')]
        except Exception:  # noqa: BLE001 — no file: discover
            pass
        if not hosts:
            hosts = ['127.0.0.1']
            try:
                zyre = self.hplayer.interface('zyre')
                for peer in list(zyre.node.book.values()) if zyre else []:
                    ip = getattr(peer, 'ip', None)
                    if ip and getattr(peer, 'active', True) and ip not in hosts:
                        hosts.append(ip)
            except Exception:  # noqa: BLE001
                pass
        return ['http://' + (h if ':' in h else h + ':' + str(NDI_API_PORT)) for h in hosts]

    def pollNdiSources(self):
        """ask every HNdi node for the NDI sources it sees; push the union to the Regie
        pages when it changes. A host with no node refuses or times out: silently skipped."""
        names = []
        for base in self.ndiNodes():
            try:
                with urllib.request.urlopen(base + '/sources', timeout=0.7) as r:
                    for x in json.loads(r.read().decode()):
                        n = x.get('name', '') if isinstance(x, dict) else ''
                        if n and n not in names:
                            names.append(n)
            except Exception:  # noqa: BLE001 — refused, timeout, bad json: no node there
                continue
        if names != self._ndi_sources:
            self._ndi_sources = names
            self.log('NDI sources:', names)
            if self._server:
                self._server.sendBuffer.put(('data', {'ndiSources': names}))

    def projectPath(self):
        return os.path.join(self._datapath, 'project.json')
    

    def projectRaw(self):
        project =  '{"pool":[], "project":[[]]}'
        if os.path.isfile(self.projectPath()):
            with open( self.projectPath(), 'r') as file:
                project = file.read()
        return project
        
        
    # parse locally for programatic execution
    def reload(self):    
        try:
            self._project = json.loads(self.projectRaw())
        except:
            self._project = None
            self.log("Error while parsing project..")
            
        # print(self._project)
        
        return self._project
    
    
    # play sequence
    def playseq(self, sceneIndex, seqIndex):
        self.log("PLAYSEQ")
        
        try:
            # self.log('PLAYSEQ', seqIndex, sceneIndex, boxes)
            orderz = []
            boxes = [b for b in self._project["project"][0][sceneIndex]["allMedias"] if b["y"] == seqIndex]
            for b in boxes:
                peerName = self._project["pool"][ b["x"] ]["name"]
                
                # MEDIA
                order = { 'peer': peerName, 'synchro':  True}
                
                if b["media"] in ['stop', 'pause', 'unfade'] :
                    order["event"] = b["media"]
                elif b["media"] == '...':
                    order["event"] = 'continue'
                elif b["media"].startswith('fade'):
                    order["event"] = 'fade'
                    order["data"] = b["media"].split('fade ')[1]
                else:
                    order["event"] = 'playthen'
                    order["data"] = [ self._project["project"][0][sceneIndex]["name"] + '/' + b["media"] ]
                    
                    # ON MEDIA END
                    if 'onend' in b:
                        if b['onend'] == 'next':
                            order["data"].append( {'event': 'do-playseq', 'data': [sceneIndex, seqIndex+1] } )
                        elif b['onend'] == 'prev':
                            order["data"].append( {'event': 'do-playseq', 'data': [sceneIndex, seqIndex-1] } )
                        elif b['onend'] == 'replay':
                            order["data"].append( {'event': 'do-playseq', 'data': [sceneIndex, seqIndex] } )                  
    
                orderz.append(order)
                
                # LOOP
                if b["loop"] == 'loop':
                    orderz.append( { 'peer': peerName, 'event':  'loop', 'data': 1} )
                elif b["loop"] == 'unloop':
                    orderz.append( { 'peer': peerName, 'event':  'unloop'} )

                # LIGHT
                if b["light"] and b["light"] != '...':
                    order = { 'peer': peerName, 'synchro':  True, 'event': 'esp'}
                    
                    if b["light"].startswith('light'):
                        order["data"] = {
                            'topic': 'leds/all',
                            'data': b["light"].split('light ')[1]
                        }
                    
                    elif b["light"].startswith('preset'):
                        order["data"] = {
                            'topic': 'leds/mem',
                            'data': b["light"].split('preset ')[1]
                        }
                        
                    elif b["light"].startswith('off'):
                        order["data"] = {
                            'topic': 'leds/stop',
                            'data': ''
                        }
                        
                    orderz.append(order)
                    
            self.emit('playingseq', sceneIndex, seqIndex)
            
            
            self.emit('peers.triggers', orderz, 437)

        except:
            self.log('Error playing Scene', sceneIndex, 'Seq', seqIndex)
            
    
 

#
# Threaded HTTP Server
#
class ThreadedHTTPServer(object):
    def __init__(self, regieinterface, port):

        self.regieinterface = regieinterface

        interface_path = os.path.dirname(os.path.realpath(__file__))

        if os.path.isdir(REGIE_PATH1):
            www_path = os.path.join(REGIE_PATH1, 'web')
        elif os.path.isdir(REGIE_PATH2):
            www_path = os.path.join(REGIE_PATH2, 'web')
        else:
            www_path = os.path.join(interface_path, 'regie')

        app = Flask(__name__, template_folder=www_path)
        app.config['SECRET_KEY'] = 'secret!'
        socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100_000_000)


        #
        # FLASK Routing Static
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
        # FLASK Routing API
        #
        
        # @app.route('/<path:path>')
        # def send_static(path):
        #     # self.regieinterface.log('requesting '+path)
        #     return send_from_directory(www_path, path)

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
            
        @self.regieinterface.hplayer.on('files.activedir-updated')
        def activedir_send(ev, *args):
            self.sendBuffer.put( ('data', {'scene': args[1]}) )

        @self.regieinterface.hplayer.on('*.peer.*')
        def peer_send(ev, *args):
            event = ev.split('.')[-1]
            if event == 'playingseq':
                print(ev, args[0]['data'][1])
                self.sendBuffer.put( ('data', {'sequence': args[0]['data'][1]}) )
            else:
                args[0].update({'type': event})
                self.sendBuffer.put( ('peer', args[0]) )


        # !!! TODO: stop zyre monitoring when every client are disconnected

        @socketio.on('connect')
        def client_connect():
            self.regieinterface.log('New Remote Regie connected')


        @socketio.on('save')
        def save(data):
            print("SAAAAVE")
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
            self.regieinterface.emit('peers.subscribe', ['status', 'settings', 'playingseq'])


        @socketio.on('event')
        def event(data):
            self.regieinterface.emit('peers.triggers', data, 437)

        @socketio.on('ndifile')
        def ndifile(data):
            """An NDI source picked in the grid becomes a `.ndi` FILE in the scene folder
            (first line = source name). It travels with the synced media tree and every
            peer plays it as an ordinary media, so the sequence chaining stays compatible
            with players whose regie.py knows nothing of NDI (the sacvp Pis)."""
            try:
                scene = os.path.basename(str(data.get('scene', '')).strip())
                source = str(data.get('source', '')).strip()
                if not scene or not source:
                    return
                safe = ''.join(c if c.isalnum() or c in ' ()-_.' else '_' for c in source)
                name = safe + '.ndi'
                # the scene folder lives in the first base path that has it (the synced show tree)
                for base in self.regieinterface.hplayer.files.root_paths:
                    folder = os.path.join(base, scene)
                    if os.path.isdir(folder):
                        path = os.path.join(folder, name)
                        if not os.path.exists(path):
                            with open(path, 'w') as fd:
                                fd.write(source + '\n')
                            self.regieinterface.log('ndi file created', path)
                            self.regieinterface.hplayer.files.refresh()
                        emit('ndifile', {'scene': scene, 'name': name})
                        return
                self.regieinterface.log('ndifile: no folder for scene', scene)
            except Exception as e:  # noqa: BLE001
                self.regieinterface.log('ndifile error', e)


        # prepare sub-thread
        self.server_thread = threading.Thread(target=lambda:socketio.run(app, host='0.0.0.0', port=port))
        self.server_thread.daemon = True
        
        # watchdog project.json
        self.watcher()
        
        # internal load project
        self.regieinterface.reload()


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
        
    
    def projectData(self):
        data={
            'fullproject':  self.regieinterface.projectRaw(),
            'fileTree':     self.regieinterface.hplayer.files()
        }
        return data
    
    
    def watcher(self):
    
        def onchange(e):
            self.regieinterface.log('project updated ! pushing it...')
            self.regieinterface.reload()
            self.sendBuffer.put( ('data', self.projectData()) )

        handler = PatternMatchingEventHandler("*/project.json", None, False, True)
        handler.on_any_event = onchange
        self.projectObserver = Observer()
        self.projectObserver.schedule(handler, os.path.dirname(self.regieinterface.projectPath()))
        try:
            self.projectObserver.start()
        except:
            self.regieinterface.log('project.json not found')