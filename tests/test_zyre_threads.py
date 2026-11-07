"""Zyre node thread-safety: publish() and every call on the zyre actor pipe come from any
thread — at a media change the two mpv listener threads emit `stopped` in the same
millisecond, and each emit runs ZyreNode.publish() in its own thread (HPO 2026-10-15).

On libzyre 2.0.1 zyre_uuid() is not a getter: it frees its cached string and asks the zyre
actor again, and ctypes drops the GIL around every native call, so two threads inside it at
once double-free -> python3 SIGSEGV. No czmq/zyre here: the bindings are replaced by fakes
that count how often the uuid is asked, and record any moment two threads are inside the
same native object at once.
"""
import itertools, json, threading, time, types

import pytest

import core.interfaces.zyre as zyremod


class Window:
    """One native object: records every moment two threads are inside it together."""
    def __init__(self):
        self._mx = threading.Lock()
        self._inside = 0
        self.calls = 0
        self.overlaps = 0

    def enter(self):
        with self._mx:
            self._inside += 1
            self.calls += 1
            if self._inside > 1:
                self.overlaps += 1
        time.sleep(0.0005)      # ctypes drops the GIL around the real call: hold the window open
        with self._mx:
            self._inside -= 1


class FakeSock:
    """A zsock: what was sent on it, by which threads, and a queue for the reading end."""
    def __init__(self, port):
        self.port = port
        self.window = Window()
        self.frames = []
        self.senders = set()
        self.queue = []
        self.cv = threading.Condition()
        self.sndtimeo = -1

    def endpoint(self):
        return ('tcp://0.0.0.0:%d' % self.port).encode()

    def deliver(self, frames):
        self.window.enter()
        with self.cv:
            self.frames.append(frames)
            self.senders.add(threading.current_thread().name)
            self.queue.append(frames)
            self.cv.notify_all()

    def take(self):
        with self.cv:
            return self.queue.pop(0) if self.queue else None

    def send(self, picture, *args):
        self.deliver(list(args))

    def signal(self, status):
        pass

    def __del__(self):
        pass


class FakeZmsg:
    def __init__(self):
        self.frames = []

    def addstr(self, s):
        self.frames.append(s)

    def popstr(self):
        return self.frames.pop(0) if self.frames else None

    @staticmethod
    def send(msg, sock):
        sock.deliver(list(msg.frames))

    @staticmethod
    def recv(sock):
        frames = sock.take()
        if frames is None:
            return None
        msg = FakeZmsg()
        msg.frames = list(frames)
        return msg

    @staticmethod
    def dup(msg):
        copy = FakeZmsg()
        copy.frames = list(msg.frames)
        return copy


class FakeZsock:
    """Zsock(ptr, False) wraps the actor's own end of its pipe: here, the very same queue."""
    ports = itertools.count(6000)

    def __new__(cls, ptr, owned=True):
        return ptr

    @staticmethod
    def new_xpub(endpoint):
        return FakeSock(next(FakeZsock.ports))

    @staticmethod
    def new_rep(endpoint):
        return FakeSock(next(FakeZsock.ports))

    @staticmethod
    def set_sndtimeo(sock, ms):
        sock.sndtimeo = ms


class FakeZyre:
    """The zyre handle. In libzyre 2.0.1 every call below crosses ONE actor pipe."""
    def __init__(self, _):
        self.pipe = Window()
        self.uuid_calls = 0
        self.inbox = FakeSock(5999)

    def set_interface(self, *args):
        pass
    set_name = set_header = set_interval = set_interface
    set_evasive_timeout = set_silent_timeout = set_expired_timeout = set_interface

    def start(self):
        pass

    def socket(self):
        return self.inbox

    def uuid(self):
        self.uuid_calls += 1
        self.pipe.enter()
        return b'DESK-UUID'

    def name(self):
        self.pipe.enter()
        return b'desk'

    def join(self, group):
        self.pipe.enter()

    def leave(self, group):
        self.pipe.enter()

    def whispers(self, uuid, data):
        self.pipe.enter()

    def shouts(self, group, data):
        self.pipe.enter()

    def own_groups(self):
        self.pipe.enter()
        return ['broadcast', 'sync']

    def __del__(self):
        pass


