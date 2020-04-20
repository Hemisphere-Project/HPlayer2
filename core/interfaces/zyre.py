from .base import BaseInterface
from zyre import Zyre, ZyreEvent
from czmq import *
import time, random
from time import sleep
import json
from threading import Timer, Lock


from ctypes import string_at
from sys import getsizeof
from binascii import hexlify

# current_milli_time = lambda: int(round(time.time() * 1000))

def get_port(sock):
    if not sock: 
        print('ERROR while binding socket')
        return 0
    return sock.endpoint().decode().split(':')[2]

def extract_ip(x): 
    return str(x).split('//')[1].split(':')[0]

def zlist_strlist(zlist):
    list = []
    el = zlist.pop()
    while el:
        list.append(string_at(el).decode())
        el = zlist.pop()
    return list




PRECISION = 1000000
SAMPLER_SIZE = 500
KEEP_SAMPLE = [0.01, 0.3]


#
#  Round Trip REQ-REP Time sample
#
class TimeSample():
    def __init__(self, sock):
        self.sock = sock
        self.LT1 = int(time.time()*PRECISION)
        msg = Zmsg()
        msg.addstr( str(self.LT1).encode() )
        Zmsg.send( msg, self.sock)

    def recv(self):
        if not self.sock:
            return
        self.LT2 = int(time.time()*PRECISION)
        self.ST = int(Zmsg.recv(self.sock).popstr().decode())
        self.sock = None
        self.RTT = self.LT2 - self.LT1
        self.CS = self.ST - (self.RTT/2) - self.LT1


#
#  CLIENT Actor to perform Clock Shift measurment with a remote peer
#
class TimeClient():
    def __init__(self, ip, port):
        self.client_ip = ip
        self.url = ("tcp://"+self.client_ip+":"+port).encode()
        self.clockshift = 0
        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        self.done = True
        self.start()

    def start(self):
        if not self.done: 
            self.stop()
        
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Sync request"))
        self.done = False
        
        self._refresh = Timer(60, self.start)
        self._refresh.start()

    def stop(self):
        if not self.done:
            self.actor.sock().send(b"s", b"$TERM")
        if self._refresh:
            self._refresh.cancel()
        self.done = True


    # CLIENT TimeSync REQ Zactor
    def actor_fn(self, pipe, args):
        self.status = 4
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        req_sock = Zsock.new_req(self.url)
        poller = Zpoller(internal_pipe, req_sock, None)
        internal_pipe.signal(0)
        retry = 0

        # print("TimeClient: Starts sampling", self.client_ip)

        sampler = []
        sample = TimeSample(req_sock)

        terminated = False
        while not terminated and retry < 10:
            sock = poller.wait(500)

            # NOBODY responded ...
            if not sock:
                sample = TimeSample(req_sock)
                retry += 1

            # REP received
            elif sock == req_sock:
                retry = 0
                sample.recv()
                sampler.append( sample )
                # print("Pong", sample.RTT, sample.CS)
                if len(sampler) >= SAMPLER_SIZE:
                    break
                sample = TimeSample(req_sock)

            # INTERNAL commands
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg or msg.popstr() == b"$TERM":
                    return

        # print("TimeClient: Sampling done", self.client_ip)
        self.compute(sampler)
        self.done = True


    #  COMPUTE average Clock Shift
    #  - remove firsts samples / keep 70% lower RTT / ponderate lower RTT -
    def compute(self, sampler):
        if len(sampler) >= SAMPLER_SIZE:
            RTTs = sorted(sampler, key=lambda x: x.RTT)
            RTTs = RTTs[int(len(RTTs) * KEEP_SAMPLE[0]) : int(len(RTTs) * KEEP_SAMPLE[1])]
            sampler = RTTs
            sampler.reverse()

            cs = 0
            cs_count = 0
            for k, s in enumerate(sampler):
                p = 10*k/len(sampler)   # higher index are lower RTT -> more value
                cs += s.CS * p
                cs_count += p
            if cs_count > 0:
                cs = int(cs/cs_count)

            print(self.client_ip, "clock shift", str(cs)+"ns", "using", len(sampler), "samples")
            if self.clockshift:
                print('\t correction =', str(self.clockshift-cs)+"ns" )
            self.clockshift = cs
            self.status = 1
        else:
            self.status = 0
            print("ERROR: sampler not full.. something might be broken")


