from zyre import Zyre, ZyreEvent
from czmq import *
import time, random
from time import sleep
import json
from threading import Timer

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
SAMPLER_SIZE = 1000
KEEP_SAMPLE = 0.3


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
            RTTs = RTTs[2 : int(len(RTTs) * KEEP_SAMPLE)]
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
        poller = Zpoller(internal_pipe, req_sock)
        internal_pipe.signal(0)
        retry = 0

        print("TimeClient: Starts sampling", self.peer['ip'])

        sampler = []
        sample = TimeSample(req_sock)

        terminated = False
        while not terminated and retry < 10:
            # sock = poller.wait(500)
            #
            # # NOBODY responded ...
            # if not sock:
            #     sample = TimeSample(req_sock)
            #     retry += 1
            #
            # # REP received
            # elif sock == req_sock:

            retry = 0
            sample.recv()
            sampler.append( sample )
            # print("Pong", sample.RTT, sample.CS)
            if len(sampler) >= SAMPLER_SIZE:
                break
            sample = TimeSample(req_sock)

            # # INTERNAL commands
            # elif sock == internal_pipe:
            #     msg = Zmsg.recv(internal_pipe)
            #     if not msg or msg.popstr() == b"$TERM":
            #         return

        print("TimeClient: Sampling done", self.peer['ip'])
        self.compute(sampler)
        self.done = True

#
#  BOOK to perform and record sync with others
#
class TimeBook():
    def  __init__(self):
        self.peers = {}
        self.phonebook = {}

    def stop(self):
        for peer in self.peers.values():
            peer.stop()

    def newpeer(self, uuid, addr, port):
        self.phonebook[uuid] = {}
        self.phonebook[uuid]['uuid'] = uuid
        self.phonebook[uuid]['ip'] = extract_ip(addr)
        self.phonebook[uuid]['port'] = port.decode()
        print("New Peer detected", self.phonebook[uuid])

    def sync(self, uuid):
        if uuid in self.phonebook:
            ip = self.phonebook[uuid]['ip']
            if not ip in self.peers:
                self.peers[ip] = TimeClient(self.phonebook[uuid])

    def cs(self, uuid):
        if uuid in self.phonebook:
            ip = self.phonebook[uuid]['ip']
            if ip in self.peers:
                return self.peers[ip].clockshift
        return 0



#
#  NODE zyre peers discovery, sync and communication
#
class ZyreNode ():
    def  __init__(self, processor=None):
        self.processor = processor

        self.timebook = TimeBook()

        self._actor_fn = zactor_fn(self.actor_fn) # ctypes function reference must live as long as the actor.
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Zyre node"))
        self.done = False

    def stop(self):
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

    def eventProc(self, data):

        # if a programmed time is provided, correct it with peer CS
        # Set timer
        if 'at' in data:
            data['at'] -= self.timebook.cs( data['from'] )
            delay =  data['at'] / PRECISION - time.time()
            print('programmed event in', delay, 'seconds')
            t = Timer( delay, self.processor, args=[data])
            t.start()

        elif self.processor:
            self.processor(data)




    # ZYRE Zactor
    def actor_fn(self, pipe, arg):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        arg = string_at(arg)

        global port

        zyre_node = Zyre(None)
        zyre_node.set_header (b"TS-PORT", str(port).encode());
        zyre_node.start()
        zyre_node.join(b"broadcast")
        zyre_node.join(b"sync")
        zyre_pipe = zyre_node.socket()

        poller = Zpoller(zyre_pipe, internal_pipe)

        internal_pipe.signal(0)

        print('ZYRE Node started')
        terminated = False
        while not terminated:
            # time.sleep(1)
            # sock = poller.wait(1000)
            # if not sock:
            #     continue
            #
            #
            # ZYRE receive
            #
            # if sock == zyre_pipe:
                e = ZyreEvent(zyre_node)

                # ANY
                if e.type() != b"EVASIVE":
                    e.print()
                    pass

                # ENTER: add to phonebook for external contact (i.e. TimeSync)
                if e.type() == b"ENTER":
                    self.timebook.newpeer(e.peer_uuid(), e.peer_addr(), e.header(b"TS-PORT"))

                # EXIT
                elif e.type() == b"EXIT":
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

                    self.eventProc(data)
            #
            #
            # #
            # # INTERNAL commands
            # #
            # elif sock == internal_pipe:
            #     msg = Zmsg.recv(internal_pipe)
            #     if not msg: break
            #
            #     command = msg.popstr()
            #     if command == b"$TERM":
            #         print('ZYRE Node TERM')
            #         break
            #
            #     elif command == b"JOIN":
            #         group = msg.popstr()
            #         zyre_node.join(group)
            #
            #     elif command == b"LEAVE":
            #         group = msg.popstr()
            #         zyre_node.leave(group)
            #
            #     elif command == b"SHOUT":
            #         group = msg.popstr()
            #         data = msg.popstr()
            #         zyre_node.shouts(group, data)
            #
            #         # if own group -> send to self too !
            #         groups = zlist_strlist( zyre_node.own_groups() )
            #         if group.decode() in groups:
            #             data = json.loads(data.decode())
            #             data['from'] = 'self'
            #             data['group'] = group.decode()
            #             self.eventProc(data)


        # zyre_node.stop()  # HANGS !
        internal_pipe.__del__()
        zyre_node.__del__()
        print('ZYRE Node stopped')   # WEIRD: print helps the closing going smoothly..
        self.done = True




# TIME SERVER

# REPLY Sync Zactor
def ts_fn(pipe, args):
    internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
    reply_sock = Zsock.new_rep(("tcp://*:*").encode())
    if not reply_sock:
        print('ERROR while binding TimeBook REP socket')
    else:
        port = reply_sock.endpoint().decode().split(':')[2]

    #poller = Zpoller(internal_pipe, reply_sock)
    poller = Zpoller(internal_pipe)
    poller.add(reply_sock)
    internal_pipe.signal(0)

    while True:
        sock = poller.wait(10000)
        if not sock: continue

        # REQ received
        if sock == reply_sock:
            msgin = Zmsg.recv(reply_sock)
            msg = Zmsg()
            msg.addstr(str(int(time.time()*PRECISION)).encode())
            Zmsg.send( msg, reply_sock )

        # INTERNAL commands
        elif sock == internal_pipe:
            msg = Zmsg.recv(internal_pipe)
            if not msg or msg.popstr() == b"$TERM":
                break



port = 0
_ts_fn = zactor_fn(ts_fn) # ctypes function reference must live as long as the actor.
ts_actor = Zactor(_ts_fn, create_string_buffer(b"Sync reply"))


# ZYRE

# def proc(data):
#     print('PROC', data)
#
# node = ZyreNode(proc)

while True:
    try:
        sleep(1)
    except KeyboardInterrupt:
        break

# node.stop()
# sleep(1)
# print("Bye!")
