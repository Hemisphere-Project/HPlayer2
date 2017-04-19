from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
import netifaces as ni

def get_ip(iface):
    ip = '127.0.0.1'
    try:
        ip = ni.ifaddresses(iface)[AF_INET][0]['addr']
    except:
        pass
    return ip

def get_broadcast(iface):
    ip = '127.0.0.1'
    try:
        ip = ni.ifaddresses(iface)[AF_INET][0]['broadcast']
    except:
        pass
    return ip
