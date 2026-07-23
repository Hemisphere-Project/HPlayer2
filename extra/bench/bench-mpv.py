#!/usr/bin/env python3
"""mpv seek/speed benchmark — characterize the actuator the drifter drives.

Runs ON the player box with the SAME mpv invocation HPlayer2 uses (flags
passed as argv). For each media: a seek matrix (near/far, ahead/behind,
keyframes vs exact) measuring latency + landing error + hangs, and a
speed matrix measuring apply-latency, achieved rate, and frame drops.
Outputs JSON lines to stdout (prefix BENCH:).
"""
import json, os, socket, subprocess, sys, time

MEDIA_DIR = "/data/bench-media"
SOCK = "/tmp/bench-mpv"
SEEK_DELTAS = [2, 10, 40, -10, -40]
SEEK_MODES = ["keyframes", "exact"]
SPEEDS = [0.5, 0.8, 0.95, 0.99, 1.01, 1.05, 1.2, 1.5, 2.0, 4.0, 8.0]
SEEK_TIMEOUT = 30.0

def log(*a): print(*a, file=sys.stderr, flush=True)

class Mpv:
    def __init__(self, argv):
        if os.path.exists(SOCK): os.unlink(SOCK)
        self.proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if os.path.exists(SOCK): break
            time.sleep(0.1)
        self.s = socket.socket(socket.AF_UNIX); self.s.connect(SOCK)
        self.s.settimeout(0.25)
        self.buf = b""; self.rid = 0
        self.events = []

    def _pump(self, timeout=0.0):
        end = time.monotonic() + timeout
        while True:
            try:
                data = self.s.recv(65536)
                if data: self.buf += data
            except socket.timeout:
                pass
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                try: msg = json.loads(line)
                except ValueError: continue
                if "event" in msg: self.events.append((time.monotonic(), msg))
                else: self.replies.setdefault(msg.get("request_id"), msg)
            if time.monotonic() >= end: return

    replies = {}
    def cmd(self, *args, wait=True):
        self.rid += 1
        self.s.send((json.dumps({"command": list(args), "request_id": self.rid}) + "\n").encode())
        if not wait: return None
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self._pump(0.05)
            if self.rid in self.replies: return self.replies.pop(self.rid)
        return None

    def get(self, prop):
        r = self.cmd("get_property", prop)
        return r.get("data") if r else None

    def wait_event(self, name, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self._pump(0.1)
            for i, (t, e) in enumerate(self.events):
                if e.get("event") == name:
                    self.events = self.events[i+1:]
                    return t
        return None

    def drain(self): self._pump(0.2); self.events = []

    def quit(self):
        try: self.cmd("quit", wait=False)
        except Exception: pass
        try: self.proc.wait(timeout=5)
        except Exception: self.proc.kill()

def bench_media(m, path, host):
    name = os.path.basename(path)
    r = m.cmd("loadfile", path)
    if not m.wait_event("playback-restart", 20):
        print("BENCH:" + json.dumps({"host": host, "media": name, "error": "load failed"}), flush=True)
        return
    time.sleep(2); m.cmd("set_property", "pause", False); m.drain()
    dur = m.get("duration") or 120.0

    # ── seek matrix ──
    for mode in SEEK_MODES:
        for delta in SEEK_DELTAS:
            m.drain()
            pos0 = m.get("time-pos")
            if pos0 is None: continue
            target = (pos0 + delta) % dur
            t0 = time.monotonic()
            m.cmd("seek", str(target), "absolute", mode, wait=False)
            t_land = m.wait_event("playback-restart", SEEK_TIMEOUT)
            lat = (t_land - t0) if t_land else None
            time.sleep(0.15)
            pos1 = m.get("time-pos")
            # subtract playback since landing for the error estimate
            err = None
            if pos1 is not None and t_land:
                played = time.monotonic() - t_land
                err = ((pos1 - played - target + dur / 2) % dur) - dur / 2
            rec = {"host": host, "media": name, "test": "seek", "mode": mode,
                   "delta": delta, "from": round(pos0, 2), "target": round(target, 2),
                   "latency_s": round(lat, 3) if lat else None,
                   "landing_err_s": round(err, 3) if err is not None else None,
                   "hang": lat is None}
            print("BENCH:" + json.dumps(rec), flush=True)
            time.sleep(1.0)

    # ── speed matrix ──
    m.cmd("set_property", "speed", 1.0); time.sleep(1.0)
    for s in SPEEDS:
        m.drain()
        drop0 = m.get("frame-drop-count") or 0
        p0 = m.get("time-pos"); t0 = time.monotonic()
        m.cmd("set_property", "speed", s, wait=False)
        time.sleep(3.0)
        p1 = m.get("time-pos"); t1 = time.monotonic()
        drop1 = m.get("frame-drop-count") or 0
        rate = None
        if p0 is not None and p1 is not None:
            dp = ((p1 - p0 + dur / 2) % dur) - dur / 2
            rate = dp / (t1 - t0)
        rec = {"host": host, "media": name, "test": "speed", "speed": s,
               "achieved": round(rate, 3) if rate is not None else None,
               "ratio": round(rate / s, 3) if rate else None,
               "dropped": drop1 - drop0}
        print("BENCH:" + json.dumps(rec), flush=True)
        m.cmd("set_property", "speed", 1.0); time.sleep(1.0)

def main():
    host = os.uname().nodename
    argv = sys.argv[1:]
    argv = [a for a in argv if not a.startswith(("--input-ipc-server", "--log-file", "--idle"))]
    argv += ["--input-ipc-server=" + SOCK, "--idle=yes", "--loop-file=inf",]
    log("mpv:", argv[0])
    m = Mpv(argv)
    medias = sorted(os.listdir(MEDIA_DIR))
    for f in medias:
        if not f.endswith(".mp4"): continue
        log(">>", f)
        bench_media(m, os.path.join(MEDIA_DIR, f), host)
    m.quit()
    print("BENCH:" + json.dumps({"host": host, "done": True}), flush=True)

if __name__ == "__main__":
    main()
