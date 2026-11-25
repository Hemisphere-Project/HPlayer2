"""mDNS (zeroconf) advertising that never takes its interface down.

Two players with one hostname on one LAN (two generic cards booted before they are named, or two
cards stamped with one name) announce the same service instance. python-zeroconf then raises
NonUniqueNameException from register_service. http2, http and osc registered inside their listen
thread with nothing around it, so the thread died there: the second player had no web interface
and no OSC input (hplayer2#t-109, seen 25/11 on the rig with two player-000 cards).

Advertising is a convenience. The service itself must come up whatever happens here:
  - a taken name is renamed by zeroconf (« HPlayer2._player-000 » → « HPlayer2._player-000-2 »)
    and the new name is logged;
  - any other failure (no zeroconf, no interface, a busy mdns stack) is logged, nothing raises.
"""
import importlib
import socket
import threading

from .network import get_allip, get_hostname

ServiceInfo = None
Zeroconf = None
try:
    _zeroconf = importlib.import_module("zeroconf")
    ServiceInfo = getattr(_zeroconf, "ServiceInfo", None)
    Zeroconf = getattr(_zeroconf, "Zeroconf", None)
except ImportError:
    pass


def available():
    return ServiceInfo is not None and Zeroconf is not None


class Advert(object):
    """One Zeroconf instance and the services it actually registered."""

    def __init__(self, zc):
        self.zc = zc
        self.infos = []

    def names(self):
        return [info.name for info in self.infos]


def advertise(services, log=print):
    """Register each (service_type, instance, port) on mDNS, e.g.
    ("_http._tcp.local.", "HPlayer2._player-000", 80).

    Returns an Advert holding what got registered (hand it to withdraw() at shutdown), or None
    when nothing did. Never raises.
    """
    if not available():
        return None
    try:
        hostname = get_hostname()
        addresses = [socket.inet_aton(ip) for ip in get_allip()]
        zc = Zeroconf()
    except Exception as e:
        log("zeroconf: not advertising —", repr(e))
        return None

    advert = Advert(zc)
    for stype, instance, port in services:
        wanted = instance + "." + stype
        try:
            info = ServiceInfo(
                stype,
                wanted,
                addresses=addresses,
                port=port,
                properties={},
                server=hostname + ".local.",
            )
            zc.register_service(info, allow_name_change=True)
        except Exception as e:
            log("zeroconf: could not advertise", wanted, "—", repr(e))
            continue
        if info.name != wanted:
            log("zeroconf: name taken on the LAN, advertised as", info.name, "instead of", wanted)
        advert.infos.append(info)

    if not advert.infos:
        _close(zc)
        return None
    return advert


def withdraw(advert, timeout=3.0):
    """Unregister and close, bounded: unregister/close can hang on a busy mdns stack, and the
    listen threads are non-daemon (a hang there held the whole process until systemd's 90 s
    SIGKILL)."""
    if advert is None:
        return

    def _bye():
        for info in advert.infos:
            try:
                advert.zc.unregister_service(info)
            except Exception:
                pass
        _close(advert.zc)

    t = threading.Thread(target=_bye, daemon=True)
    t.start()
    t.join(timeout)


def _close(zc):
    try:
        zc.close()
    except Exception:
        pass
