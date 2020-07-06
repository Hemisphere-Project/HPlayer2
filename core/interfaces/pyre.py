from .base import BaseInterface
from time import sleep
from pyre import Pyre 
from pyre import zhelper 
import zmq 


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

        self.zyre.set_name(str(self.interface.hplayer.name()).encode())
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
            'name':         self.zyre.name().decode(),
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
