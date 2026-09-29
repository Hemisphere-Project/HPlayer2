from .base import BaseInterface
from ..module import safe_print
from ..engine import network
import importlib
import time
import random
from time import sleep
import json
from threading import Timer, Lock, Thread
import queue
import sys

from ctypes import string_at, create_string_buffer
from sys import getsizeof
from binascii import hexlify

Zyre = None
ZyreEvent = None
Zsock = None
Zmsg = None
Zpoller = None
Zactor = None
zactor_fn = None

_ZYRE_IMPORT_ERROR = None
_CZMQ_IMPORT_ERROR = None

try:
    _zyre_module = importlib.import_module("zyre")
    Zyre = getattr(_zyre_module, "Zyre", None)
    ZyreEvent = getattr(_zyre_module, "ZyreEvent", None)
except ImportError as err:
    _ZYRE_IMPORT_ERROR = err

try:
    _czmq_module = importlib.import_module("czmq")
    Zsock = getattr(_czmq_module, "Zsock", None)
    Zmsg = getattr(_czmq_module, "Zmsg", None)
    Zpoller = getattr(_czmq_module, "Zpoller", None)
    Zactor = getattr(_czmq_module, "Zactor", None)
    zactor_fn = getattr(_czmq_module, "zactor_fn", None)
except ImportError as err:
    _CZMQ_IMPORT_ERROR = err

# current_milli_time = lambda: int(round(time.time() * 1000))

def get_port(sock):
    if not sock: 
        safe_print('ERROR while binding socket')
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

#
#  REAPER: tear peers down off the zyre actor thread
#
#  Peer.stop() waits up to 1 s for its TimeClient and 1 s for its Subscriber. Called from the
#  node's actor on ENTER/EXIT, that froze the one thread that also answers every slave's clock
#  samples and zyre's own heartbeats: during a link-flap storm (Kouagou01-64, 2026-09-25 05:49,
#  hundreds of ENTER/EXIT a minute for kouagou03) each teardown made the next flap likelier and
#  starved every slave's clock sync. One long-lived worker, a queue, never a thread per peer.
_reapQ = queue.Queue()
_reaper = [None]

def _reapLoop():
    while True:
        peer = _reapQ.get()
        try:
            peer.stop()
        except Exception as e:
            safe_print('peer teardown error (ignored):', e)

def reap(peer):
    peer.active = False             # out of every lookup right now, torn down in the background
    if _reaper[0] is None or not _reaper[0].is_alive():
        t = Thread(target=_reapLoop, name='zyre-reaper', daemon=True)
        try:
            t.start()
            _reaper[0] = t
        except RuntimeError:
            peer.stop()             # no thread to spare: tear down inline, as before
            return
    _reapQ.put(peer)

