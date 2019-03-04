from .base import BaseInterface
from zyre import Zyre, ZyreEvent
from czmq import *
import time, random
from time import sleep

# current_milli_time = lambda: int(round(time.time() * 1000))
extract_ip = lambda x: str(x).split('//')[1].split(':')[0]

PRECISION = 1000000
SAMPLER_SIZE = 100


class TimeSample():
    def send(self, sock):
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


class TimePeer():
    def __init__(self, ip, uuid):
        self.ip = ip
        self.url = ("tcp://"+ip+":71443").encode()
        self.uuid = uuid
        self.status = 2
        self.clockshift = 0
        self.start()

    def start(self):
        if self.status > 2:
            return
        self.status = 3
        self._request_actor = zactor_fn(self.request_actor) # ctypes function reference must live as long as the actor.
        self.actor = Zactor(self._request_actor, create_string_buffer(b"Sync request"))


    # REQUEST Sync Zactor
    def request_actor(self, pipe, args):
        self.status = 4
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        req_sock = Zsock.new_req(self.url)
        poller = Zpoller(internal_pipe, req_sock)
        internal_pipe.signal(0)

        sampler = []
        print("starting requester at", self.url.decode())

        sample = TimeSample()
        sample.send(req_sock)

        terminated = False
        retry = 0
        while not terminated and retry < 10:
            sock = poller.wait(500)

            #
            # REQ received
            #
            if sock == req_sock:
                retry = 0
                sample.recv()
                sampler.append( sample )
                # print("Pong", sample.RTT, sample.CS)
                if len(sampler) >= SAMPLER_SIZE:
                    break
                sample = TimeSample()
                sample.send(req_sock)

            #
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg:
                    break # Interrupted

                command = msg.popstr()
                if command == b"$TERM":
                    terminated = True

            #
            # NOBODY responded ...
            #
            elif not sock:
                sample = TimeSample()
                sample.send(req_sock)
                retry += 1

        print("sampling done")
        #
        #  COMPUTE average Clock Shift
        #
        if len(sampler) >= SAMPLER_SIZE:
            RTTs = sorted(sampler, key=lambda x: x.RTT)
            RTTs = RTTs[2 : int(len(RTTs) * .7)]
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

            print(self.ip, "clock shift", str(cs)+"ns", "using", cs_count, "samples")
            self.clockshift = cs
            self.status = 1
        else:
            self.status = 0
            print("ERROR: sampler not full.. something might be broken")




class ZyreInterface (BaseInterface):

    def  __init__(self, player):
        super().__init__(player, "ZYRE")

        self.sync_peers = {}
        self.phonebook = {}

        self._zyre_actor = zactor_fn(self.zyre_actor) # ctypes function reference must live as long as the actor.
        self.node = Zactor(self._zyre_actor, create_string_buffer(b"Zyre node"))

        self._reply_actor = zactor_fn(self.reply_actor) # ctypes function reference must live as long as the actor.
        self.replier = Zactor(self._reply_actor, create_string_buffer(b"Sync reply"))

    def listen(self):
        self.log( "P2P node ready")
        self.stopped.wait()
        self.node.sock().send(b"s", b"$TERM")
        self.replier.sock().send(b"s", b"$TERM")
        sleep(0.5)

    def sync(self, uuid):
        ip = self.phonebook[uuid]
        if not ip in self.sync_peers:
            self.sync_peers[ip] = TimePeer(ip, uuid)


    def shout(self, group, path, args=None):
        data = path
        if args:
            if not isinstance(args, list):
                args = [args]
            for a in args:
                data += " " + a
        self.node.sock().send(b"sss", b"SHOUT", group.encode(), data.encode())

    def broadcast(self, path, args=None):
        self.shout('broadcast', path, args)

    def join(self, group):
        self.node.sock().send(b"ss", b"JOIN", group.encode())

    def leave(self, group):
        self.node.sock().send(b"ss", b"LEAVE", group.encode())

    # REPLY Sync Zactor
    def reply_actor(self, pipe, args):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        reply_sock = Zsock.new_rep(("tcp://*:71443").encode())
        if not reply_sock:
            print('ERROR while opening port 71443')

        poller = Zpoller(internal_pipe, reply_sock)
        internal_pipe.signal(0)

        self.log('REP started')
        terminated = False
        while not terminated:
            sock = poller.wait(1000)
            if not sock:
                # self.log('no thing to reply')
                continue
            #
            # REQ received
            #
            if sock == reply_sock:
                msgin = Zmsg.recv(reply_sock)
                # sleep(0.001+random.randint(1,9)/1000)
                msg = Zmsg()
                msg.addstr(str(int(time.time()*PRECISION)).encode())
                Zmsg.send( msg, reply_sock )
                # self.log("Go")

            #
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg:
                    break # Interrupted

                command = msg.popstr()
                if command == b"$TERM":
                    terminated = True

        self.log('REP stopped')



    # ZYRE Zactor
    def zyre_actor(self, pipe, arg):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        arg = string_at(arg)

        zyre_node = Zyre(None)
        zyre_node.start()
        zyre_node.join(b"broadcast")
        zyre_node.join(b"sync")
        zyre_pipe = zyre_node.socket()

        poller = Zpoller(zyre_pipe, internal_pipe)

        internal_pipe.signal(0)

        self.log('NODE started')
        terminated = False
        while not terminated:
            sock = poller.wait(1000)
            if not sock:
                # self.log("no thing")
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

                # ENTER
                if e.type() == b"ENTER":
                    self.log( "new peer detected")
                    self.phonebook[e.peer_uuid()] = extract_ip( e.peer_addr() )

                # ENTER
                elif e.type() == b"EXIT":
                    self.log( "peer is gone..")

                # JOIN
                elif e.type() == b"JOIN":

                    # SYNC clocks
                    if e.group() == b"sync":
                        pass
                        # self.sync(e.peer_uuid())

                # LEAVE
                elif e.type() == b"LEAVE":
                    self.log( "peer left a group..")

                # SHOUT -> process event
                elif e.type() == b"SHOUT":
                    # e.print()
                    group = e.group().decode('utf-8')
                    data = e.msg().popstr().decode('utf-8').split(' ')
                    self.processor(group, data[0], data[1:])



            #
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg:
                    break # Interrupted

                command = msg.popstr()
                if command == b"$TERM":
                    terminated = True

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
                    print(zyre_node.own_groups())
                    # TODO: send to self if concerned

        zyre_node.stop()
        self.log('NODE stopped')


    def processor(self, group, path, args):

        if not self.player:
            return

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
