"""Two players with one name on one LAN: the second must still serve (hplayer2#t-109).

Seen 25/11 on the rig: bench-01 and bench-03 both booted as player-000, and the second one's
http2 thread died on zeroconf's NonUniqueNameException before its web server started — no web
interface at all. http and osc registered the same way. core/engine/mdns.py renames a taken
name and swallows every other zeroconf failure; these tests hold the interfaces to « the server
starts whatever mDNS does ».
"""
import threading
import time
import urllib.request

import pytest

zeroconf = pytest.importorskip("zeroconf")

from core.engine import mdns  # noqa: E402

HTTP = "_http._tcp.local."


class FakeZeroconf:
    """register_service as python-zeroconf behaves on a LAN where some names are taken."""

    taken = set()
    fail_with = None            # every register raises this (a busy or broken mdns stack)
    instances = []

    def __init__(self):
        self.registered, self.unregistered, self.closed = [], [], False
        FakeZeroconf.instances.append(self)

    def register_service(self, info, ttl=None, allow_name_change=False, **kw):
        if FakeZeroconf.fail_with is not None:
            raise FakeZeroconf.fail_with
        if info.name in FakeZeroconf.taken:
            if not allow_name_change:
                raise zeroconf.NonUniqueNameException
            instance = info.name[: -len(info.type) - 1]
            info.name = instance + "-2." + info.type          # what zeroconf 0.149 does
        self.registered.append(info.name)

    def unregister_service(self, info):
        self.unregistered.append(info.name)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_zc(monkeypatch):
    FakeZeroconf.taken, FakeZeroconf.fail_with, FakeZeroconf.instances = set(), None, []
    monkeypatch.setattr(mdns, "Zeroconf", FakeZeroconf)
    monkeypatch.setattr(mdns, "get_allip", lambda: ["10.0.0.5"])
    monkeypatch.setattr(mdns, "get_hostname", lambda: "player-000")
    return FakeZeroconf


def test_a_taken_name_is_renamed_and_logged(fake_zc):
    fake_zc.taken = {"HPlayer2._player-000." + HTTP}
    logs = []
    advert = mdns.advertise([(HTTP, "HPlayer2._player-000", 80)], lambda *a: logs.append(a))
    assert advert.names() == ["HPlayer2._player-000-2." + HTTP]
    assert any("name taken" in str(line) for line in logs)

    zc = fake_zc.instances[0]
    mdns.withdraw(advert)
    assert zc.unregistered == ["HPlayer2._player-000-2." + HTTP]   # the name it really holds
    assert zc.closed


def test_a_free_name_is_kept(fake_zc):
    logs = []
    advert = mdns.advertise([(HTTP, "HPlayer2._player-000", 80)], lambda *a: logs.append(a))
    assert advert.names() == ["HPlayer2._player-000." + HTTP]
    assert logs == []


def test_a_failing_registration_only_logs(fake_zc):
    fake_zc.fail_with = RuntimeError("mdns stack busy")
    logs = []
    assert mdns.advertise([(HTTP, "HPlayer2._player-000", 80)], lambda *a: logs.append(a)) is None
    assert fake_zc.instances[0].closed                    # nothing registered: socket released
    assert any("could not advertise" in str(line) for line in logs)
    mdns.withdraw(None)                                   # the shutdown path takes the None


def test_one_failing_service_keeps_the_other(fake_zc, monkeypatch):
    fake_zc.taken = {"OSC input._player-000._osc._udp.local."}

    class Picky(FakeZeroconf):
        def register_service(self, info, **kw):
            if info.name.startswith("OSC output"):
                raise OSError("no route")
            super().register_service(info, **kw)

    monkeypatch.setattr(mdns, "Zeroconf", Picky)
    advert = mdns.advertise([("_osc._udp.local.", "OSC input._player-000", 4000),
                             ("_osc._udp.local.", "OSC output._player-000", 4001)],
                            lambda *a: None)
    assert advert.names() == ["OSC input._player-000-2._osc._udp.local."]


def test_no_network_only_logs(fake_zc, monkeypatch):
    def no_iface():
        raise OSError("No such device")
    monkeypatch.setattr(mdns, "Zeroconf", no_iface)
    logs = []
    assert mdns.advertise([(HTTP, "HPlayer2._player-000", 80)], lambda *a: logs.append(a)) is None
    assert any("not advertising" in str(line) for line in logs)


def test_withdraw_is_bounded(fake_zc):
    hang = threading.Event()
    advert = mdns.advertise([(HTTP, "HPlayer2._player-000", 80)], lambda *a: None)
    advert.zc.unregister_service = lambda info: hang.wait(30)
    t0 = time.monotonic()
    mdns.withdraw(advert, timeout=0.2)
    assert time.monotonic() - t0 < 2
    hang.set()