PRECISION = 1000000
SAMPLER_SIZE = 100
KEEP_SAMPLE = [0.001, 0.3]

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
        self.status = 0
        self._refresh = None
        self._terminated = False
        self._actor_fn = zactor_fn(self.actor_fn_guarded) # ctypes function reference must live as long as the actor.
        self.done = True
        self.failures = 0           # failed rounds in a row
        self.start()

    def actor_fn_guarded(self, pipe, args):
        try:
            self.actor_fn(pipe, args)
        except Exception as e:
            safe_print("\t", "["+self.client_ip+"]", "clock round error:", e)
            self.done = True
            if not self._terminated:
                self._arm(10)

    def start(self):
        if not self.done: 
            self.stop()
        
        self._terminated = False
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Sync request"))
        self.done = False
        self._arm(120)

    def _arm(self, delay):
        # Schedule the next round. A Timer that cannot start (`can't start new thread`) used to
        # raise out of here — from __init__ (Peer.sync) that left the peer with no TimeClient
        # while the actor just launched sampled for nobody: kouagou03 freewheeled ~60 h that way
        # (2026-09-21 23:28, a link-loss rebuild storm). Never raise: an unarmed client reports
        # stalled() and wallclock re-arms it.
        if self._refresh:
            self._refresh.cancel()
        self._refresh = None
        t = Timer(delay, self.start)
        try:
            t.start()
            self._refresh = t
        except RuntimeError as e:
            safe_print("\t", "["+self.client_ip+"]", "refresh timer unavailable (" + str(e) + "): waiting for a re-arm")

    def stalled(self):
        # round over, not stopped, and nothing scheduled to start the next one
        return self.done and not self._terminated and not (self._refresh and self._refresh.is_alive())

    def stop(self):
        self._terminated = True
        if not self.done:
            self.actor.sock().send(b"s", b"$TERM")
            retry = 0
            while not self.done and retry < 10:
                sleep(0.1)
                retry += 1
        t, self._refresh = self._refresh, None      # a stopped client holds no finished Timer (3.13+: 8 MB each)
        if t:
            t.cancel()


    # CLIENT TimeSync REQ Zactor
    def actor_fn(self, pipe, args):
        self.status = 4
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        req_sock = Zsock.new_req(self.url)
        poller = Zpoller(internal_pipe, req_sock, None)
        internal_pipe.signal(0)
        retry = 0

        # safe_print("TimeClient: Starts sampling", self.client_ip)

        sampler = []
        sample = TimeSample(req_sock)

        while retry < 10:
            sock = poller.wait(500)

            # NOBODY responded ...
            if not sock:
                sample = TimeSample(req_sock)   # next Sample
                retry += 1

            # REP received
            elif sock == req_sock:
                retry = 0
                sample.recv()
                sampler.append( sample )
                # safe_print("Pong", sample.RTT, sample.CS)
                if len(sampler) >= SAMPLER_SIZE:
                    break
                sample = TimeSample(req_sock)   # next Sample

            # INTERNAL commands
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg or msg.popstr() == b"$TERM":
                    # print("Timeclient terminated")
                    break

        # safe_print("TimeClient: Sampling done", self.client_ip)
        self.compute(sampler)
        req_sock.__del__()
        self.done = True
        # A round that did not fill the sampler (master's time server not answering yet at a
        # fleet power-on, boot-storm packet loss) used to wait the full 120 s refresh before
        # trying again — a wall slave shows black that whole time (no clockshift, no chase, no
        # self-start). Retry a failed round after 10 s instead; a good round keeps the 120 s pace.
        if self.status != 1 and not self._terminated:
            self._arm(10)


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

            # safe_print("\t", "["+self.client_ip+"]", "clock shift", str(cs)+"µs", "using", len(sampler), "samples")
            if self.clockshift:
                safe_print("\t", "["+self.client_ip+"]", "correction =", str(self.clockshift-cs)+"µs")
            else:
                safe_print("\t", "["+self.client_ip+"]", "clock sync")

            self.clockshift = cs
            self.status = 1
            self.failures = 0
        else:
            # A failed round says the LINK was bad for 5 s, not that the shift we measured is wrong:
            # two Pi clocks drift microseconds a minute. Keep a good shift and its status; only a
            # client that never had one stays at 0. (Resetting it made every lossy minute on
            # kouagou03 look like "no clock", 2026-09-25.)
            self.failures += 1
            if self.status != 1:
                self.status = 0
            if self.failures in (1, 10) or self.failures % 60 == 0:
                safe_print("\t", "["+self.client_ip+"]", "ERROR: sampler not full.. something might be broken",
                           "(%d in a row%s)" % (self.failures, ', keeping the last good shift' if self.status == 1 else ''))





