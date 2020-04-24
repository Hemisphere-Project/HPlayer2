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


PING_PEER = 1000

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
#  SUBSCRIBER to others publishing
#
class Subscriber():
    def __init__(self, node, ip, port, topic):
        self.node = node
        self.cache = {}

        self.sub = Zsock.new_sub(("tcp://"+ip+":"+port).encode(), topic.encode())

        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        self.done = True
        self.start()

        # self.node.interface.log("Subscribing to", ip)

    def start(self):
        if not self.done: 
            self.stop()
        
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Subscriber"))
        self.done = False
        
    def stop(self):
        if not self.done:
            self.actor.sock().send(b"s", b"$TERM")
        self.sub.__del__()
        self.done = True

    def subscribe(self, topic):
        Zsock.set_unsubscribe(self.sub, topic.encode())
        Zsock.set_subscribe(self.sub, topic.encode())

    # SUB Zactor
    def actor_fn(self, pipe, args):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        poller = Zpoller(internal_pipe, self.sub, None)
        internal_pipe.signal(0)
        terminated = False
        while not terminated:
            sock = poller.wait(500)

            # NOBODY responded ...
            if not sock:
                continue

            # INTERNAL commands
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg or msg.popstr() == b"$TERM":
                    break

            # SUB received
            elif sock == self.sub:
                msg = Zmsg.recv(self.sub)
                topic = msg.popstr().decode()
                uuid = msg.popstr()
                peer = self.node.peer(uuid)
                name = peer.name if peer else uuid.decode()
                data = json.loads(msg.popstr().decode())
                arg = {'name': name, 'data': data, 'at': int(time.time()*PRECISION)}
                self.cache[topic] = arg
                self.node.interface.emit(topic, arg)


        internal_pipe.__del__()
        self.done = True


#
#   PEER
#
class Peer():
    def __init__(self, node, conf):
        self.node = node

        if isinstance(conf, ZyreEvent):
            conf = {
                'uuid':         conf.peer_uuid(),
                'ip':           extract_ip( conf.peer_addr() ),
                'name':         conf.peer_name().decode(),
                'ts_port':      conf.header(b"TS-PORT").decode(),
                'pub_port':     conf.header(b"PUB-PORT").decode(),
            }
        for key in conf:
            setattr(self, key, conf[key])

        self.link = 0   # 0: GONE / 1: SILENT / 2: EVASIVE / 3: OK
        self.timerLink = None
        self.linker(3)

        self.timeclient = None
        self.subscribers = None

    def stop(self):
        if self.timerLink:
            self.timerLink.cancel()
        if self.timeclient: 
            self.timeclient.stop()
        if self.subscribers: 
            self.subscribers.stop()

    def linker(self, l):
        if self.timerLink:
            self.timerLink.cancel()
        
        if l != self.link:
            self.link = l
            self.node.interface.emit('peer.link', {'name': self.name, 'data': self.link})
        
        if self.link < 3:
            self.timerLink = Timer(PING_PEER*1.5/1000.0, self.linker, args=[l+1])
            self.timerLink.start()

    def sync(self):
        self.timeclient = TimeClient(self.ip, self.ts_port)

    def clockshift(self):
        shift = 0
        if self.timeclient:
            return self.timeclient.clockshift
        return 0

    def subscribe(self, topics):
        if not isinstance(topics, list): topics = [topics]
        for t in topics:
            top = 'peer.'+t
            if not self.subscribers:
                self.subscribers = Subscriber(self.node, self.ip, self.pub_port, top)
            else:
                self.subscribers.subscribe(top)
    