#
#  SERVER to handle Time sync request from remote clients
#
class TimeServer():
    def  __init__(self):
        self.port = 0
        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Sync reply"))
        self.done = False

    def stop(self):
        if not self.done:
            self.actor.sock().send(b"s", b"$TERM")

    # REPLY Sync Zactor
    def actor_fn(self, pipe, args):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        reply_sock = Zsock.new_rep(("tcp://*:*").encode())
        if not reply_sock:
            print('ERROR while binding PeerBook REP socket')
        else:
            self.port = reply_sock.endpoint().decode().split(':')[2]

        poller = Zpoller(internal_pipe, reply_sock, None)
        internal_pipe.signal(0)

        # print('TimeServer started on port', self.port)
        terminated = False
        while not terminated:
            sock = poller.wait(500)
            if not sock:
                continue

            # REQ received
            if sock == reply_sock:
                msgin = Zmsg.recv(reply_sock)
                msg = Zmsg()
                msg.addstr(str(int(time.time()*PRECISION)).encode())
                Zmsg.send( msg, reply_sock )
                # self.log("Go")

            # INTERNAL commands
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg or msg.popstr() == b"$TERM":
                    break

        # print('TimeServer stopped')
        reply_sock.__del__()
        self.done = True


#
#  SUBSCRIBER to others publishing
#
class Subscriber():
    def __init__(self, node, ip, port, topic):
        self.node = node
        self.client_ip = ip
        self._topics = [topic]
        self.url = ("tcp://"+self.client_ip+":"+port).encode()
        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        self.done = True
        self.start()

    def start(self):
        if not self.done: 
            self.stop()
        
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Subscriber"))
        self.done = False
        

    def stop(self):
        if not self.done:
            self.actor.sock().send(b"s", b"$TERM")
        self.done = True

    # SUB Zactor
    def actor_fn(self, pipe, args):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        sub_sock = Zsock.new_sub(self.url, self._topics[0].encode())
        poller = Zpoller(internal_pipe, sub_sock, None)
        internal_pipe.signal(0)

        print("Subscribing to", self.client_ip)

        terminated = False
        while not terminated:
            sock = poller.wait(500)

            # NOBODY responded ...
            if not sock:
                continue

            # SUB received
            elif sock == sub_sock:
                msg = Zmsg.recv(sub_sock)
                topic = msg.popstr().decode()
                uuid = msg.popstr()
                peer = self.node.peerbook.peer(uuid)
                name = peer['name'] if peer else uuid.decode()
                data = json.loads(msg.popstr().decode())
                arg = {'peer': name, 'data': data}
                self.node.zyre.emit(topic, arg)

            # INTERNAL commands
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg or msg.popstr() == b"$TERM":
                    break

        sub_sock.__del__()
        self.done = True


#
#  BOOK to perform and record sync with others
#
class PeerBook():
    def  __init__(self, node):
        self.node = node
        self.phonebook = {}
        self._lock = Lock()
        self._topics = []

    def stop(self):
        with self._lock:
            for peer in self.phonebook.values():
                if peer['sync']: 
                    peer['sync'].stop()
                for t in peer['subscriber']:
                    peer['subscriber'][t].stop()


    def newpeer(self, peer):

        # peer completion
        peer['sync'] = None
        peer['status'] = None
        peer['subscriber'] = {}

        # add to phonebook
        uuid = peer['uuid']
        self.gone(uuid)
        with self._lock:
            self.phonebook[uuid] = peer
            # print("New Peer detected", self.phonebook[uuid])

        # subscribe to if necessary
        for topic in self._topics:
            self.subscribePeer(topic, uuid)


    def peer(self, uuid):
        if uuid in self.phonebook:
            return self.phonebook[uuid]
        else:
            return None


    def sync(self, uuid):
        with self._lock:
            peer = self.peer(uuid)
            if peer: peer['sync'] = TimeClient(peer['ip'], peer['ts_port'])


    def gone(self, uuid):
        with self._lock:
            if uuid in self.phonebook:
                del self.phonebook[uuid]

    def activeCount(self):
        return len(self.phonebook)


    def cs(self, uuid):
        shift = 0
        with self._lock:
            peer = self.peer(uuid)
            if peer and peer['sync']:
                shift = peer['sync'].clockshift
        return shift


    def subscribePeer(self, topic, uuid):
        peer = self.peer(uuid)
        if peer:
            with self._lock:
                # Close previous subscription
                if topic in peer['subscriber']:
                    peer['subscriber'][topic].stop()

                peer['subscriber'][topic] = Subscriber(self.node, peer['ip'], peer['pub_port'], topic)
            

    def subscribeAll(self, topic):
        with self._lock:
            if not topic in self._topics:
                self._topics.append(topic)
        for uuid in self.phonebook.keys():
            self.subscribePeer(topic, uuid)