#
#  SUBSCRIBER to others publishing
#
class Subscriber():
    def __init__(self, node, ip, port, topic):
        self.node = node
        self.cache = {}

        self.sub = Zsock.new_sub(("tcp://"+ip+":"+port).encode(), topic.encode())

        self._actor_fn = zactor_fn(self.actor_fn_guarded) # ctypes function reference must live as long as the actor.
        self.done = True
        self.start()

        # self.node.interface.log("Subscribing to", ip)

    def start(self):
        if not self.done: 
            self.stop()
        
        self.actor = Zactor(self._actor_fn, create_string_buffer(b"Subscriber"))
        self.done = False
        
    def stop(self):
        # Only a running actor gets $TERM: a send into a finished actor's pipe has no peer and can
        # block (same trap as ZyreNode.stop, kmini-001 2026-09-04).
        if not self.done:
            try:
                self.actor.sock().send(b"s", b"$TERM")
            except Exception:
                pass
            retry = 0
            while not self.done and retry < 10:
                sleep(0.1)
                retry += 1
        self.sub.__del__()

    def subscribe(self, topic):
        Zsock.set_unsubscribe(self.sub, topic.encode())
        Zsock.set_subscribe(self.sub, topic.encode())

    # SUB Zactor
    def actor_fn(self, pipe, args):
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.
        poller = Zpoller(internal_pipe, self.sub, None)
        internal_pipe.signal(0)

        fastfail = 0
        while True:
            # STOP program (was `self.interface`, which a Subscriber does not have: every subscriber
            # actor died on its first loop from 2025-03 to 2026-09 — no peer.* pub/sub, and every
            # teardown waited its full second on an actor that would never answer)
            if self.node.interface.stopped.is_set():
                break

            # POLL
            now = time.time()
            sock = poller.wait(500)

            if not sock:
                if time.time() - now < 0.1:
                    # Same EINTR-vs-broken ambiguity as the node poller —
                    # and killing the whole app for one peer's subscriber is
                    # scorched earth. Debounce, then let THIS subscriber die;
                    # transport commands ride zyre proper and the wallclock
                    # rides its own multicast, so the wall keeps beating.
                    fastfail += 1
                    if fastfail >= 5:
                        self.node.interface.log('subscriber broken (5x fast-empty).. dropping this subscriber')
                        break
                else:
                    fastfail = 0
                continue
            fastfail = 0

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
                if peer:
                    name = peer.name
                    data = json.loads(msg.popstr().decode())
                    arg = {'name': name, 'data': data, 'at': int(time.time()*PRECISION)}
                    self.cache[topic] = arg
                    self.node.interface.emit(topic, arg)
                else:
                    safe_print('INVALID message received: Unknown Publisher !')
                

        safe_print("Subscriber terminated")
        self.done = True

    def actor_fn_guarded(self, pipe, args):
        try:
            self.actor_fn(pipe, args)
        finally:
            self.done = True


#
#   PEER
#
class Peer():
    def __init__(self, node, conf):
        self.node = node

        if isinstance(conf, ZyreEvent):
            conf2 = {
                'uuid':         conf.peer_uuid(),
                'ip':           extract_ip( conf.peer_addr() ),
                'name':         conf.peer_name().decode(),
            }

            try:
                conf2['ts_port'] = conf.header(b"TS-PORT").decode()
            except:
                self.node.interface.log(conf2['name']+' missing TS-PORT !')
                conf2['ts_port'] = None

            try:
                conf2['pub_port'] = conf.header(b"PUB-PORT").decode()
            except:
                self.node.interface.log(conf2['name']+' missing PUB-PORT !')
                conf2['pub_port'] = None

            conf = conf2

        for key in conf:
            setattr(self, key, conf[key])

        self.active = True

        self.link = 0   # 0: GONE / 1: SILENT / 2: EVASIVE / 3: OK
        self.timerLink = None
        self.linker(3)

        self.timeclient = None
        self.subscriber = None

    def stop(self):
        # safe_print('stopping peer')
        self.active = False

        t, self.timerLink = self.timerLink, None
        if t:
            # safe_print(' - cancel timelink')
            t.cancel()

        if self.timeclient:
            # safe_print(' - stop timeclient')
            self.timeclient.stop()

        if self.subscriber: 
            # safe_print(' - stop subscriptions')
            self.subscriber.stop()
            

    def linker(self, l):
        # The Timer that called us is self.timerLink: once its work is done, drop it — on CPython
        # 3.13+ a finished Timer kept in an attribute keeps its 8 MB stack (hplayer2#t-075).
        t, self.timerLink = self.timerLink, None
        if t:
            t.cancel()
        if not self.active: return

        if l != self.link:
            self.link = l
            self.node.interface.emit('peer.link', {'name': self.name, 'data': self.link})

        if self.link < 3:
            self.timerLink = Timer(PING_PEER*1.5/1000.0, self.linker, args=[l+1])
            try:
                self.timerLink.start()
            except RuntimeError as e:
                # `can't start new thread` (seen on kouagou02/03 during link-loss storms,
                # 2026-09-18..21): without this the link state machine stalled below 3 for good.
                # Step the link now instead of in PING_PEER*1.5 ms — a peer is still a peer.
                self.timerLink = None
                self.node.interface.log('peer', self.name, 'link timer unavailable (' + str(e) + '): linking now')
                self.linker(l+1)

    SYNC_MIN_INTERVAL = 30.0    # s between two TimeClients for one peer (JOIN storms)

    def sync(self, force=False):
        if not self.active: return
        if not self.ts_port: return
        tc = self.timeclient
        now = time.time()
        # A JOIN storm (link flapping) used to build a new TimeClient — a Zactor thread and a
        # Timer thread — on every JOIN. A healthy client stays; a new one at most every 30 s
        # unless the caller insists.
        if tc and not force and not tc.stalled() and now - getattr(self, '_syncAt', 0) < self.SYNC_MIN_INTERVAL:
            return
        if tc and not force and tc.status == 1 and not tc.stalled():
            return
        self._syncAt = now
        if tc:
            tc.stop()      # a second JOIN (or a wallclock re-sync) must not leave the old one sampling
        try:
            self.timeclient = TimeClient(self.ip, self.ts_port)
        except RuntimeError as e:
            self.timeclient = None
            self.node.interface.log('peer', self.name, 'time client unavailable (' + str(e) + '): wallclock will retry')

    def clockshift(self):
        if self.timeclient:
            return self.timeclient.clockshift
        return 0

    def subscribe(self, topics):
        if not self.active: return
        if not self.pub_port: return
        if not isinstance(topics, list): topics = [topics]
        for t in topics:
            top = 'peer.'+t
            if not self.subscriber:
                self.subscriber = Subscriber(self.node, self.ip, self.pub_port, top)
            else:
                self.subscriber.subscribe(top)
    



