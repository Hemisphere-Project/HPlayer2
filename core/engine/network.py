from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
import netifaces as ni

def get_ip(iface=None):
    ip = '127.0.0.1'
    if iface:
        try:
            ip = ni.ifaddresses(iface)[AF_INET][0]['addr']
        except:
            pass
        return ip
    else:
        ifaces = ni.interfaces()
        for iface in ifaces:
            if iface.startswith("e"):
                try:
                    ip = ni.ifaddresses(iface)[AF_INET][0]['addr']
                except:
                    pass
        if ip != '127.0.0.1':
            return ip
        else:
            for iface in ifaces:
                if iface.startswith("w"):
                    try:
                        ip = ni.ifaddresses(iface)[AF_INET][0]['addr']
                    except:
                        pass
    return ip


def get_broadcast(iface=None):
    ip = '127.0.0.1'
    if iface:
        try:
            ip = ni.ifaddresses(iface)[AF_INET][0]['broadcast']
        except:
            pass
        return ip
    else:
        ifaces = ni.interfaces()
        for iface in ifaces:
            if iface.startswith("e"):
                try:
                    ip = ni.ifaddresses(iface)[AF_INET][0]['broadcast']
                except:
                    pass
        if ip != '127.0.0.1':
            return ip
        else:
            for iface in ifaces:
                if iface.startswith("w"):
                    try:
                        ip = ni.ifaddresses(iface)[AF_INET][0]['broadcast']
                    except:
                        pass
    return ip