#
#  NODE zyre peers discovery, sync and communication
#
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
        self.zyre.set_silent_timeout(PING_PEER*6)
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

        # Start Poller
        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        if netiface:
            netiface = create_string_buffer(str.encode(netiface))
        self.actor = Zactor(self._actor_fn, netiface)
        self.done = False


    # ZYRE Zactor
    def actor_fn(self, pipe, netiface):

        # Internal
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.

        # Poller
        poller = Zpoller(self.zyre.socket(), internal_pipe, self.publisher, self.timereply, None)

        # RUN
        self.interface.log('Node started')
        internal_pipe.signal(0)
        terminated = False
        while not terminated:
            sock = poller.wait(500)
            if not sock:
                continue

            #
            # ZYRE receive
            #
            if sock == self.zyre.socket():
                e = ZyreEvent(self.zyre)
                uuid = e.peer_uuid()

                # ENTER: add to book for external contact (i.e. TimeSync)
                if e.type() == b"ENTER":
                    if uuid in self.book:
                        # print ('Already exist: replacing')  ## PROBLEM : Same name may appear with different uuid (not a real problem, only if crash and restart with new uuid in a short time..)
                        self.book[uuid].stop()
                        del self.book[uuid]

                    newpeer = Peer(self, e) 
                    self.book[uuid] = newpeer
                    self.book[uuid].subscribe(self.topics)

                # EVASIVE
                elif e.type() == b"EVASIVE":
                    # if uuid in self.book:
                    #     self.book[uuid].linker(2)
                    pass

                # SILENT
                elif e.type() == b"SILENT":
                    if uuid in self.book:
                        self.book[uuid].linker(1)

                # EXIT
                elif e.type() == b"EXIT":
                    if uuid in self.book:
                        self.book[uuid].linker(0)
                        self.book[uuid].stop()
                        del self.book[uuid]

                # JOIN
                elif e.type() == b"JOIN":
                    # self.interface.log("peer join a group..", e.peer_name(), e.group().decode())

                    # SYNC clocks
                    if e.group() == b"sync":
                        if self.peer(uuid): 
                            self.peer(uuid).sync()

                # LEAVE
                elif e.type() == b"LEAVE":
                    # self.interface.log("peer left a group..")
                    pass

                # SHOUT -> process event
                elif e.type() == b"SHOUT" or e.type() == b"WHISPER":

                    # Parsing message
                    data = json.loads(e.msg().popstr().decode())
                    data['from'] = uuid

                    # add group
                    if e.type() == b"SHOUT": data['group'] = e.group().decode()
                    else: data['group'] = 'whisper'

                    self.preProcessor1(data)


            #
            # PUBLISHER event
            #
            elif sock == self.publisher:
                msg = Zmsg.recv(self.publisher)
                if not msg: break
                topic = msg.popstr()

                # Somebody subscribed: push Last Value Cache !
                if len(topic) > 0 and topic[0] == 1:
                    topic = topic[1:]
                    if topic in self.pub_cache:
                        # self.interface.log('XPUB lvc send for', topic.decode())
                        msg = Zmsg.dup(self.pub_cache[topic])
                        Zmsg.send(msg, self.publisher)

                    # else:
                    #     self.interface.log('XPUB lvc empty for', topic.decode())

            #
            # TIMESERVER event
            #
            elif sock == self.timereply:
                msgin = Zmsg.recv(self.timereply)
                msg = Zmsg()
                msg.addstr(str(int(time.time()*PRECISION)).encode())
                Zmsg.send( msg, self.timereply )

            #
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg: break

                if msg.popstr() == b"$TERM":
                    print('ZYRE Node TERM')
                    break
                    

        # self.zyre.stop()  # HANGS !
        internal_pipe.__del__()
        self.interface.log('Node stopped')   # WEIRD: print helps the closing going smoothly..
        self.done = True

    def stop(self):
        for peer in self.book.values():
            peer.stop()
        if not self.done:
            self.actor.sock().send(b"ss", b"$TERM", "gone")
        self.zyre.__del__()
        self.publisher.__del__()
        self.timereply.__del__()

    def peer(self, uuid):
        if uuid in self.book:
            return self.book[uuid]

    def peerByName(self, name):
        for peer in self.book.values():
            if peer.name == name:
                return peer

    #
    # PUB/SUB
    #

    def subscribe(self, topics):
        if not isinstance(topics, list): topics = [topics]
        self.topics = list(set(self.topics) | set(topics))    # merge lists and remove duplicates
        for peer in self.book.values():
            peer.subscribe(self.topics)

    def publish(self, topic, args=None):
        topic = topic.encode()
        
        msg = Zmsg()
        msg.addstr(topic)
        msg.addstr(self.zyre.uuid())
        msg.addstr(json.dumps(args).encode())

        self.pub_cache[topic] = Zmsg.dup(msg)
        Zmsg.send(msg, self.publisher)

    #
    # ZYRE send messages
    #

    def makeMsg(self, event, args=None, delay_ms=0):
        data = {}
        data['event'] = event
        data['args'] = []
        if args:
            if not isinstance(args, list):
                # self.interface.log('NOT al LIST', args)
                args = [args]
            data['args'] = args

        # add delay
        if delay_ms > 0:
            data['at'] = int(time.time()*PRECISION + delay_ms * PRECISION / 1000)

        return json.dumps(data).encode()

    def whisper(self, uuid, event, args=None, delay_ms=0):
        data = self.makeMsg(event, args, delay_ms)
        if uuid == self.zyre.uuid():
            data = json.loads(data.decode())
            data['from'] = 'self'
            data['group'] = 'whisper'
            self.preProcessor1(data)
        else:
            self.zyre.whispers(uuid, data)

    def shout(self, group, event, args=None, delay_ms=0):
        data = self.makeMsg(event, args, delay_ms)
        self.zyre.shouts(group.encode(), data)

        # if own group -> send to self too !
        groups = zlist_strlist( self.zyre.own_groups() )
        if group in groups:
            data = json.loads(data.decode())
            data['from'] = 'self'
            data['group'] = group
            self.preProcessor1(data)

    def broadcast(self, event, args=None, delay_ms=0):
        self.shout('broadcast', event, args, delay_ms)

    def join(self, group):
        self.zyre.join(group.encode())

    def leave(self, group):
        self.zyre.leave(group.encode())

    #
    # ZYRE messages processor
    #

    def preProcessor1(self, data):
        # if a programmed time is provided, correct it with peer CS
        # Set timer
        if 'at' in data:
            if self.peer(data['from']):
                data['at'] -= self.peer(data['from']).clockshift()
            delay =  (data['at']) / PRECISION - time.time()

            if delay <= 0:
                self.preProcessor2(data)
            else:
                self.interface.log('programmed event in', delay, 'seconds')
                t = Timer( delay, self.preProcessor2, args=[data])
                t.start()
                self.interface.emit('planned', data)

        else:
            self.preProcessor2(data)

    def preProcessor2(self, data):
        self.interface.emit('event', *[data])
        self.interface.emit(data['event'], *data['args'])



