"""
Conduite desk test: pure-function DMX cue evaluation (core/engine/conduite.py).

No hardware, no player, no serial. Exercises the text parser, channel/alias
addressing, value scales, snap vs fade interpolation, per-channel fade override,
hold-until-next semantics and error reporting.

    python3 tests/desk_conduite.py
"""
import sys, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core.engine.conduite import Conduite

_fails = []


def check(name, got, want):
    ok = got == want
    print(('  ok  ' if ok else ' FAIL ') + name + ('' if ok else '  got=%r want=%r' % (got, want)))
    if not ok:
        _fails.append(name)


def approx(name, got, want, tol=1):
    ok = abs(got - want) <= tol
    print(('  ok  ' if ok else ' FAIL ') + name + ('' if ok else '  got=%r want=%r' % (got, want)))
    if not ok:
        _fails.append(name)


print("\n[1] snap, hold, blackout")
c = Conduite("""
0:00  1@0
0:03  1@255
0:10  1@0
""")
check("t=1 before snap holds 0", c.level(1, 1), 0)
check("t=3 snaps to 255", c.level(1, 3), 255)
check("t=7 holds 255", c.level(1, 7), 255)
check("t=10 back to 0", c.level(1, 10), 0)
check("untouched channel is 0", c.level(2, 7), 0)

print("\n[2] fade interpolation (start at cue, arrive at cue+fade)")
c = Conduite("0:00 1@0\n0:10 1@100 fade 10")
check("t=10 fade just started = from-value", c.level(1, 10), 0)
approx("t=15 halfway", c.level(1, 15), 50)
check("t=20 fade complete", c.level(1, 20), 100)
check("t=25 holds target", c.level(1, 25), 100)

print("\n[3] aliases, ranges, lists")
c = Conduite("""
def wash 1-4
def spots 6,8
0:00 wash@255 spots@128
""")
check("range ch1", c.level(1, 1), 255)
check("range ch4", c.level(4, 1), 255)
check("range ch5 untouched", c.level(5, 1), 0)
check("list ch6", c.level(6, 1), 128)
check("list ch8", c.level(8, 1), 128)
check("active channels", c.activeChannels(), [1, 2, 3, 4, 6, 8])

print("\n[4] value scales: raw + percent")
c = Conduite("0:00 1@50%  2@255  3@0%")
check("50% -> 128", c.level(1, 0), 128)
check("raw 255", c.level(2, 0), 255)
check("0% -> 0", c.level(3, 0), 0)

print("\n[5] per-channel fade override within one cue")
c = Conduite("0:00 1@0 2@0\n0:00 1@100/10 2@100")   # ch1 fades over 10s, ch2 snaps
# second cue at t=0: ch1 from 0 over 10s, ch2 instant
approx("ch1 mid-fade at t=5", c.level(1, 5), 50)
check("ch2 snapped", c.level(2, 0), 100)

print("\n[6] time formats")
c = Conduite("90 1@10\n1:30 2@20\n0:01:30 3@30")
check("bare seconds 90", c.level(1, 90), 10)
check("m:ss 1:30 == 90s", c.level(2, 90), 20)
check("h:m:s 0:01:30 == 90s", c.level(3, 90), 30)

print("\n[7] frame() builds a full universe")
c = Conduite("0:00 1@255 512@128")
fr = c.frame(0)
check("frame length", len(fr), 512)
check("frame ch1", fr[0], 255)
check("frame ch512", fr[511], 128)

print("\n[8] errors are collected, good lines still parse")
c = Conduite("""
0:00 1@255
0:03 bogusline
0:05 999@10
0:07 2@50
""")
check("2 errors reported", len(c.errors), 2)
check("good cue before error still works", c.level(1, 1), 255)
check("good cue after error still works", c.level(2, 8), 50)

print("\n" + ("ALL PASS" if not _fails else "FAILURES: " + ", ".join(_fails)))
sys.exit(1 if _fails else 0)
