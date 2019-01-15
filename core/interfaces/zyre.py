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
extract_ip = lambda x: str(x).split('//')[1].split(':')[0]

def zlist_strlist(zlist):
    list = []
    el = zlist.pop()
    while el:
        list.append(string_at(el).decode())
        el = zlist.pop()
    return list


PRECISION = 1000000
SAMPLER_SIZE = 500
KEEP_SAMPLE = [0.05, 0.5]


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
    def __init__(self, peer):
        self.peer = peer
        self.url = ("tcp://"+peer['ip']+":"+peer['port']).encode()
        self.clockshift = 0

        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Sync request"))
        self.done = False

    def stop(self):
        if not self.done:
            self.actor.sock().send(b"s", b"$TERM")


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

            print(self.peer['ip'], "clock shift", str(cs)+"ns", "using", len(sampler), "samples")
            self.clockshift = cs
            self.status = 1
        else:
            self.status = 0
            print("ERROR: sampler not full.. something might be broken")

    # CLIENT TimeSync REQ Zactor
    def actor_fn(self, pipe, args):
        self.status = 4
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        req_sock = Zsock.new_req(self.url)
        poller = Zpoller(internal_pipe, req_sock, None)
        internal_pipe.signal(0)
        retry = 0

        # print("TimeClient: Starts sampling", self.peer['ip'])

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

        # print("TimeClient: Sampling done", self.peer['ip'])
        self.compute(sampler)
        self.done = True

#
#  BOOK to perform and record sync with others
#
class TimeBook():
    def  __init__(self):
        self.peers = {}
        self.phonebook = {}
        self.activePeers = 0
        self._lock = Lock()

    def stop(self):
        with self._lock:
            for peer in self.peers.values():
                peer.stop()

    def newpeer(self, uuid, addr, port):
        self.gone(uuid)
        with self._lock:
            self.phonebook[uuid] = {}
            self.phonebook[uuid]['uuid'] = uuid
            self.phonebook[uuid]['ip'] = extract_ip(addr)
            self.phonebook[uuid]['port'] = port.decode()
            self.phonebook[uuid]['active'] = True
            self.activePeers += 1
            print("New Peer detected", self.phonebook[uuid])

    def sync(self, uuid):
        with self._lock:
            if uuid in self.phonebook:
                ip = self.phonebook[uuid]['ip']
                # if not ip in self.peers:
                self.peers[ip] = TimeClient(self.phonebook[uuid])

    def gone(self, uuid):
        with self._lock:
            if uuid in self.phonebook and self.phonebook[uuid]['active']:
                self.phonebook[uuid]['active'] = False
                self.activePeers -= 1

    def activeCount(self):
        c = 0
        with self._lock:
            c = self.activePeers
        return c

    def cs(self, uuid):
        shift = 0
        with self._lock:
            if uuid in self.phonebook:
                ip = self.phonebook[uuid]['ip']
                if ip in self.peers:
                    shift = self.peers[ip].clockshift
        return shift



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
            print('ERROR while binding TimeBook REP socket')
        else:
            self.port = reply_sock.endpoint().decode().split(':')[2]

        poller = Zpoller(internal_pipe, reply_sock, None)
        internal_pipe.signal(0)

        print('TimeServer started on port', self.port)
        terminated = False
        while not terminated:
            sock = poller.wait(1000)
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
        self.done = True