# ---- the interfaces: listen() must reach its server whatever zeroconf does -----------------

def _run_listen(iface):
    """Start iface.listen() in a thread the way BaseInterface does; it must still be serving
    after half a second (before the fix it died on the first line)."""
    errors = []

    def target():
        try:
            iface.listen()
        except BaseException as e:            # the bug: the thread dies here
            errors.append(e)

    iface.stopped = threading.Event()
    t = threading.Thread(target=target, daemon=True)
    t.start()
    time.sleep(0.5)
    return t, errors


def _stop(iface, t):
    iface.stopped.set()
    t.join(5)
    assert not t.is_alive()


@pytest.fixture(params=["taken", "broken"])
def hostile_zc(request, fake_zc):
    if request.param == "taken":
        fake_zc.taken = {"HPlayer2._player-000." + HTTP,
                         "HPlayer2._player-000._api-http._tcp.local.",
                         "OSC input._player-000._osc._udp.local."}
    else:
        fake_zc.fail_with = zeroconf.NonUniqueNameException()
    return fake_zc


def test_http2_web_interface_starts_when_the_name_is_taken(hostile_zc, monkeypatch):
    http2 = pytest.importorskip("core.interfaces.http2")
    entered = []

    class Server:
        def __init__(self, iface, port):
            self.port = port

        def __enter__(self):
            entered.append(self.port)
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(http2, "ThreadedHTTPServer", Server)
    monkeypatch.setattr(http2, "get_hostname", lambda: "player-000")
    iface = http2.Http2Interface.__new__(http2.Http2Interface)
    iface._port = 80
    logs = []
    iface.log = lambda *a: logs.append(a)

    t, errors = _run_listen(iface)
    assert errors == []
    assert entered == [80]                              # the web server came up
    assert ("web interface on port", 80) in logs
    _stop(iface, t)


def test_http_api_answers_when_the_name_is_taken(hostile_zc, monkeypatch):
    http = pytest.importorskip("core.interfaces.http")
    servers = []

    class Server(http.ThreadedHTTPServer):
        def __init__(self, port, handler):
            super().__init__(0, handler)                  # a free port, the real HTTPServer
            servers.append(self)

    monkeypatch.setattr(http, "ThreadedHTTPServer", Server)
    monkeypatch.setattr(http, "get_hostname", lambda: "player-000")
    iface = http.HttpInterface.__new__(http.HttpInterface)
    iface._port = 8037
    iface.log = lambda *a: None

    t, errors = _run_listen(iface)
    assert errors == []
    port = servers[0].server.server_address[1]
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
    assert b"HPlayer2 API endpoint" in body
    _stop(iface, t)


def test_osc_input_serves_when_the_name_is_taken(hostile_zc, monkeypatch):
    osc = pytest.importorskip("core.interfaces.osc")
    if not osc.OSC_DEPENDENCIES_AVAILABLE:
        pytest.skip("python-osc missing")
    monkeypatch.setattr(osc, "get_hostname", lambda: "player-000")
    iface = osc.OscInterface.__new__(osc.OscInterface)
    iface._portIn, iface._portOut, iface.hostOut = 0, 0, "127.0.0.1"
    iface.log = lambda *a: None

    t, errors = _run_listen(iface)
    assert errors == []
    assert t.is_alive()                                  # serving, not dead on registration
    _stop(iface, t)


# ---- the real library, two instances on this host ------------------------------------------

def test_real_zeroconf_renames_the_second_player(monkeypatch):
    """The fake above mirrors python-zeroconf; this checks it against the real one. Needs
    multicast looped back on this host: without it both register unchallenged → skip."""
    monkeypatch.setattr(mdns, "get_allip", lambda: ["127.0.0.1"])
    monkeypatch.setattr(mdns, "get_hostname", lambda: "player-t109")
    monkeypatch.setattr(mdns, "Zeroconf",
                        lambda: zeroconf.Zeroconf(ip_version=zeroconf.IPVersion.V4Only))
    first = second = None
    try:
        first = mdns.advertise([(HTTP, "HPlayer2._player-t109", 80)], lambda *a: None)
        if first is None:
            pytest.skip("zeroconf cannot start on this host")
        time.sleep(0.5)
        second = mdns.advertise([(HTTP, "HPlayer2._player-t109", 80)], lambda *a: None)
        assert second is not None
        if second.names() == first.names():
            pytest.skip("no multicast loopback here: the two never saw each other")
        assert second.names() == ["HPlayer2._player-t109-2." + HTTP]
    finally:
        mdns.withdraw(second)
        mdns.withdraw(first)
