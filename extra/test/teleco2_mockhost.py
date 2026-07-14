#!/usr/bin/env python3
"""
Mock HPlayer2 host for the teleco2 CoreS3 firmware (protocol v1) — needs pyserial.

Run from a laptop/dev machine with the CoreS3 plugged in:
    python3 extra/test/teleco2_mockhost.py              # grep "HPlayer2|303a:1001"
    python3 extra/test/teleco2_mockhost.py /dev/ttyACM0 # or a literal port / pty

Serves a scripted full dump then live state: st ticks 2Hz with advancing position,
net every 2s, peers flapping every 10s, playlist regenerated every 60s.
Reacts to device commands (prev/next/playpause/stop/playindex/volup/voldown).
Press ENTER to toggle a 10s freeze (exercises the device stale banner + recovery).
"""

import sys, json, time, select

import serial
from serial.tools import list_ports

PROTO = 1
MEDIAS = ["01_intro", "02_dance_loop", "03_interlude", "04_finale", "05_credits_stop"] \
       + [f"{i:02d}_extra_track_with_a_longer_name" for i in range(6, 26)]
PEERS = [f"anna-{i:02d}" for i in range(1, 13)]


class Host:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=.1)
        self.pl, self.i, self.pos, self.vol, self.gen = 0, 0, 0, 80, 1
        self.links = {p: 3 for p in PEERS}

    def send(self, obj):
        line = json.dumps(obj, separators=(',', ':'))
        assert len(line) <= 512, f"oversize line: {len(line)}B"
        self.ser.write((line + '\n').encode())

    def st(self):
        self.send({'t': 'st', 'pl': self.pl, 'med': MEDIAS[self.i] if self.pl else '',
                   'i': self.i, 'n': len(MEDIAS), 'pos': self.pos, 'dur': 180})

    def volmsg(self):
        self.send({'t': 'vol', 'v': self.vol, 'mute': 0, 'loop': -1})

    def net(self):
        self.send({'t': 'net', 'ssid': 'Pi-sync', 'rssi': 70 + (int(time.time()) % 3) * 5,
                   'ip': '10.0.0.12'})

    def plist(self):
        for o in range(0, len(MEDIAS), 8):
            self.send({'t': 'list', 'g': self.gen, 'n': len(MEDIAS), 'i': o,
                       'items': MEDIAS[o:o + 8]})

    def peers(self):
        items = [{'nm': 'anna-00', 'lk': 3, 'me': 1}] + \
                [{'nm': p, 'lk': lk, 'me': 0} for p, lk in self.links.items()]
        for o in range(0, len(items), 6):
            self.send({'t': 'peers', 'n': len(items), 'i': o, 'items': items[o:o + 6]})

    def dump(self):
        self.send({'t': 'hello', 'proto': PROTO, 'name': 'mock-host', 'ip': '10.0.0.12'})
        self.volmsg()
        self.st()
        self.net()
        self.plist()
        self.peers()
        print("-- full dump sent")

    def on_cmd(self, line):
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]
        print(f"<< {line}")
        if cmd in ('hello', 'getall'):
            self.dump()
        elif cmd == 'prev':
            self.i = (self.i - 1) % len(MEDIAS); self.pos = 0; self.pl = 1; self.st()
        elif cmd == 'next':
            self.i = (self.i + 1) % len(MEDIAS); self.pos = 0; self.pl = 1; self.st()
        elif cmd == 'playindex' and args:
            self.i = int(args[0]) % len(MEDIAS); self.pos = 0; self.pl = 1; self.st()
        elif cmd == 'playpause':
            self.pl = {0: 1, 1: 2, 2: 1}[self.pl]; self.st()
        elif cmd == 'stop':
            self.pl = 0; self.pos = 0; self.st()
        elif cmd == 'volup':
            self.vol = min(100, self.vol + 1); self.volmsg()
        elif cmd == 'voldown':
            self.vol = max(0, self.vol - 1); self.volmsg()


def find_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    dev = next(list_ports.grep("HPlayer2|303a:1001"), None)
    if not dev:
        sys.exit("no device matching 'HPlayer2|303a:1001' — pass a port explicitly")
    return dev.device


def main():
    host = Host(find_port())
    print(f"mock host on {host.ser.port} — ENTER toggles a 10s freeze (stale test)")
    host.dump()

    last_st = last_net = last_flap = time.time()
    frozen_until = 0
    buf = b''

    while True:
        now = time.time()

        if now < frozen_until:
            time.sleep(0.1)
            continue

        data = host.ser.read(256)
        if data:
            buf += data
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                if line.strip():
                    host.on_cmd(line.decode(errors='replace').strip())

        if now - last_st >= 0.5:
            last_st = now
            if host.pl == 1:
                host.pos = (host.pos + 1) % 180
            host.st()
        if now - last_net >= 2.0:
            last_net = now
            host.net()
        if now - last_flap >= 10.0:
            last_flap = now
            victim = PEERS[int(now) % len(PEERS)]
            host.links[victim] = {3: 1, 1: 3, 2: 3}[host.links[victim]]
            host.peers()
            print(f"-- peer {victim} link -> {host.links[victim]}")

        if select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
            frozen_until = time.time() + 10
            print("-- FROZEN 10s (device should show stale banner, then recover)")


if __name__ == '__main__':
    main()
