"""Zyre teardown on ONE owner thread (hplayer2#t-077).

0d13c87 (2026-09-29) dropped a stopped TimeClient's/Subscriber's actor and ctypes callback in
place, inside stop(). Under a peer storm kouagou03 died twice with SIGSEGV: stop() ran on two
threads at once (the node's actor through Peer.sync, the reaper through Peer.stop); the first
blocked in zactor_destroy while the callback had not returned yet, the second freed the libffi
closure the C thread was still executing. And an object whose last reference died on its own
actor's thread would have run zactor_destroy there, waiting for itself.

No czmq here: the fakes keep exactly the semantics those two crashes hang on.
  - Thunk = a CFUNCTYPE. C holds no Python reference to it: freed while its handler still runs
    = the SIGSEGV (recorded, not crashed).
  - ActorZactor = zactor_new / zactor_destroy: a real thread runs the handler; destroy sends
    $TERM and waits for the handler to return; destroy from the actor's own thread = it would
    wait for itself (recorded). sock() on a destroyed actor = czmq's assert (recorded).
"""
import gc, random, threading, time, weakref

import pytest

import core.interfaces.zyre as zyremod
from test_zyre_threads import FakeSock, FakeZmsg, FakeZsock, FakeZyre, FakePoller, FakeInterface


class World:
    """What every fake reports to: the hazards seen, every actor ever made."""
    def __init__(self):
        self.violations = []
        self.actors = []
        self.thunks = []
        self.polled = set()         # id() of sockets a live actor is polling
        self.lock = threading.Lock()

    def violate(self, what):
        with self.lock:
            self.violations.append(what)


W = None


class Thunk:
    """A ctypes CFUNCTYPE around a bound method."""
    def __init__(self, fn):
        self.fn = fn
        self.state = {'executing': 0, 'freed': False}
        weakref.finalize(self, Thunk._freed, self.state, W)
        W.thunks.append(self.state)

    @staticmethod
    def _freed(state, world):
        state['freed'] = True
        if state['executing']:
            world.violate('callback freed while its handler runs (the SIGSEGV of 30/09)')


class ActorPipe(FakeSock):
    def __init__(self):
        super().__init__(5997)
        self.started = threading.Event()

    def signal(self, status):
        self.started.set()

    def wait_term(self, timeout):
        """Block until something arrives on the pipe (the $TERM) or the round's time is up."""
        with self.cv:
            return self.cv.wait_for(lambda: self.queue, timeout=timeout)


class ActorZactor:
    """zactor_new(handler, args) / zactor_destroy."""
    def __init__(self, thunk, args):
        # C keeps the function POINTER: no reference to the thunk object itself
        self.state = thunk.state
        self.pipe = ActorPipe()
        self.ended = threading.Event()
        self.destroyed_by = []         # the thread(s) that ran zactor_destroy: one, the reaper
        self.ident = None
        self.thread = threading.Thread(target=self._shim, args=(thunk.fn, args), daemon=True,
                                       name='actor-%d' % len(W.actors))
        W.actors.append(self)
        self.thread.start()
        self.pipe.started.wait(5)           # zactor_new waits for the handler's first signal

    def _shim(self, fn, args):
        self.ident = threading.get_ident()
        self.state['executing'] += 1
        try:
            fn(self.pipe, args)
        finally:
            fn = None
            if self.state['freed']:
                W.violate('handler returned into a freed callback')
            self.state['executing'] -= 1
            self.ended.set()                # the shim's last signal

    def sock(self):
        if self.destroyed_by:
            W.violate('sock() on a destroyed actor (czmq asserts)')
        return self.pipe

    def destroy(self):
        if self.destroyed_by:
            return                          # zactor_destroy(&NULL): no-op
        if threading.get_ident() == self.ident:
            W.violate('zactor_destroy on the actor\'s own thread (waits for itself)')
            self.destroyed_by.append(threading.current_thread().name)
            return
        if not self.ended.is_set():
            self.pipe.send(b"s", b"$TERM")
            if not self.ended.wait(5):
                W.violate('zactor_destroy hung')
        self.destroyed_by.append(threading.current_thread().name)

    def __del__(self):                  # the binding's destructor: zactor_destroy, explicit or at refcount 0
        self.destroy()