#
#  HPLAYER2 Zyre interface
#
class ZyreInterface (BaseInterface):

    def  __init__(self, hplayer, netiface=None):
        super().__init__(hplayer, "ZYRE")
        self.node = ZyreNode(self, netiface)

        # Publish self status
        @self.hplayer.on('player.playing')
        @self.hplayer.on('player.paused')
        @self.hplayer.on('player.end')
        def st(*args):
            self.node.publish('peer.status', self.hplayer.status())

        # Publish self settings
        @self.hplayer.on('settings.updated')
        def se(ev, settings):
            self.node.publish('peer.settings', settings)

        # Subscribe to peers
        @self.hplayer.on('*.peers.subscribe')
        def mon(ev, topics):
            self.node.subscribe(topics)

        # Trig peers link status
        @self.hplayer.on('*.peers.getlink')
        def links(ev):
            for peer in self.node.book.values():
                self.emit('peer.link', {'name': peer.name, 'data': peer.link})

        # Triggers event on peers
        @self.hplayer.on('*.peers.triggers')
        def trig(ev, *args):
            delay = args[1] if len(args) > 1 else 0
            for ev in args[0]:
                data = None
                if 'data' in ev: 
                    data = ev['data']
                if 'peer' in ev:
                    peer = self.node.peerByName(ev['peer'])
                    self.node.whisper( peer.uuid, ev['event'], data, delay)
                else:
                    self.node.broadcast(ev['event'], data, delay)

    def listen(self):
        self.log( "interface ready")
        self.stopped.wait()
        self.node.stop()
        self.log( "closing sockets...") # CLOSING is messy !
        sleep(0.2)

    def activeCount(self):
        return len(self.node.book)

    def peersList(self):
        return self.node.book

        