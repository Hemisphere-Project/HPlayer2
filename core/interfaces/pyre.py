from .base import BaseInterface
from time import sleep
from ctypes import string_at
import importlib

Pyre = None
zhelper = None
zmq = None
Zsock = None
Zmsg = None
Zpoller = None
Zactor = None
zactor_fn = None
Zyre = None
get_port = None
PING_PEER = None
Peer = None

_PYRE_IMPORT_ERROR = None
_ZMQ_IMPORT_ERROR = None
_CZMQ_IMPORT_ERROR = None
_ZYRE_IMPORT_ERROR = None

try:
    _pyre_module = importlib.import_module("pyre")
    Pyre = getattr(_pyre_module, "Pyre", None)
    zhelper = getattr(_pyre_module, "zhelper", None)
except ImportError as err:
    _PYRE_IMPORT_ERROR = err

try:
    zmq = importlib.import_module("zmq")
except ImportError as err:
    _ZMQ_IMPORT_ERROR = err

try:
    _czmq_module = importlib.import_module("czmq")
    Zsock = getattr(_czmq_module, "Zsock", None)
    Zmsg = getattr(_czmq_module, "Zmsg", None)
    Zpoller = getattr(_czmq_module, "Zpoller", None)
    Zactor = getattr(_czmq_module, "Zactor", None)
    zactor_fn = getattr(_czmq_module, "zactor_fn", None)
except ImportError as err:
    _CZMQ_IMPORT_ERROR = err

try:
    _zyre_module = importlib.import_module("zyre")
    Zyre = getattr(_zyre_module, "Zyre", None)
except ImportError as err:
    _ZYRE_IMPORT_ERROR = err

try:
    _zyre_helpers = importlib.import_module("core.interfaces.zyre")
    get_port = getattr(_zyre_helpers, "get_port", None)
    PING_PEER = getattr(_zyre_helpers, "PING_PEER", None)
    Peer = getattr(_zyre_helpers, "Peer", None)
except ImportError:
    pass


class ZyreNode ():
    def  __init__(self, interface, netiface=None):
        self.interface = interface

        # Peers book
        self.book = {}
        self.topics = []

        # Publisher
        self.pub_cache  = {}
        self.publisher  = Zsock.new_xpub(("tcp://*:*").encode())

        # TimeServer
        self.timereply = Zsock.new_rep(("tcp://*:*").encode())
        
        # Zyre 
        self.zyre = Zyre(None)
        if netiface:
            self.zyre.set_interface( string_at(netiface) )
            print("ZYRE Node forced netiface: ", string_at(netiface) )

        self.zyre.set_name(str(self.interface.hplayer.hostname()).encode())
        self.zyre.set_header(b"TS-PORT",  str(get_port(self.timereply)).encode())
        self.zyre.set_header(b"PUB-PORT", str(get_port(self.publisher)).encode())

        self.zyre.set_interval(PING_PEER)
        self.zyre.set_evasive_timeout(PING_PEER*3)
        self.zyre.set_silent_timeout(PING_PEER*5)
        self.zyre.set_expired_timeout(PING_PEER*10)

        self.zyre.start()
        self.zyre.join(b"broadcast")
        self.zyre.join(b"sync")

        # Add self to book
        self.book[self.zyre.uuid()] = Peer(self, {
            'uuid':         self.zyre.uuid(),
            'name':         self.zyre.hostname().decode(),
            'ip':           '127.0.0.1',
            'ts_port':      get_port(self.timereply),
            'pub_port':     get_port(self.publisher)
        }) 
        self.book[self.zyre.uuid()].subscribe(self.topics)

    


#
#  HPLAYER2 Pyre interface
#
class PyreInterface (BaseInterface):

    def  __init__(self, hplayer, netiface=None):
        if _PYRE_IMPORT_ERROR:
            raise RuntimeError("pyre is required for PyreInterface") from _PYRE_IMPORT_ERROR
        if _ZMQ_IMPORT_ERROR:
            raise RuntimeError("pyzmq is required for PyreInterface") from _ZMQ_IMPORT_ERROR
        if _CZMQ_IMPORT_ERROR:
            raise RuntimeError("czmq is required for PyreInterface") from _CZMQ_IMPORT_ERROR
        if _ZYRE_IMPORT_ERROR:
            raise RuntimeError("zyre is required for PyreInterface") from _ZYRE_IMPORT_ERROR
        required = [Pyre, zhelper, zmq, Zsock, Zmsg, Zpoller, Zactor, zactor_fn, Zyre, get_port, PING_PEER, Peer]
        if any(dep is None for dep in required):
            raise RuntimeError("pyre interface dependencies are unavailable")
        super().__init__(hplayer, "PYRE")        
        self.node = ZyreNode(self, netiface)
        

    def listen(self):
        self.log( "interface ready")
        self.stopped.wait()
        self.log( "closing pyre...") 
        # self.node.stop()
        # while not self.node.done:
        #     sleep(0.1)
        self.log( "done.")

    def activeCount(self):
        return 0 #len(self.node.book)

    def peersList(self):
        return [] #self.node.book