class FakeZactor:
    """zactor_new without the thread: a test runs actor_fn itself when it needs the actor side."""
    def __init__(self, fn, args):
        self.fn = fn
        self.pipe = FakeSock(5998)

    def sock(self):
        return self.pipe


class FakePoller:
    def __init__(self, *socks):
        self.pipe = socks[1]        # actor_fn polls (zyre, internal pipe, publisher, timereply)

    def wait(self, ms):
        with self.pipe.cv:
            if self.pipe.cv.wait_for(lambda: self.pipe.queue, timeout=ms / 1000):
                return self.pipe
        return None


class FakeInterface:
    def __init__(self):
        self.stopped = threading.Event()
        self.hplayer = types.SimpleNamespace(hostname=lambda: 'desk')
        self.logs = []

    def log(self, *args):
        self.logs.append(args)

    def emit(self, *args):
        pass


@pytest.fixture
def node(monkeypatch):
    fakes = {'Zyre': FakeZyre, 'ZyreEvent': type('FakeZyreEvent', (), {}), 'Zsock': FakeZsock,
             'Zmsg': FakeZmsg, 'Zactor': FakeZactor, 'Zpoller': FakePoller, 'zactor_fn': lambda fn: fn,
             'zlist_strlist': lambda groups: list(groups)}
    for name, fake in fakes.items():
        monkeypatch.setattr(zyremod, name, fake)
    return zyremod.ZyreNode(FakeInterface())


def together(fn, threads=2, rounds=50):
    """`threads` threads released by one barrier, each calling fn(t, i) `rounds` times —
    the two mpv listeners at a media change."""
    gate = threading.Barrier(threads)
    errors = []

    def run(t):
        gate.wait()
        for i in range(rounds):
            try:
                fn(t, i)
            except Exception as err:
                errors.append(err)

    workers = [threading.Thread(target=run, args=(t,), name='listener-%d' % t) for t in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert not errors


def test_uuid_is_read_once_at_init(node):
    assert node.zyre.uuid_calls == 1
    assert node.uuid == b'DESK-UUID' and node.uuid in node.book

    together(lambda t, i: node.publish('peer.status', {'t': t, 'i': i}))
    together(lambda t, i: node.tomyself('ping'))

    assert node.zyre.uuid_calls == 1


def test_two_threads_publish_through_the_actor_pipe_one_at_a_time(node):
    together(lambda t, i: node.publish('peer.status', {'t': t, 'i': i}))

    pipe = node.actor.sock()
    assert pipe.sndtimeo == 200                 # a dead actor drops a publish, never blocks the caller
    assert node.publisher.frames == []          # no caller thread touched the XPUB
    assert len(pipe.frames) == 100
    assert pipe.window.overlaps == 0
    assert all(f[:2] == [b'PUB', b'peer.status'] for f in pipe.frames)


def test_the_actor_sends_and_caches_every_publish(node):
    actor = threading.Thread(target=node.actor_fn, args=(node.actor.sock(), None), name='actor')
    actor.start()

    together(lambda t, i: node.publish('peer.status', {'t': t, 'i': i}))
    node.stop()                                 # $TERM through the same pipe, under the same lock
    actor.join(2)

    assert not actor.is_alive() and node.done
    assert node.publisher.senders == {'actor'}
    assert len(node.publisher.frames) == 100
    topic, uuid, payload = node.publisher.frames[-1]
    assert (topic, uuid) == (b'peer.status', b'DESK-UUID')
    assert node.pub_cache[b'peer.status'].frames == [topic, uuid, payload]
    assert json.loads(payload)['i'] == 49

    sent = len(node.actor.sock().frames)
    node.publish('peer.status', {'late': True})  # after stop: dropped, not queued to a dead actor
    assert len(node.actor.sock().frames) == sent


def test_zyre_actor_calls_never_overlap(node):
    calls = [lambda: node.whisper(b'PEER-UUID', 'play', ['a.mp4']),
             lambda: node.shout('sync', 'stop'),
             lambda: node.join('extra'),
             lambda: node.leave('extra')]
    before = node.zyre.pipe.calls

    together(lambda t, i: calls[(t + i) % len(calls)]())

    assert node.zyre.pipe.calls - before >= 100
    assert node.zyre.pipe.overlaps == 0