#
#  NODE zyre peers discovery, sync and communication
#
class ZyreNode ():
    def  __init__(self, processor=None, iface=None):
        self.processor = processor

        self.timebook = TimeBook()
        self.timeserver = TimeServer()

        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.

        if iface:
            iface = create_string_buffer(str.encode(iface))
        self.actor = Zactor(self._actor_fn, iface)
        self.done = False

        self.deltadelay = 0

    def stop(self):
        self.timeserver.stop()
        self.timebook.stop()
        if not self.done:
            self.actor.sock().send(b"ss", b"$TERM", "gone")
            # print('ZYRE term sent')

    def shout(self, group, event, args=None, delay_ms=0):
        data = {}
        data['event'] = event
        data['args'] = []
        if args:
            if not isinstance(args, list):
                print('NOT al LIST', args)
                args = [args]
            data['args'] = args

        # add delay
        if delay_ms > 0:
            data['at'] = int(time.time()*PRECISION + delay_ms * PRECISION / 1000)

        data = json.dumps(data)
        self.actor.sock().send(b"sss", b"SHOUT", group.encode(), data.encode())

    def broadcast(self, event, args=None, delay_ms=0):
        self.shout('broadcast', event, args, delay_ms)

    def join(self, group):
        self.actor.sock().send(b"ss", b"JOIN", group.encode())

    def leave(self, group):
        self.actor.sock().send(b"ss", b"LEAVE", group.encode())

    def preProcessor1(self, data):

        # if a programmed time is provided, correct it with peer CS
        # Set timer
        if 'at' in data:
            data['at'] -= self.timebook.cs( data['from'] )
            #delay =  (data['at']-self.deltadelay) / PRECISION - time.time()
            delay =  (data['at']) / PRECISION - time.time()


            if delay <= 0:
                self.preProcessor2(data)
            else:
                print('programmed event in', delay, 'seconds')
                t = Timer( delay, self.preProcessor2, args=[data])
                t.start()

        elif self.processor:
            self.preProcessor2(data)

    def preProcessor2(self, data):
        if 'at' in data:
            self.deltadelay += (int(time.time()*PRECISION)-data['at'])  # Might get crazy..

        self.processor(data)



    # ZYRE Zactor
    def actor_fn(self, pipe, iface):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.

        zyre_node = Zyre(None)
        if iface:
            zyre_node.set_interface( string_at(iface) )
            print("ZYRE Node forced iface: ", string_at(iface) )
        zyre_node.set_header (b"TS-PORT", str(self.timeserver.port).encode());
        zyre_node.start()
        zyre_node.join(b"broadcast")
        zyre_node.join(b"sync")
        zyre_pipe = zyre_node.socket()

        poller = Zpoller(zyre_pipe, internal_pipe, None)

        internal_pipe.signal(0)

        print('ZYRE Node started')
        terminated = False
        while not terminated:
            sock = poller.wait(1000)
            if not sock:
                continue

            #
            # ZYRE receive
            #
            if sock == zyre_pipe:
                e = ZyreEvent(zyre_node)

                # ANY
                if e.type() != b"EVASIVE":
                    # e.print()
                    pass

                # ENTER: add to phonebook for external contact (i.e. TimeSync)
                if e.type() == b"ENTER":
                    self.timebook.newpeer(e.peer_uuid(), e.peer_addr(), e.header(b"TS-PORT"))

                # EXIT
                elif e.type() == b"EXIT":
                    self.timebook.gone(e.peer_uuid())
                    print( "ZYRE Node: peer is gone..")

                # JOIN
                elif e.type() == b"JOIN":

                    # SYNC clocks
                    if e.group() == b"sync":
                        pass
                        self.timebook.sync(e.peer_uuid())

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
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg: break

                command = msg.popstr()
                if command == b"$TERM":
                    print('ZYRE Node TERM')
                    break

                elif command == b"JOIN":
                    group = msg.popstr()
                    zyre_node.join(group)

                elif command == b"LEAVE":
                    group = msg.popstr()
                    zyre_node.leave(group)

                elif command == b"SHOUT":
                    group = msg.popstr()
                    data = msg.popstr()
                    zyre_node.shouts(group, data)

                    # if own group -> send to self too !
                    groups = zlist_strlist( zyre_node.own_groups() )
                    if group.decode() in groups:
                        data = json.loads(data.decode())
                        data['from'] = 'self'
                        data['group'] = group.decode()
                        self.preProcessor1(data)


        # zyre_node.stop()  # HANGS !
        internal_pipe.__del__()
        zyre_node.__del__()
        print('ZYRE Node stopped')   # WEIRD: print helps the closing going smoothly..
        self.done = True


#
#  HPLAYER2 Zyre interface
#
class ZyreInterface (BaseInterface):

    def  __init__(self, player, iface=None):
        super().__init__(player, "ZYRE")
        self.node = ZyreNode(self.processor, iface)

    def listen(self):
        self.log( "interface ready")
        self.stopped.wait()
        self.node.stop()
        self.log( "closing sockets...") # CLOSING is messy !
        sleep(1)

    def activeCount(self):
        c = self.node.timebook.activeCount()+1
        return c

    def processor(self, data):

        self.log('Received: ', data)

        if 'at' in data:
            # self.log('DELTA', int(time.time()*PRECISION)-data['at'], 'ns' )
            pass

        if not self.player:
            return

        path = data['event']
        args = data['args']

        if path == '/play':
            self.player.loop(0)
            if args and len(args) >= 1:
                self.player.play(args[0])
            else:
                self.player.play()

        elif path == '/playloop':
            self.player.loop(1)
            if args and len(args) >= 1:
                self.player.play(args[0])
            else:
                self.player.play()

        elif path == '/playindex':
            if args and len(args) >= 1:
                self.player.play(args[0])

        elif path == '/playlist':
            if args and len(args) >= 1:
                self.player.load(args[0])
                if len(args) >= 2: self.player.play(args[1])
                else: self.player.play()
                # self.log('DELTA PLAY', int(time.time()*PRECISION)-data['at'], 'ns' )

        elif path == '/load':
            if args and len(args) >= 1:
                self.player.load(args[0])

        elif path == '/stop':
            self.player.stop()

        elif path == '/pause':
            self.player.pause()

        elif path == '/resume':
            self.player.resume()

        elif path == '/next':
            self.player.next()

        elif path == '/prev':
            self.player.prev()

        elif path == '/loop':
            self.player.loop(1)

        elif path == '/unloop':
            self.player.loop(0)

        elif path == '/volume':
            if args and len(args) >= 1:
                self.player.volume(args[0])

        elif path == '/mute':
            self.player.mute(True)

        elif path == '/unmute':
            self.player.mute(False)

        elif path == '/pan':
            if args and len(args) >= 2:
                self.player.pan(args[0], args[1])

        elif path == '/flip':
            self.player.flip(True)

        elif path == '/unflip':
            self.player.flip(False)

        else:
            self.player.trigger(path, args)
