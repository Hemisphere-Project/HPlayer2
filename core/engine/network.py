try:
    from netifaces import AF_INET, AF_LINK, AF_PACKET
except ImportError:  # pragma: no cover - fallback for platforms without AF_PACKET
    from netifaces import AF_INET, AF_LINK

    AF_PACKET = AF_LINK
import netifaces as ni
import subprocess
import shutil

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
    for iface in ni.interfaces():
        if not iface.startswith("e"):
            continue
        try:
            addresses = ni.ifaddresses(iface)
        except ValueError:
            continue
        for family in (AF_LINK, AF_PACKET):
            if family in addresses and addresses[family]:
                candidate = addresses[family][0].get('addr')
                if candidate:
                    return candidate
    return mac


def get_essid(iface):
    if shutil.which("iw") is None:
        return ""
    try:
        command = [
            "iw",
            iface,
            "link",
        ]
        output = subprocess.check_output(command, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    for line in output.decode('ascii', errors='ignore').splitlines():
        if "SSID:" in line:
            return line.split("SSID:", 1)[-1].strip()
    return ""

def get_rssi(iface):
    if shutil.which("iw") is None:
        return None
    try:
        command = [
            "iw",
            iface,
            "link",
        ]
        output = subprocess.check_output(command, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    rssi = None
    for line in output.decode('ascii', errors='ignore').splitlines():
        if "signal:" in line:
            try:
                rssi = int(line.split("signal:", 1)[-1].split()[0])
            except (ValueError, IndexError):
                return None
            break
    else:
        return None

    if rssi is None:
        return None

    minVal = -85
    maxVal = -40
    return round(max(0, (rssi-minVal)*100/(maxVal-minVal)))

def has_interface(iface):
    return iface in ni.interfaces()