#
#  NODE zyre peers discovery, sync and communication
#
class ZyreNode ():
    def  __init__(self, zyre, iface=None):
        self.zyre = zyre
        
        self.peerbook = PeerBook(self)


        self.timeserver = TimeServer()

        # Publisher
        self.pub_cache  = {}
        self.pub_sock   = Zsock.new_xpub(("tcp://*:*").encode())
        self.pub_port   = get_port( self.pub_sock )
        
        # Zyre 
        self.zyre_node = Zyre(None)
        if iface:
            self.zyre_node.set_interface( string_at(iface) )
            print("ZYRE Node forced iface: ", string_at(iface) )

        self.zyre_node.set_name(str(self.zyre.hplayer.name()).encode())
        self.zyre_node.set_header(b"TS-PORT", str(self.timeserver.port).encode())
        self.zyre_node.set_header(b"PUB-PORT", str(self.pub_port).encode())

        self.zyre_node.set_interval(1000)
        self.zyre_node.set_evasive_timeout(5000)
        self.zyre_node.set_silent_timeout(8000)
        self.zyre_node.set_expired_timeout(15000)

        self.zyre_node.start()
        self.zyre_node.join(b"broadcast")
        self.zyre_node.join(b"sync")

        self.zyre_sock = self.zyre_node.socket()
        


        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        if iface:
            iface = create_string_buffer(str.encode(iface))
        self.actor = Zactor(self._actor_fn, iface)
        self.done = False


    def stop(self):
        self.timeserver.stop()
        self.peerbook.stop()
        if not self.done:
            self.actor.sock().send(b"ss", b"$TERM", "gone")
            # self.zyre.log('ZYRE term sent')

    def publish(self, topic, args=None, delay_ms=0):
        # self.actor.sock().send(b"sss", b"PUBLISH", topic.encode(), json.dumps(args).encode())
        topic = topic.encode()
        
        msg = Zmsg()
        msg.addstr(topic)
        msg.addstr(self.zyre_node.uuid())
        msg.addstr(json.dumps(args).encode())

        self.pub_cache[topic] = Zmsg.dup(msg)
        Zmsg.send(msg, self.pub_sock)

    def makeMsg(self, event, args=None, delay_ms=0):
        data = {}
        data['event'] = event
        data['args'] = []
        if args:
            if not isinstance(args, list):
                # self.zyre.log('NOT al LIST', args)
                args = [args]
            data['args'] = args

        # add delay
        if delay_ms > 0:
            data['at'] = int(time.time()*PRECISION + delay_ms * PRECISION / 1000)

        return json.dumps(data).encode()

    def whisper(self, uuid, event, args=None, delay_ms=0):
        data = self.makeMsg(event, args, delay_ms)
        if uuid == 'self':
            data = json.loads(data.decode())
            data['from'] = 'self'
            data['group'] = 'whisper'
            self.preProcessor1(data)
        else:
            self.zyre_node.whispers(uuid, data)

    def shout(self, group, event, args=None, delay_ms=0):
        data = self.makeMsg(event, args, delay_ms)
        self.zyre_node.shouts(group.encode(), data)

        # if own group -> send to self too !
        groups = zlist_strlist( self.zyre_node.own_groups() )
        if group in groups:
            data = json.loads(data.decode())
            data['from'] = 'self'
            data['group'] = group
            self.preProcessor1(data)

    def broadcast(self, event, args=None, delay_ms=0):
        self.shout('broadcast', event, args, delay_ms)

    def join(self, group):
        self.zyre_node.join(group.encode())

    def leave(self, group):
        self.zyre_node.leave(group.encode())

    def preProcessor1(self, data):
        # if a programmed time is provided, correct it with peer CS
        # Set timer
        if 'at' in data:
            data['at'] -= self.peerbook.cs( data['from'] )
            delay =  (data['at']) / PRECISION - time.time()


            if delay <= 0:
                self.preProcessor2(data)
            else:
                self.zyre.log('programmed event in', delay, 'seconds')
                t = Timer( delay, self.preProcessor2, args=[data])
                t.start()
                self.zyre.emit('planned', data)

        else:
            self.preProcessor2(data)

    def preProcessor2(self, data):
        self.zyre.emit('event', *[data])
        self.zyre.emit(data['event'], *data['args'])


    # ZYRE Zactor
    def actor_fn(self, pipe, iface):

        # Internal
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.

        # ADD self in phone Book
        me = {
            'uuid':      None,
            'ip':        '127.0.0.1',
            'name':      'self',
            'ts_port':   self.timeserver.port,
            'pub_port':  self.pub_port
        }
        self.peerbook.newpeer(me)

        # Poller
        poller = Zpoller(self.zyre_sock, internal_pipe, self.pub_sock, None)

        # RUN
        print('ZYRE Node started')
        internal_pipe.signal(0)
        terminated = False
        while not terminated:
            sock = poller.wait(500)
            if not sock:
                continue

            #
            # ZYRE receive
            #
            if sock == self.zyre_sock:
                e = ZyreEvent(self.zyre_node)


                # ENTER: add to phonebook for external contact (i.e. TimeSync)
                if e.type() == b"ENTER":
                    newpeer = {
                        'uuid':      e.peer_uuid(),
                        'ip':        extract_ip( e.peer_addr() ),
                        'name':      e.peer_name().decode(),
                        'ts_port':   e.header(b"TS-PORT").decode(),
                        'pub_port':  e.header(b"PUB-PORT").decode()
                    }
                    self.peerbook.newpeer(newpeer)

                # EVASIVE
                elif e.type() == b"EVASIVE":
                    # self.zyre.log(e.peer_name(), "is evasive..")
                    # e.print()
                    pass

                # SILENT
                elif e.type() == b"SILENT":
                    self.zyre.log(e.peer_name(), "is silent..")

                # EXIT
                elif e.type() == b"EXIT":
                    self.peerbook.gone(e.peer_uuid())
                    self.zyre.log(e.peer_name(), "is gone..")

                # JOIN
                elif e.type() == b"JOIN":
                    print("ZYRE Node: peer join a group..", e.peer_name(), e.group().decode())

                    # SYNC clocks
                    if e.group() == b"sync":
                        self.peerbook.sync(e.peer_uuid())

                # LEAVE
                elif e.type() == b"LEAVE":
                    print("ZYRE Node: peer left a group..")

                # SHOUT -> process event
                elif e.type() == b"SHOUT" or e.type() == b"WHISPER":

                    # Parsing message
                    data = json.loads(e.msg().popstr().decode())
                    data['from'] = e.peer_uuid()

                    # add group
                    if e.type() == b"SHOUT": data['group'] = e.group().decode()
                    else: data['group'] = 'whisper'

                    self.preProcessor1(data)


            #
            # PUBLISHER event
            #
            elif sock == self.pub_sock:
                msg = Zmsg.recv(self.pub_sock)
                if not msg: break
                topic = msg.popstr()

                # Somebody subscribed: push Last Value Cache !
                if len(topic) > 0 and topic[0] == 1:
                    topic = topic[1:]
                    if topic in self.pub_cache:
                        # print('XPUB lvc send for', topic.decode())
                        msg = Zmsg.dup(self.pub_cache[topic])
                        Zmsg.send(msg, self.pub_sock)

                    else:
                        print('XPUB lvc empty for', topic.decode())


            #
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg: break

                if msg.popstr() == b"$TERM":
                    print('ZYRE Node TERM')
                    break
                    

        # self.zyre_node.stop()  # HANGS !
        internal_pipe.__del__()
        self.zyre_node.__del__()
        self.pub_sock.__del__()
        print('ZYRE Node stopped')   # WEIRD: print helps the closing going smoothly..
        self.done = True


#
#  HPLAYER2 Zyre interface
#
class ZyreInterface (BaseInterface):

    def  __init__(self, hplayer, iface=None):
        super().__init__(hplayer, "ZYRE")
        self.node = ZyreNode(self, iface)

        # Publish self status
        @self.hplayer.on('status')
        def s(*args):
            self.node.publish('peer-status', args[0])

        # Connect to peers
        @self.hplayer.on('*.peers-subscribe')
        def mon(*args):
            topic = args[0]
            self.node.peerbook.subscribeAll(topic)


    def listen(self):
        self.log( "interface ready")
        self.stopped.wait()
        self.node.stop()
        self.log( "closing sockets...") # CLOSING is messy !
        sleep(0.2)

    def activeCount(self):
        c = self.node.peerbook.activeCount()+1
        return c

    def peersList(self):
        return self.node.peerbook.phonebook

        