class SubSock(FakeSock):
    def __init__(self):
        super().__init__(5996)
        self.destroyed = 0

    def __del__(self):
        if id(self) in W.polled:
            W.violate('SUB socket destroyed under its running actor')
        self.destroyed += 1


class SubZsock(FakeZsock):
    @staticmethod
    def new_sub(url, topic):
        return SubSock()

    @staticmethod
    def set_subscribe(sock, topic):
        pass
    set_unsubscribe = set_subscribe


class LogInterface(FakeInterface):
    """Logs text, like the real interface: a kept exception object would hold its frame, and the
    node through it (the fake time server dies at once on FakePoller and logs why)."""
    def log(self, *args):
        self.logs.append(' '.join(str(a) for a in args))


LINGER = [0.02]     # s between `done = True` and the handler's return: 0d13c87's window


def client_round(self, pipe, args):
    """TimeClient.actor_fn: one sampling round — ends on $TERM, or by itself after `round`."""
    pipe.signal(0)
    pipe.wait_term(getattr(self, 'round_s', 5.0))
    self.status = 1
    self.done = True
    time.sleep(LINGER[0])


def subscriber_loop(self, pipe, args):
    """Subscriber.actor_fn: polls the SUB socket until $TERM (+ a slow exit when asked)."""
    W.polled.add(id(self.sub))
    pipe.signal(0)
    pipe.wait_term(5.0)
    time.sleep(getattr(self, 'slow_exit', 0.0))
    W.polled.discard(id(self.sub))
    self.done = True


@pytest.fixture
def world(monkeypatch):
    global W
    W = World()
    for name, fake in {'Zyre': FakeZyre, 'ZyreEvent': type('FakeZyreEvent', (), {}), 'Zsock': SubZsock,
                       'Zmsg': FakeZmsg, 'Zactor': ActorZactor, 'Zpoller': FakePoller,
                       'zactor_fn': Thunk}.items():
        monkeypatch.setattr(zyremod, name, fake)
    monkeypatch.setattr(zyremod.TimeClient, 'actor_fn', client_round)
    monkeypatch.setattr(zyremod.Subscriber, 'actor_fn', subscriber_loop)
    LINGER[0] = 0.02
    gc.disable()                            # what dies here dies by refcount, not by a collect
    yield W
    gc.enable()
    gc.collect()


def drain():
    """Wait until the reaper has ended everything handed to it so far."""
    done = threading.Event()
    zyremod._reapQ.put(done.set)
    zyremod._startReaper()
    assert done.wait(10), 'reaper stuck'


def settle(world):
    drain()
    for a in world.actors:
        assert a.ended.wait(5), 'an actor never returned'


def assert_clean(world):
    assert world.violations == []
    for a in world.actors:
        assert a.destroyed_by == ['zyre-reaper'], a.destroyed_by
    assert all(t['freed'] for t in world.thunks), 'a callback outlived its actor'


def test_two_threads_stopping_one_client_never_free_the_callback_under_it(world):
    """The 30/09 crash: the node's actor (Peer.sync) and the reaper (Peer.stop) in stop() at once."""
    LINGER[0] = 0.15
    tc = zyremod.TimeClient('10.0.0.2', '5000')
    gate = threading.Barrier(2)

    def stopper():
        gate.wait()
        tc.stop()

    ts = [threading.Thread(target=stopper, name=n) for n in ('node-actor', 'listen')]
    for t in ts:
        t.start()
    for t in ts:
        t.join(5)
    settle(world)

    assert tc.actor is None and tc._actor_fn is None
    assert len(world.actors) == 1
    assert_clean(world)


