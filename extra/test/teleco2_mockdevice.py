#!/usr/bin/env python3
"""
Mock CoreS3 remote for the teleco2 interface (protocol v1) — stdlib only.

Plays the DEVICE side over a pty:
    socat -d pty,raw,echo=0,link=/tmp/hp2r-host pty,raw,echo=0,link=/tmp/hp2r-dev &
    python3 extra/test/teleco2_mockdevice.py [/tmp/hp2r-dev]

or as a fw 6 remote on WiFi (hplayer2#t-090, player profile with netport=3740):
    python3 extra/test/teleco2_mockdevice.py --find [BCAST]        # UDP 3739 probe, list the "here"s
    python3 extra/test/teleco2_mockdevice.py --tcp HOST[:3740]     # session: hello 1 6 MOCK, hb 1 s

Prints every NDJSON message received from the host, and lets you type device
commands on stdin:  prev | next | playpause | stop | playindex N | volup |
voldown | hello | getall  (empty line re-prints the local state summary)
"""

import sys, os, json, select, time, socket

PORT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/hp2r-dev'
PROBE_PORT, NET_PORT = 3739, 3740
CHIP = 'MOCK%04X' % (os.getpid() & 0xffff)

state = {'list': {}, 'listgen': None, 'peers': {}, 'lastRx': 0}


def show(msg):
    t = msg.get('t', '?')
    if t == 'list':
        if msg['g'] != state['listgen']:
            state['listgen'] = msg['g']
            state['list'] = {}
        for k, name in enumerate(msg['items']):
            state['list'][msg['i'] + k] = name
        print(f"<< list  g={msg['g']} total={msg['n']} chunk@{msg['i']} ({len(state['list'])} loaded)")
    elif t == 'peers':
        for p in msg['items']:
            state['peers'][p['nm']] = p
        print(f"<< peers n={msg['n']} chunk@{msg['i']} " +
              " ".join(f"{p['nm']}{'*' if p.get('me') else ''}:lk{p['lk']}" for p in msg['items']))
    elif t == 'st':
        pl = ['STOP', 'PLAY', 'PAUSE'][msg['pl']]
        print(f"<< st    {pl} [{msg['i']+1}/{msg['n']}] {msg['med']!r} {msg['pos']}/{msg['dur']}s")
    else:
        print(f"<< {t:5} {json.dumps({k: v for k, v in msg.items() if k != 't'})}")


def find(bcast='255.255.255.255', wait=1.0):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    u.settimeout(0.2)
    u.sendto(f"find 1 6 {CHIP}".encode(), (bcast, PROBE_PORT))
    t0, heres = time.time(), []
    while time.time() - t0 < wait:
        try:
            d, addr = u.recvfrom(512)
        except socket.timeout:
            continue
        try:
            h = json.loads(d.decode())
        except ValueError:
            continue
        heres.append((addr[0], h))
        print(f"<< here  {addr[0]:15} {h.get('nm', '?'):12} port={h.get('port')} lead={h.get('lead')} rssi={h.get('rssi')} fw={h.get('fw')}")
    print(f"-- {len(heres)} player(s) answered")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--find':
        return find(sys.argv[2] if len(sys.argv) > 2 else '255.255.255.255')
    tcp = None
    if len(sys.argv) > 2 and sys.argv[1] == '--tcp':
        host, _, port = sys.argv[2].partition(':')
        tcp = socket.create_connection((host, int(port or NET_PORT)), timeout=3)
        tcp.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        tcp.settimeout(None)
        fd = tcp.fileno()
        print(f"mock fw 6 remote {CHIP} on tcp {host}:{port or NET_PORT} — commands as below, + bat <pct> <chg>")
        os.write(fd, f"hello 1 6 {CHIP}\n".encode())
    else:
        fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY)
        print(f"mock device on {PORT} — type commands (prev/next/playpause/stop/playindex N/volup/voldown/getall)")
        os.write(fd, b"hello 1\n")
    lastHb = time.time()
    stdinOpen = True

    buf = b''
    while True:
        r, _, _ = select.select([fd] + ([sys.stdin] if stdinOpen else []), [], [], 0.25)

        if fd in r:
            data = os.read(fd, 4096)
            if not data:
                print("EOF, host gone"); break
            buf += data
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                line = line.strip()
                if not line:
                    continue
                if len(line) > 512:
                    print(f"!! oversize line ({len(line)}B) — protocol violation")
                state['lastRx'] = time.time()
                try:
                    show(json.loads(line))
                except ValueError:
                    print(f"!! not json: {line[:80]!r}")

        if sys.stdin in r:
            raw = sys.stdin.readline()
            if not raw:
                stdinOpen = False           # stdin closed (piped script ended): keep the link alive
                continue
            cmd = raw.strip()
            if cmd:
                os.write(fd, (cmd + '\n').encode())
                print(f">> {cmd}")
            else:
                age = time.time() - state['lastRx'] if state['lastRx'] else -1
                print(f"-- state: {len(state['list'])} media, {len(state['peers'])} peers, last rx {age:.1f}s ago")

        if tcp and time.time() - lastHb >= 1.0:          # fw 6 heartbeat
            lastHb = time.time()
            os.write(fd, b"hb\n")

        stale = 3 if tcp else 8
        if state['lastRx'] and time.time() - state['lastRx'] > stale:
            print(f"!! STALE (>{stale}s without host line) — firmware would grey the UI now")
            state['lastRx'] = 0


if __name__ == '__main__':
    main()