#
#  NODE zyre peers discovery, sync and communication
#
class ZyreNode ():
    def  __init__(self, interface, netiface=None):
        self.interface = interface

        # Peers book
        self.book = {}
        self.topics = []
        self.enters = 0        # ENTER/EXIT counters: the health monitor reads the flap rate
        self.exits = 0
        self.startedAt = time.time()
        self.gone = {}         # uuid -> (Peer, when): EXITed peers kept GONE_GRACE s for a flap-back

        # Publisher
        self.pub_cache  = {}
        self.publisher  = Zsock.new_xpub(("tcp://*:*").encode())

        # TimeServer
        self.timereply = Zsock.new_rep(("tcp://*:*").encode())
        
        # Zyre 
        self.zyre = Zyre(None)
        if netiface:
            self.zyre.set_interface( str(netiface).encode() )
            self.interface.log("ZYRE Node forced netiface: ", str(netiface).encode() )

        self.zyre.set_name(str(self.interface.hplayer.hostname()).encode())
        self.zyre.set_header(b"TS-PORT",  str(get_port(self.timereply)).encode())
        self.zyre.set_header(b"PUB-PORT", str(get_port(self.publisher)).encode())

        self.zyre.set_interval(PING_PEER)
        self.zyre.set_evasive_timeout(PING_PEER*3)
        self.zyre.set_silent_timeout(PING_PEER*5)
        self.zyre.set_expired_timeout(PING_PEER*10)

        self.zyre.start()
        self.uuid = self.zyre.uuid()      # cached: read by other threads (health) without touching zyre
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
        self._actor_fn = zactor_fn(self.actor_fn_guarded) # ctypes function reference must live as long as the actor.
        if netiface:
            netiface = create_string_buffer(str.encode(netiface))
        self.actor = Zactor(self._actor_fn, netiface)
        self.done = False
        self.broken = False    # set by actor_fn on confirmed poller failure

        # TimeServer on its own thread: the slaves' clock samples must be answered even while
        # this node's actor is busy with an ENTER/EXIT storm (it used to share that thread).
        self._tsStop = False
        self._tsDone = False
        self._tsThread = Thread(target=self._timeServer, name='zyre-timeserver', daemon=True)
        self._tsThread.start()

    GONE_GRACE = 20.0

    def _expireGone(self):
        now = time.time()
        for k in [k for k, (p, t) in self.gone.items() if now - t > self.GONE_GRACE]:
            reap(self.gone.pop(k)[0])

    def _samePeer(self, peer, e):
        try:
            return (peer.ip == extract_ip(e.peer_addr())
                    and str(peer.ts_port) == e.header(b"TS-PORT").decode()
                    and str(peer.pub_port) == e.header(b"PUB-PORT").decode())
        except Exception:
            return False

    def _timeServer(self):
        poller = Zpoller(self.timereply, None)
        try:
            while not self._tsStop and not self.interface.stopped.is_set():
                t = time.time()
                sock = poller.wait(250)
                if not sock and time.time() - t < 0.05:
                    sleep(0.05)             # an interrupted / broken poller must not spin a core
                if sock == self.timereply:
                    Zmsg.recv(self.timereply)
                    msg = Zmsg()
                    msg.addstr(str(int(time.time()*PRECISION)).encode())
                    Zmsg.send(msg, self.timereply)
                elif not sock:
                    continue
        except Exception as e:
            self.interface.log('time server stopped:', e)
        self._tsDone = True


    # An exception escaping the actor used to end it silently ("Exception ignored while calling
    # ctypes callback"): Kouagou01-64 ran 12 h with a dead node after one `can't start new thread`
    # (2026-09-25 23:54) — no zyre events, no time server, peers expired — and nothing noticed,
    # because the supervisor only watched for a broken poller. Now the node is flagged broken and
    # the supervisor rebuilds it in place.
    def actor_fn_guarded(self, pipe, netiface):
        try:
            self.actor_fn(pipe, netiface)
        except BaseException as e:
            self.interface.log('node actor died (' + type(e).__name__ + ': ' + str(e) + ').. flagging node for rebuild')
            self.broken = True
            self.done = True

    # ZYRE Zactor
    def actor_fn(self, pipe, netiface):

        print('start node actor')
        # Internal
        internal_pipe = Zsock(pipe, False) # We don't own the pipe, so False.

        # Poller
        poller = Zpoller(self.zyre.socket(), internal_pipe, self.publisher, None)

        # RUN
        self.interface.log('Node started')
        internal_pipe.signal(0)

        fastfail = 0
        while True:

            # STOP program
            if self.interface.stopped.is_set():
                self.interface.log('stopping node')
                break

            # POLL
            now = time.time()
            sock = poller.wait(500)

            if not sock:
                if time.time() - now < 0.1:
                    # Instant-empty return: an interrupted wait (EINTR-class)
                    # or a genuinely broken poller. One-shot detection used to
                    # kill the WHOLE APP on RF churn (wifi wall bench,
                    # 2026-07-22, twice): debounce, then flag the node for an
                    # in-place rebuild by the interface supervisor — never
                    # interface.quit() from here.
                    fastfail += 1
                    if fastfail >= 5:
                        self.interface.log('poller broken (5x fast-empty).. flagging node for rebuild')
                        self.broken = True
                        break
                else:
                    fastfail = 0
                continue
            fastfail = 0
            
            
            
            
            #
            # ZYRE receive
            #
            if sock == self.zyre.socket():
                e = ZyreEvent(self.zyre)
                uuid = e.peer_uuid()

                # self.interface.log("ZYREmsg", uuid, e.peer_name().decode(), e.type().decode())

                # ENTER: add to book for external contact (i.e. TimeSync)
                if e.type() == b"ENTER":
                    self.enters += 1
                    self._expireGone()
                    # The same process coming back (a link flap: EXIT then ENTER of one uuid, the
                    # Kouagou01-64 storm) gets its Peer back — clock client and subscriber intact —
                    # instead of a new Peer, Subscriber and TimeClient (threads) per flap.
                    old = self.book.get(uuid)
                    if not old and uuid in self.gone:
                        old = self.gone.pop(uuid)[0]
                        if self._samePeer(old, e):
                            old.active = True
                            self.book[uuid] = old
                            old.linker(3)
                            continue
                        reap(old)
                        old = None
                    if old and old.active and self._samePeer(old, e):
                        old.linker(3)
                        continue

                    newpeer = Peer(self, e)
                    # Replace any stale entry for this uuid or this NAME (a rebuilt node comes back
                    # with a new uuid). Torn down by the reaper: never block this thread (see reap).
                    for k in [k for k, p in self.book.items() if k == uuid or (p.name == newpeer.name and k != self.uuid)]:
                        reap(self.book.pop(k))
                    for k in [k for k, (p, _) in self.gone.items() if p.name == newpeer.name]:
                        reap(self.gone.pop(k)[0])

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
                    self.exits += 1
                    self._expireGone()
                    if uuid in self.book:
                        peer = self.book.pop(uuid)
                        peer.linker(0)
                        peer.active = False             # out of lookups (and the link timer stops climbing)
                        self.gone[uuid] = (peer, time.time())

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
            # INTERNAL commands
            #
            elif sock == internal_pipe:
                msg = Zmsg.recv(internal_pipe)
                if not msg or msg.popstr() == b"$TERM":
                    # safe_print('ZYRE Node TERM')
                    break
                    
        internal_pipe.__del__()
        self.interface.log('node stopped')   # WEIRD: print helps the closing going smoothly..
        self.done = True

    def stop(self):
        self.interface.log('stopping peers')
        for peer in list(self.book.values()) + [p for p, _ in list(self.gone.values())]:
            peer.stop()
        self.gone = {}

        self.interface.log('stopping node')
        # The actor usually leaves by itself (its loop breaks on `stopped`), and czmq
        # closes its side of the pipe when the fn returns. A $TERM sent into that
        # finished actor is a PAIR send with no peer: it blocks forever — that held
        # every `systemctl stop` until the 90 s SIGKILL (kmini-001, 2026-09-04). Only
        # ask a still-running actor to leave, and give it a bounded second.
        if not self.done:
            self.actor.sock().send(b"ss", b"$TERM")
            retry = 0
            while not self.done and retry < 10:
                sleep(0.1)
                retry += 1

        self._tsStop = True
        retry = 0
        while not self._tsDone and retry < 10:
            sleep(0.1)
            retry += 1

        # self.zyre.stop()        # HANGS !
        self.zyre.__del__()
        self.publisher.__del__()
        self.timereply.__del__()
            

    def peer(self, uuid):
        if uuid in self.book and self.book[uuid].active:
            return self.book[uuid]

    def peerByName(self, name):
        for peer in list(self.book.values()):     # snapshot: the actor thread adds/removes peers
            if peer.active and peer.name == name:
                return peer

    #
    # PUB/SUB
    #

    def subscribe(self, topics):
        if not isinstance(topics, list): topics = [topics]
        self.topics = list(set(self.topics) | set(topics))    # merge lists and remove duplicates
        for peer in list(self.book.values()):     # snapshot (see peerByName)
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

    def makeMsg(self, event, args=None, delay_ms=0, at=0):
        data = {}
        data['event'] = event
        data['args'] = []
        if args:
            if not isinstance(args, list):
                # self.interface.log('NOT al LIST', args)
                args = [args]
            data['args'] = args

        # at time
        if at > 0:
            data['at'] = at

        # add delay
        if delay_ms > 0:
            if not 'at' in data: 
                data['at'] = 0
            data['at'] += int(time.time()*PRECISION + delay_ms * PRECISION / 1000)

        return json.dumps(data).encode()

    def whisper(self, uuid, event, args=None, delay_ms=0, at=0):
        data = self.makeMsg(event, args, delay_ms, at)
        if uuid == self.zyre.uuid():
            data = json.loads(data.decode())
            data['from'] = 'self'
            data['group'] = 'whisper'
            self.preProcessor1(data)
        else:
            self.zyre.whispers(uuid, data)

    def shout(self, group, event, args=None, delay_ms=0, at=0):
        data = self.makeMsg(event, args, delay_ms, at)
        self.zyre.shouts(group.encode(), data)

        # if own group -> send to self too !
        groups = zlist_strlist( self.zyre.own_groups() )
        if group in groups:
            data = json.loads(data.decode())
            data['from'] = 'self'
            data['group'] = group
            self.preProcessor1(data)

    def broadcast(self, event, args=None, delay_ms=0, at=0):
        self.shout('broadcast', event, args, delay_ms, at)
        
    def tomyself(self, event, args=None, delay_ms=0, at=0):
        self.whisper(self.zyre.uuid(), event, args, delay_ms, at)

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
            at = data['at'] / PRECISION
            delay =  at - time.time()

            if delay <= -10:
                self.interface.log('WARNING event already passed by', delay, 's, its very late !! might be out of sync !')
                self.preProcessor2(data)
            elif delay <= 0.1:
                self.interface.log('WARNING event already passed by', delay, 's, playing late... ')
                self.preProcessor2(data)
            elif delay > 3:
                self.interface.log('WARNING event in', delay, 's, thats weird, playing now... ')
                self.preProcessor2(data)
            else:
                
                # play event -> propagate now paused and timer to unpause
                # if data['event'].startswith('play'):
                #     dataNow = data.copy()
                #     dataNow['event'] = dataNow['event'].replace('play', 'playpause')
                #     self.preProcessor2(dataNow)
                #     data['event'] = 'resumesync'   
                
                # event is programmed in the future
                self.interface.log('programmed event in', delay, 's')
                t = Timer( delay-0.03, self.preProcessor2, args=[data, at])
                t.start()
                self.interface.emit('planned', data)

        else:
            self.preProcessor2(data)

    def preProcessor2(self, data, at=0):
        
        # busy loop until time is reached
        while at > 0 and at-time.time() >= 0.0005:
            time.sleep(0.0005)
            # self.interface.log('busy loop', at-time.time())
        
        self.interface.log('zyre processor sync accuracy', (time.time()-at)*1000, 'ms')
        self.interface.emit('event', *[data])
        self.interface.emit(data['event'], *data['args'])


