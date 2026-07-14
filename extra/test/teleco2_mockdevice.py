#!/usr/bin/env python3
"""
Mock CoreS3 remote for the teleco2 interface (protocol v1) — stdlib only.

Plays the DEVICE side over a pty:
    socat -d pty,raw,echo=0,link=/tmp/hp2r-host pty,raw,echo=0,link=/tmp/hp2r-dev &
    python3 extra/test/teleco2_mockdevice.py [/tmp/hp2r-dev]

Prints every NDJSON message received from the host, and lets you type device
commands on stdin:  prev | next | playpause | stop | playindex N | volup |
voldown | hello | getall  (empty line re-prints the local state summary)
"""

import sys, os, json, select, time

PORT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/hp2r-dev'

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


def main():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY)
    print(f"mock device on {PORT} — type commands (prev/next/playpause/stop/playindex N/volup/voldown/getall)")
    os.write(fd, b"hello 1\n")

    buf = b''
    while True:
        r, _, _ = select.select([fd, sys.stdin], [], [], 1.0)

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
            cmd = sys.stdin.readline().strip()
            if cmd:
                os.write(fd, (cmd + '\n').encode())
                print(f">> {cmd}")
            else:
                age = time.time() - state['lastRx'] if state['lastRx'] else -1
                print(f"-- state: {len(state['list'])} media, {len(state['peers'])} peers, last rx {age:.1f}s ago")

        if state['lastRx'] and time.time() - state['lastRx'] > 8:
            print("!! STALE (>8s without host line) — firmware would grey the UI now")
            state['lastRx'] = 0


if __name__ == '__main__':
    main()