def test_a_stop_on_the_actors_own_thread_does_not_wait_for_itself(world, monkeypatch):
    stopped = threading.Event()

    def round_that_stops_its_client(self, pipe, args):
        pipe.signal(0)
        if not stopped.is_set():
            stopped.set()
            self.stop()                 # the last word on this client comes from its own actor
        self.done = True

    monkeypatch.setattr(zyremod.TimeClient, 'actor_fn', round_that_stops_its_client)
    tc = zyremod.TimeClient('10.0.0.2', '5000')
    assert stopped.wait(5)
    settle(world)
    assert_clean(world)
    assert tc._closed


def test_a_refresh_landing_after_stop_starts_nothing(world):
    tc = zyremod.TimeClient('10.0.0.2', '5000')
    tc.stop()
    tc.start()                          # the refresh Timer, the clock-step Timer, the wallclock
    tc._arm(10)                         # a round ending after stop()
    settle(world)
    assert len(world.actors) == 1 and tc.actor is None and tc._refresh is None
    assert_clean(world)


def test_a_stopped_client_dies_by_refcount(world):
    tc = zyremod.TimeClient('10.0.0.2', '5000')
    refresh = tc._refresh
    ref = weakref.ref(tc)
    tc.stop()
    settle(world)
    refresh.join(5)                     # a cancelled Timer still holds start() until its thread exits
    del tc, refresh
    assert ref() is None, 'a stopped client waits for a collect (a cycle is left)'
    assert_clean(world)


def test_a_round_replaced_by_start_ends_on_the_reaper(world):
    """Every 120 s refresh (and every clock step) replaces the actor: the old one ends on the reaper."""
    tc = zyremod.TimeClient('10.0.0.2', '5000')
    for _ in range(5):
        tc.start()
    tc.stop()
    settle(world)
    assert len(world.actors) == 6
    assert_clean(world)


def test_a_storm_of_starts_stops_and_resyncs_ends_every_actor_once_on_the_reaper(world):
    """JOIN storm shape: Peer.sync replacing clients, refresh/clock-step restarts, reaper stops."""
    LINGER[0] = 0.005
    rnd = random.Random(77)
    slots = [zyremod.TimeClient('10.0.0.%d' % i, '5000') for i in range(4)]
    for tc in slots:
        tc.round_s = 0.03
    retired = []
    mx = threading.Lock()
    t_end = time.monotonic() + 2.0

    def worker(seed):
        r = random.Random(seed)
        while time.monotonic() < t_end:
            i = r.randrange(len(slots))
            op = r.random()
            tc = slots[i]
            if op < 0.5:
                tc.start()
            elif op < 0.8:
                tc.stop()
            else:                       # Peer.sync: stop the old one, build a new one
                tc.stop()
                new = zyremod.TimeClient('10.0.0.%d' % i, '5000')
                new.round_s = 0.03
                with mx:
                    retired.append(slots[i])
                    slots[i] = new
            time.sleep(r.random() * 0.01)

    ws = [threading.Thread(target=worker, args=(rnd.random(),), name='storm-%d' % k) for k in range(3)]
    for w in ws:
        w.start()
    for w in ws:
        w.join(30)
    for tc in slots + retired:
        tc.stop()
    settle(world)

    assert len(world.actors) > 20
    assert_clean(world)


def test_subscriber_socket_is_destroyed_after_its_actor_returned(world):
    node = type('N', (), {})()
    node.interface = LogInterface()
    sub = zyremod.Subscriber(node, '10.0.0.2', '5001', 'peer.status')
    sub.slow_exit = 1.5                 # longer than stop()'s bounded second
    sock = sub.sub
    sub.stop()
    sub.stop()                          # Peer.stop from the reaper and the node's stop: once
    settle(world)
    assert sock.destroyed == 1
    assert_clean(world)


def test_node_stop_ends_its_actor_on_the_reaper_and_leaves_no_cycle(world):
    node = zyremod.ZyreNode(LogInterface())
    ref = weakref.ref(node)
    actor = node.actor
    node.stop()
    node.stop()                         # once
    settle(world)
    assert node.actor is None and node._actor_fn is None
    assert node.book == {} and node.gone == {}
    assert actor.destroyed_by == ['zyre-reaper']
    del node, actor
    assert ref() is None, 'a stopped node waits for a collect (a cycle is left)'
    assert_clean(world)