#
#  HPLAYER2 Zyre interface
#
class ZyreInterface (BaseInterface):

    def  __init__(self, hplayer, netiface=None):
        if _ZYRE_IMPORT_ERROR:
            raise RuntimeError("zyre is required for ZyreInterface") from _ZYRE_IMPORT_ERROR
        if _CZMQ_IMPORT_ERROR:
            raise RuntimeError("czmq is required for ZyreInterface") from _CZMQ_IMPORT_ERROR
        required = [Zyre, ZyreEvent, Zsock, Zmsg, Zpoller, Zactor, zactor_fn]
        if any(dep is None for dep in required):
            raise RuntimeError("zyre interface dependencies are unavailable")
        super().__init__(hplayer, "ZYRE")
        self.iface = netiface
        # Handlers are registered HERE, on the main thread at construction, not in listen():
        # registering listeners from the interface thread while the main thread is emitting
        # (settings.load() at startup) mutates pymitter's listener tree under its own iteration
        # — `RuntimeError: dictionary changed size during iteration`, HPlayer2 down at its first
        # start and back on systemd's restart 20 s later (Tapuaki01 cold start, 2026-09-21).
        # They resolve self.node at call time and do nothing while it is not up.
        self._installHandlers()

    def _installHandlers(self):
        def node():
            return getattr(self, 'node', None)

        # Publish self status
        @self.hplayer.on('*.playing')
        @self.hplayer.on('*.paused')
        @self.hplayer.on('*.stopped')
        def st(ev, *args):
            n = node()
            if n:
                n.publish('peer.status', self.hplayer.statusPlayers())

        # Publish self settings
        @self.hplayer.on('settings.updated')
        def se(ev, settings):
            n = node()
            if n:
                n.publish('peer.settings', settings)

        # Publish when self do play seq
        @self.hplayer.on('*.playingseq')
        def seq(ev, *args):
            n = node()
            if n:
                n.publish('peer.playingseq', args)

        # Subscribe to peers
        @self.hplayer.on('*.peers.subscribe')
        def mon(ev, topics):
            n = node()
            if n:
                n.subscribe(topics)

        # Trig peers link status
        @self.hplayer.on('*.peers.getlink')
        def links(ev):
            n = node()
            if not n:
                return
            for peer in list(n.book.values()):
                self.emit('peer.link', {'name': peer.name, 'data': peer.link})

        # Triggers event on peers
        @self.hplayer.on('*.peers.triggers')
        def trig(ev, *args):
            n = node()
            if not n:
                self.log('peers.triggers while the node is not up: dropped')
                return
            delay = args[1] if len(args) > 1 else 0
            at = int(time.time()*PRECISION + delay * PRECISION / 1000)
            for ev in args[0]:
                if not 'synchro' in ev:
                    ev['synchro'] = False
                data = None
                if 'data' in ev:
                    data = ev['data']
                if 'peer' in ev:
                    peer = n.peerByName(ev['peer'])
                    if peer:
                        self.log('whisper', ev['peer'], ev['event'], data, at if ev['synchro'] else 0)
                        n.whisper( peer.uuid, ev['event'], data, 0, at if ev['synchro'] else 0)
                    else:
                        self.log('peer is missing', ev['peer'])
                else:
                    n.broadcast(ev['event'], data, 0, at if ev['synchro'] else 0)

    # A node started on an interface that has no address yet never beacons: on a fleet
    # power-on the slaves' HPlayer2 comes up before the master's DHCP has answered, zyre
    # is started on a bare eth0/wlan0 and the wallclock waits for discovery forever — the
    # 6-screen wall came up master-only after every full power cycle (atafuwa, 2026-09-14).
    # Wait for the address (bounded), and rebuild the node if the address changes later.
    IP_WAIT = 90.0

    def _ifaceIp(self):
        if not self.iface:
            return None
        ip = network.get_ip(self.iface)
        return ip if ip and ip != '127.0.0.1' else None

    def _waitIfaceIp(self):
        if not self.iface:
            return None
        ip = self._ifaceIp()
        if ip:
            return ip
        self.log('no address on', self.iface, 'yet: waiting up to', int(self.IP_WAIT), 's before starting the node')
        t0 = time.time()
        while not ip and time.time() - t0 < self.IP_WAIT and self.isRunning() and not self.stopped.is_set():
            self.stopped.wait(1)
            ip = self._ifaceIp()
        self.log(('address on ' + self.iface + ': ' + ip + ' after %.0f s' % (time.time() - t0)) if ip
                 else (self.iface + ' still has no address after ' + str(int(self.IP_WAIT)) + ' s: starting the node anyway'))
        return ip

    def requestRebuild(self, why):
        """Ask the supervisor to rebuild the node in place (e.g. the wallclock hears the master's
        clock but no zyre peer appears for a minute: a master rebooted or swapped under running
        slaves keeps our address, so the address-change rebuild never fires — LACROIX 2026-09-15)."""
        self._rebuildWhy = why

    def listen(self):
        self._rebuildWhy = None
        self._boundIp = self._waitIfaceIp()
        self.node = ZyreNode(self, self.iface)
        # (the hplayer event handlers live in _installHandlers(), registered at construction)

        self.log( "interface ready")

        # Supervise the node: on a confirmed poller failure (RF churn /
        # EINTR storms — wifi wall bench, 2026-07-22) rebuild the zyre node
        # IN PLACE: peers rediscover in seconds and the wall keeps beating.
        # The handlers above resolve self.node at call time, so reassigning
        # it is enough. If it keeps breaking, exit honestly with the
        # engine's force-exit failsafe — systemd (Restart=always) then
        # resurrects a clean app instead of tonight's half-dead unsynced
        # zombie.
        recoveries = []
        while True:
            self.stopped.wait(2)
            if not self.isRunning():
                break
            # address appeared or changed under the node (late DHCP lease, renewed lease
            # with another address): the beacon is bound to the old one -> rebuild, not
            # counted as a failure
            ip = self._ifaceIp()
            why = self._rebuildWhy
            if (self.iface and ip and ip != self._boundIp) or why:
                if why:
                    self.log('rebuilding zyre node in place:', why)
                    self._rebuildWhy = None
                else:
                    self.log('address on', self.iface, 'changed', self._boundIp, '->', ip, ': rebuilding zyre node')
                self._boundIp = ip or self._boundIp
                try:
                    self.node.stop()
                except Exception as e:
                    self.log('old node teardown error (continuing):', e)
                if self.stopped.is_set() or not self.isRunning():
                    break
                try:
                    self.node = ZyreNode(self, self.iface)
                except Exception as e:
                    self.log('zyre node rebuild FAILED:', e, '— exiting for a clean app restart')
                    self.hplayer.request_shutdown(exit_code=1, force_delay=10.0)
                    break
                continue
            if not getattr(self.node, 'broken', False):
                continue
            now = time.time()
            recoveries = [t for t in recoveries if now - t < 600]
            recoveries.append(now)
            if len(recoveries) > 3:
                self.log('zyre broke', len(recoveries), 'times in 10min: exiting for a clean app restart')
                self.hplayer.request_shutdown(exit_code=1, force_delay=10.0)
                break
            self.log('rebuilding zyre node in place (recovery', len(recoveries), 'of 3)')
            try:
                self.node.stop()
            except Exception as e:
                self.log('old node teardown error (continuing):', e)
            # A SIGTERM breaks the poller too: if the app started stopping
            # while we tore the old node down, don't rebuild into shutdown.
            if self.stopped.is_set() or not self.isRunning():
                break
            try:
                self.node = ZyreNode(self, self.iface)
            except Exception as e:
                # a node we cannot rebuild is a player we cannot sync:
                # exit honestly, systemd brings back a clean app
                self.log('zyre node rebuild FAILED:', e, '— exiting for a clean app restart')
                self.hplayer.request_shutdown(exit_code=1, force_delay=10.0)
                break

        self.log( "closing sockets...") # CLOSING is messy !
        try:
            self.node.stop()
        except Exception as e:
            self.log('node stop error:', e)
        self.log( "done.")

    def activeCount(self):
        return len(self.node.book)

    def peersList(self):
        return self.node.book

        
