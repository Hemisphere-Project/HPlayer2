from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
import netifaces as ni
import subprocess

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

def get_allip():
    ip = []
    ifaces = ni.interfaces()
    for iface in ifaces:
        if iface.startswith("e"):
            try:
                ip.append(ni.ifaddresses(iface)[AF_INET][0]['addr'])
            except:
                pass
    else:
        for iface in ifaces:
            if iface.startswith("w"):
                try:
                    ip.append(ni.ifaddresses(iface)[AF_INET][0]['addr'])
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

def get_hostname():
    import socket
    return socket.gethostname()

def get_ethmac():
    mac = None
    ifaces = ni.interfaces()
    for iface in ifaces:
        if iface.startswith("e"):
            try:
                mac = ni.ifaddresses(iface)[AF_INET][0]['addr']
            except:
                pass
    return mac


def get_essid(iface):
    return subprocess.check_output("iw "+iface+" link | grep SSID: | awk '{print $2}'", shell=True).decode('ascii').strip()

def get_rssi(iface):
    rssi = int(subprocess.check_output("iw "+iface+" link | grep signal: | awk '{print $2}'", shell=True))
    minVal = -85
    maxVal = -45
    return round(max(0, (rssi-minVal)*100/(maxVal-minVal)))

