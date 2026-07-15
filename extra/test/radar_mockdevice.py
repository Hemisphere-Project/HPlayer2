#!/usr/bin/env python3
"""
Mock LD2450 radar box for the `radar` interface (core/interfaces/radar.py) — stdlib only.

Plays the DEVICE side over a pty — exactly what extra/arduino/radar_ld2450 would send:

    socat -d pty,raw,echo=0,link=/tmp/hp2-radar-host pty,raw,echo=0,link=/tmp/hp2-radar-dev &
    python3 extra/test/radar_mockdevice.py [/tmp/hp2-radar-dev]
    ./hplayer2 radartest                    (in another terminal)

Streams one "T x,y,v" line per frame at ~10 Hz. By default it walks a target through a
repeating IN -> linger -> OUT -> gap cycle so you can watch radar.enter / radar.leave.
Type on stdin to override the walk:
    in            target enters   (200,1000,-10)
    out           zone empty
    x,y,v         custom target   (mm,mm,cm/s)
    auto          resume the automatic walk
    q             quit
"""
import sys, os, select, time

PORT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/hp2-radar-dev'
RATE = 0.1   # 10 Hz, like the LD2450

# automatic walk: (label, seconds, line)
WALK = [
    ("empty",    3, "T"),
    ("ENTER",    5, "T 200,1000,-10"),   # inside the default gate
    ("linger",   4, "T 150,1100,0"),     # still present -> must NOT re-trigger
    ("leave",    4, "T"),                # zone empty
    ("far",      3, "T 100,5000,-8"),    # beyond default range -> reads as empty
    ("RE-ENTER", 5, "T -300,900,6"),     # back inside the gate
]


def main():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY)
    os.write(fd, b"hello 1\n")
    print(f"mock radar on {PORT} — auto walk; type in/out/x,y,v/auto/q")

    override = None
    phase = 0
    phase_end = time.time() + WALK[0][1]
    print(f"-- phase: {WALK[0][0]}")
    nxt = time.time()

    while True:
        r, _, _ = select.select([sys.stdin], [], [], max(0.0, nxt - time.time()))
        if sys.stdin in r:
            cmd = sys.stdin.readline().strip()
            if cmd == 'q':
                break
            elif cmd == 'auto':
                override = None; print("-- auto")
            elif cmd == 'in':
                override = "T 200,1000,-10"; print(">> in")
            elif cmd == 'out':
                override = "T"; print(">> out")
            elif cmd:
                override = "T " + cmd; print(">> " + override)

        now = time.time()
        if now >= nxt:
            nxt += RATE
            if override is None:
                if now >= phase_end:
                    phase = (phase + 1) % len(WALK)
                    phase_end = now + WALK[phase][1]
                    print(f"-- phase: {WALK[phase][0]}")
                line = WALK[phase][2]
            else:
                line = override
            try:
                os.write(fd, (line + "\n").encode())
            except OSError:
                print("host gone"); break


if __name__ == '__main__':
    main()
