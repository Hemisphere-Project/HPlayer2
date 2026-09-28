from .base import BaseInterface
from ..engine import network
from ..engine.drifter import Drifter
from termcolor import colored
import socket
import json
import time
import os
import re
from collections import deque

PRECISION = 1000000     # us - same clock base as the zyre TimeClient


class PacketClock():
    """Master-minus-local clock offset measured from the clock packets alone — the fallback
    when zyre has no usable clockshift (no peer, a TimeClient that cannot finish a round on a
    lossy link: kouagou03 chased nothing for 1.5 h on 2026-09-25 while hearing every packet).

    Each packet gives tx - recv = offset - delivery delay. The packet that crossed fastest in a
    sliding window carries the least delay, so the window's MAX of (tx - recv) estimates the
    offset minus the minimum one-way latency (~1-3 ms on the sync LAN; wifi power-save buffering
    only ever ADDS delay, the max filter drops it). One max per 1 s bucket, 30 buckets."""

    def __init__(self, window=30, minBuckets=3, latency_us=1500):
        self.window = window
        self.minBuckets = minBuckets
        self.latency = latency_us
        self.buckets = deque()      # [second, max(tx - recv)]

    def add(self, tx_us, recv_us):
        v = tx_us - recv_us
        if self.buckets and abs(v - max(b[1] for b in self.buckets)) > PRECISION:
            self.buckets.clear()    # the master's clock jumped (reboot, clock set): start over
        sec = int(recv_us // PRECISION)
        self._fold(self.buckets, sec, v)
        while self.buckets and self.buckets[0][0] <= sec - self.window:
            self.buckets.popleft()

    @staticmethod
    def _fold(series, key, v):
        # max per key; a key older than the newest (an out-of-order stamp) folds into its own slot
        if series and series[-1][0] == key:
            if v > series[-1][1]:
                series[-1][1] = v
        elif not series or key > series[-1][0]:
            series.append([key, v])
        else:
            for slot in reversed(series):
                if slot[0] == key:
                    if v > slot[1]:
                        slot[1] = v
                    break

    def reset(self):
        self.buckets.clear()

    def ready(self):
        return len(self.buckets) >= self.minBuckets

    def shift(self):
        return max(b[1] for b in self.buckets) + self.latency


def subnet_broadcast(iface, ip):
    """The sync subnet's broadcast address. A hotspot configured without `brd` (Kouagou01-64:
    `10.1.0.1/24`, 2026-09-25) reports its own address as broadcast: derive it from the netmask."""
    if not ip or ip.startswith('127.'):
        return None
    try:
        import netifaces, ipaddress
        a = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]
        b = a.get('broadcast')
        if b and b != ip and not b.startswith('127.'):
            return b
        mask = a.get('netmask') or '255.255.255.0'
        return str(ipaddress.IPv4Network(ip + '/' + mask, strict=False).broadcast_address)
    except Exception:
        return ip.rsplit('.', 1)[0] + '.255'


def media_index_of(path):
    """Numeric prefix of a media file name (01_xxx.mp4 -> 1), 0 when un-numbered.
    Same contract as the Nowde line (core/interfaces/nowde.py): the INDEX is the cue."""
    if not path:
        return 0
    m = re.match(r'^0*(\d{1,3})_', os.path.basename(str(path)))
    if not m:
        return 0
    n = int(m.group(1))
    return n if 1 <= n <= 127 else 0


def index_pattern(idx):
    """Glob alternation matching every zero-padding of a cue index (7 -> 007_*|07_*|7_*)."""
    if idx < 10:
        return "(00%d_*|0%d_*|%d_*)" % (idx, idx, idx)
    if idx < 100:
        return "(0%d_*|%d_*)" % (idx, idx)
    return "%d_*" % idx

#
#  WALLCLOCK: continuous position sync for synchronized video walls
#
#  One master, N slaves. The master emits its playback position on a
#  dedicated loss-permissive UDP socket (multicast by default, unicast
#  fan-out to zyre peers as fallback): a late clock packet must be
#  DROPPED, not queued, so the reliable zyre/ZeroMQ data plane is the
#  wrong pipe for it. Zyre stays in the picture for peer discovery and
#  clock correction: each packet timestamp is converted to local time
#  with the zyre-measured peer clockshift, then extrapolated to 'now' -
#  so network delivery delay/jitter never enters the position estimate.
#  Slaves chase the estimated master position with the Drifter speed servo.
#
#  Packet (JSON, ~140 bytes):
#    v    protocol version (1)
#    n    master hostname (= zyre peer name, clockshift lookup key)
#    s    seq, uint32 wrapping (reject reordered packets)
#    at   us epoch (time.time()*1e6) when 'pos' was true
#    pos  master player position (s)
#    dur  media duration (s), 0 if unknown
#    m    master media basename (mismatch guard)
#    p    master isPlaying
#    l    master loops seamlessly (1) or through its playlist (0)
#    tx   us epoch (master clock) when the packet was SENT — the packet-derived clock offset
#         (PacketClock) reads it; absent from masters before 2026-09-25
#
#  Transport (2026-09-25): the master sends every packet to the multicast group AND to the
#  sync subnet's broadcast address. Broadcast needs no membership, so no lost-IGMP-state,
#  20-membership cap or re-join loop can deafen a slave; multicast stays for older slaves.
#  Slaves drop the duplicate by seq. A STOPPED master sends a 1 Hz heartbeat (p=0): its slaves
#  stop chasing. Silence means "link or master trouble": slaves chase their model of it.
#
class WallclockInterface (BaseInterface):

    def __init__(self, hplayer, netiface=None, master=False, player=None,
                    port=3737, group='239.192.0.37', rate=20, unicast=False,
                    masterName=None, staleness=1.0, extrapolate=4.0, modelMax=6 * 3600,
                    driftLog='/tmp/wallclock-drift.csv', durTolerance=1.0):

        super().__init__(hplayer, "WALLCLOCK")
        self.logQuietEvents.extend(['drift'])

        self.iface = netiface
        self.master = master
        self.port = port
        self.group = group
        self.rate = rate
        self.unicast = unicast
        self.masterName = masterName        # accept only this master (None = lock on first heard)
        self.staleness = staleness
        # RF gap bridging (s): packets carry (pos, at) so the clock estimate
        # is pure extrapolation anyway — keep servoing from the last good
        # packet through short delivery gaps (wifi bursts) instead of going
        # blind; freewheel only when the gap outlives this budget. Master
        # crystal drift over 4s is microseconds — the estimate stays exact.
        self.extrapolate = max(extrapolate, staleness)
        # Link outage (2026-09-25, Thomas: "a bad link must be invisible"): past the extrapolate
        # budget a slave used to release its servo and play at speed 1.0 — it drifted at once (two
        # Pis never play at the same rate: kouagou03 needed 0.993) and hard-seeked when the clock
        # came back. It now keeps chasing its MODEL of the master (last packet + elapsed, wrapped
        # at the loop) for up to modelMax, and rejoins with a speed trim.
        self.modelMax = modelMax
        self.driftLog = driftLog
        # A different file of the SAME duration (± s) is a legitimate timeline to chase:
        # one content per screen, all cut to one length (the LEA fleet, 2026-09-10).
        self.durTolerance = durTolerance
        self._diffNoted = set()

        self._myName = network.get_hostname()

        # Player to track / drive
        players = hplayer.players()
        self.player = player if player else (players[0] if players else None)

        # Loop ownership (2026-09-10): the master says in every packet whether it loops its
        # file seamlessly in mpv (one file, no end gap) or hands the loop to the playlist
        # (several cues, or a loop-gap); slaves mirror it so nobody wraps on its own.
        self.seamless = True            # master: set by the profile; slave: last value heard
        self._masterSeamless = True

        # Health view (read by the health interface): plain attributes, written by this thread
        self.hLastSend = 0.0            # master: last packet sent (clock or heartbeat)
        self.hLastClockSend = 0.0       # master: last packet carrying a live position
        self.hLastAccept = 0.0          # slave: last packet accepted from our master
        self.hMasterPlaying = False     # slave: last packet said the master plays
        self.hLastLocked = 0.0          # slave: last servo tick inside the lock window
        self.hCsSource = None           # slave: 'zyre' | 'packets'
        self.hMismatch = 0.0            # slave: last time the master's media was not ours to chase

        if self.master:
            self.drifter = None
            # Latch (pos, at) pairs from the player status events; the send
            # loop reads the latch at its own rate. No extrapolation here:
            # raw samples out, slaves extrapolate. Single-reference tuple:
            # written by the event thread, read by the send loop.
            self._latch = None
            if self.player:
                self.hplayer.on(self.player.name + '.status')(self._onPlayerStatus)
        else:
            # danceMode: joining slaves seek-ahead + pause + timed-resume
            # instead of chaining blind jumps (113s -> ~10s join, 2026-07-23)
            self.drifter = Drifter(self.player, log=self.log, danceMode=True) if self.player else None
            self._lockedName = None
            self._lastSeq = None
            self._lastAccept = 0
            self._freewheeling = False
            self._candName = None
            self._candSince = 0
            self._candLast = 0
            self._csClient = None
            self._csReady = False
            self._csStuckSince = None   # clock client missing or stalled since (re-arm after 30 s)
            self._lastQuiet = {}
            self._ring = []
            self._lastSummary = time.time()
            self._csvFile = None
            # Cue following (numbered media): the master's NN_ prefix is the cue, every
            # slave plays its OWN NN_ file — the wired twin of the Nowde CC#100 contract.
            self._followIdx = 0         # cue currently followed (0 = master plays un-numbered media)
            self._noMedia = 0           # cue we have no file for (stay stopped, re-check every 5 s)
            self._noMediaAt = 0.0       # last time we looked for that cue's file
            self._holdEnd = False       # our file is shorter: ended, waiting for the master to loop/change
            self._myDur = 0.0           # duration of our current cue file (kept while stopped)
            self._sameDur = True        # our file and the master's share one length (seamless loop ok)
            self._loopApplied = None    # last loop mode we pushed to the player (None = profile's choice)
            self._cueStartedAt = 0.0    # when we last started a cue (a start is not a stall for 3 s)
            self._noPeerSince = None    # master clock heard but no zyre peer since (rebuild request)
            self._pkt = PacketClock()   # fallback clock offset, from the packets themselves
            self._rejoins = 0           # silent-socket re-joins (log throttle)
            self._rejoinLogAt = 0.0
            self._legacyStalled = None  # the profile's stall hook, restored when leaving cue mode

    def _rearmClockSync(self, peer, tc, name):
        # The TimeClient's own Timers are the only thing that ever starts a sampling round; when
        # one cannot start (thread exhaustion) nothing ever would, and this slave waits for a
        # clock sync forever (kouagou03, 60 h from 2026-09-21 23:28). This thread runs on every
        # master packet anyway: after 30 s of a missing or stalled client, re-arm it from here.
        stuck = tc is None or (hasattr(tc, 'stalled') and tc.stalled())
        now = time.time()
        if not stuck:
            self._csStuckSince = None
            return
        if not self._csStuckSince:
            self._csStuckSince = now
            return
        if now - self._csStuckSince < 30.0:
            return
        self._csStuckSince = now
        try:
            if tc is None:
                self.log('no clock client for', name, 'for 30 s -> re-syncing the peer')
                peer.sync()
            else:
                self.log('clock client for', name, 'stalled for 30 s -> re-arming it')
                tc.start()
        except Exception as e:
            self.log('clock re-arm failed (' + str(e) + '): retrying in 30 s')

    def _modelClock(self, base):
        """The master's position now, from the last chase-eligible packet, wrapped at the media
        length. (Two Pi crystals drift ~0.1 s per hour of outage: the rejoin trims it away.)"""
        bpos, batLocal, bdur, bseq, bcs, bwrap = base
        elapsed = (time.time() * PRECISION - batLocal) / PRECISION
        clock = bpos + elapsed
        if bdur > 3:
            clock = clock % bdur
        return clock

    def _pickShift(self, peer):
        """TimeClient first (Thomas, 2026-09-25), the packets as fallback: a missing zyre peer or
        a TimeClient that cannot finish a round (lossy link) no longer stops the chase."""
        tc = getattr(peer, 'timeclient', None) if peer else None
        if tc and getattr(tc, 'status', 0) == 1:
            return tc.clockshift, 'zyre'
        if self._pkt.ready():
            return self._pkt.shift(), 'packets'
        return None, None

    #
    # MASTER side
    #

    def _onPlayerStatus(self, ev, *args):
        if len(args) < 2:
            return
        if args[0] == 'time' and args[1] is not None:
            self._latch = (float(args[1]), int(time.time() * PRECISION))

    def _peerIps(self):
        ips = []
        z = self.hplayer.interface('zyre')
        if z and hasattr(z, 'node'):
            for peer in list(z.node.book.values()):
                if peer.active and peer.ip and peer.ip != '127.0.0.1':
                    ips.append(peer.ip)
        return ips

    def _runMaster(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Pin the multicast egress to the sync interface — and keep trying if that
        # interface has no address yet (same boot race as the slave join below): an
        # unpinned socket sends the clock down the default route, i.e. nowhere useful.
        # The broadcast address is re-read with it (a new lease may bring another subnet).
        pinned = [False]
        lastPin = [0.0]
        bcast = [None]

        def pin():
            ip = network.get_ip(self.iface) if self.iface else network.get_ip()
            lastPin[0] = time.time()
            if self.iface:
                bcast[0] = subnet_broadcast(self.iface, ip)
            if ip and ip != '127.0.0.1':
                try:
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
                    pinned[0] = True
                    return
                except OSError:
                    pass
            if not pinned[0] and lastPin[0] and not getattr(pin, 'noted', False):
                pin.noted = True
                self.log('could not pin multicast egress to', self.iface, '(no address yet): retrying every 2 s')

        pin()

        dest = 'unicast to zyre peers' if self.unicast else (self.group + (' + broadcast ' + bcast[0] if bcast[0] else ''))
        self.log('master clock: emitting on', dest, 'port', self.port, 'at', self.rate, 'Hz')

        interval = 1.0 / self.rate
        seq = 0
        lastBeat = 0.0

        def send(pkt):
            nonlocal seq
            pkt['s'] = seq
            pkt['tx'] = int(time.time() * PRECISION)
            data = json.dumps(pkt).encode()
            ok = False
            try:
                if self.unicast:
                    for pip in self._peerIps():
                        sock.sendto(data, (pip, self.port))
                        ok = True
                else:
                    try:
                        sock.sendto(data, (self.group, self.port))
                        ok = True
                    except OSError as e:
                        self._sendErr('multicast', e)
                    if bcast[0]:
                        try:
                            sock.sendto(data, (bcast[0], self.port))
                            ok = True
                        except OSError as e:
                            self._sendErr('broadcast', e)
            except OSError as e:
                self._sendErr('unicast', e)
            if ok:
                seq = (seq + 1) & 0xffffffff
                self.hLastSend = time.time()
            return ok

        while not self.stopped.is_set():
            self.stopped.wait(interval)

            if time.time() - lastPin[0] > (2.0 if not pinned[0] else 30.0):
                was = pinned[0]
                pin()
                if pinned[0] and not was:
                    self.log('multicast egress pinned to', self.iface, '(late: interface was not up at start)')

            media = self.player.status('media')
            dur = self.player.status('duration')
            base = {
                'v': 1,
                'n': self._myName,
                'dur': round(float(dur), 2) if dur else 0,
                'm': os.path.basename(media) if media else '',
                'l': 1 if self.seamless else 0
            }

            latch = self._latch
            now = time.time()
            fresh = latch is not None and (now * PRECISION - latch[1]) <= PRECISION

            if fresh:
                pos, at = latch
                pkt = dict(base, at=at, pos=pos, p=bool(self.player.isPlaying()))
                if send(pkt):
                    self.hLastClockSend = now
                continue

            # Player status silent. A player that says it is stopped announces it (1 Hz, p=0): the
            # slaves stop chasing. One that says it plays but went quiet sends nothing: the slaves
            # keep chasing their model of it, which is what a viewer should see.
            if not self.player.isPlaying() and now - lastBeat >= 1.0:
                lastBeat = now
                pos = latch[0] if latch else 0.0
                send(dict(base, at=int(now * PRECISION), pos=pos, p=False))

        sock.close()

    def _sendErr(self, what, e):
        k = '_sendErrAt_' + what
        if time.time() - getattr(self, k, 0) > 60:
            setattr(self, k, time.time())
            self.log(what, 'send error:', e)

    #
    # SLAVE side
    #

    # rate-limited log (once per 5s per message)
    def _quietLog(self, msg):
        now = time.time()
        if self._lastQuiet.get(msg, 0) + 5 < now:
            self._lastQuiet[msg] = now
            self.log(msg)

    def _lockOn(self, name):
        self._lockedName = name
        self._lastSeq = None
        self._lastAccept = time.time()
        self._freewheeling = False
        self._candName = None
        self._csClient = None
        self._csReady = False
        self._csStuckSince = None
        self._pkt.reset()
        if self.drifter:
            self.drifter.arm()
        self.log('locked on wall clock master:', name)

    def _zyrePeer(self, name):
        z = self.hplayer.interface('zyre')
        if z and hasattr(z, 'node'):
            return z.node.peerByName(name)
        return None

    def _openCsv(self):
        if not self.driftLog or self._csvFile:
            return
        try:
            header = not os.path.isfile(self.driftLog)
            self._csvFile = open(self.driftLog, 'a', buffering=1)
            if header:
                self._csvFile.write('epoch_ms,seq,diff_ms,speed,locked,jumped,cs_us\n')
        except (OSError, IOError) as e:
            self.log('drift CSV disabled:', e)
            self.driftLog = None
            self._csvFile = None

    def _telemetry(self, res):
        self._ring.append(res)
        if res.get('locked'):
            self.hLastLocked = time.time()

        if self._csvFile:
            try:
                self._csvFile.write('%d,%d,%.1f,%.2f,%d,%d,%d\n' % (
                    int(time.time() * 1000), res['seq'], res['diff'] * 1000,
                    res['speed'], res['locked'], res['jumped'], res['cs']))
                # Cap: one line per clock tick is ~55 kB/min; on /data this grew to 580 MB on
                # kouagou02 in 63 h (2026-09-21) — a permanent random-write load on the SD card.
                # Now on the tmpfs, and rotated at 10 MB (one previous kept).
                self._csvLines = getattr(self, '_csvLines', 0) + 1
                if self._csvLines % 2000 == 0 and os.path.getsize(self.driftLog) > 10 * 1024 * 1024:
                    self._csvFile.close()
                    self._csvFile = None
                    os.replace(self.driftLog, self.driftLog + '.1')
                    self._openCsv()
            except (OSError, IOError):
                self._csvFile = None

        # 60s summary: p50/p95/max |diff|, lock ratio, jumps
        now = time.time()
        if now - self._lastSummary >= 60 and len(self._ring) > 0:
            self._lastSummary = now
            diffs = sorted([abs(r['diff']) * 1000 for r in self._ring])
            n = len(diffs)
            p50 = diffs[n // 2]
            p95 = diffs[min(n - 1, int(n * 0.95))]
            locked = 100 * sum(1 for r in self._ring if r['locked']) / n
            jumps = sum(1 for r in self._ring if r['jumped'])
            model = 100 * sum(1 for r in self._ring if r.get('model')) / n
            self.log('drift 60s:',
                        'p50=' + str(round(p50, 1)) + 'ms',
                        'p95=' + str(round(p95, 1)) + 'ms',
                        'max=' + str(round(diffs[-1], 1)) + 'ms',
                        'locked=' + str(round(locked)) + '%',
                        'jumps=' + str(jumps),
                        'model=' + str(round(model)) + '%')
            self._ring = []

    #
    # Cue following (slave): numbered media, one file per cue per player
    #

    def oneLoop(self):
        """Should mpv loop our file seamlessly? Only if the master does (one file, no loop
        gap — it says so in every packet), and unless we follow a cue whose master file has
        another length: then our file must END (shorter: stop and wait for the master;
        longer: the master's wrap seeks us back) instead of wrapping on its own."""
        return self._masterSeamless and (self._followIdx == 0 or self._sameDur)

    def _startCue(self, idx, why):
        pattern = index_pattern(idx)
        files = self.hplayer.files.listFiles(pattern)
        if not files:
            if self._noMedia != idx:
                self._noMedia = idx
                self.log(colored('cue %d: no %s media here -> stopped, looking again every 5 s' % (idx, pattern), 'yellow'))
            self._noMediaAt = time.time()
            if self.player.isPlaying():
                self.player.stop()
            return False
        self._noMedia = 0
        self.log('cue %d: %s -> playing %s' % (idx, why, os.path.basename(files[0])))
        self._cueStartedAt = time.time()
        self.hplayer.playlist.play(pattern)
        if self.drifter:
            self.drifter.arm()
        return True

    def _indexStalled(self):
        """Drifter stall hook while following a cue: the local file ended (or never
        started) while the master clock runs. Restart it only when the master is inside
        our timeline; a shorter file waits, a missing cue stays dark."""
        if self._holdEnd or self._noMedia:
            return
        if self._followIdx:
            if time.time() - self._cueStartedAt < 3.0:
                return                  # mpv is still bringing the cue up: not a stall
            self._startCue(self._followIdx, 'stalled, master still playing')
        elif self._legacyStalled:
            self._legacyStalled()

    def _runSlave(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.port))
        # Multicast membership on the sync interface. At boot HPlayer2 can start before
        # the interface has its (DHCP) address: the join then fails with ENODEV and, done
        # once, left the slave deaf for good — S02-28-L / S05-28-P came up black after a
        # reboot while zyre (which retries) recovered (LEA, 2026-09-10). Retry until it
        # sticks: a late lease is the normal case on a fleet power-on, where the master's
        # DHCP server boots at the same time as its slaves.
        joined = [False]
        lastTry = [0.0]
        noted = [False]
        lastErr = [None]

        def fresh():
            # A re-join after a driver reload lands on a NEW interface index; the socket keeps one
            # dead membership per reload and the kernel refuses the 21st
            # (net.ipv4.igmp_max_memberships = 20, ENOBUFS — not the EADDRINUSE the old code took
            # for "already joined"). kouagou03 logged exactly 19 re-joins, then sat deaf for two
            # days with the clock reaching its interface (2026-09-21). Re-join on a fresh socket.
            nonlocal sock
            try:
                sock.close()
            except OSError:
                pass
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', self.port))
            sock.settimeout(0.25)

        def join(rebind=False):
            if rebind:
                try:
                    fresh()
                except OSError as e:
                    self.log('multicast socket rebind failed (' + str(e) + ')')
            ip = network.get_ip(self.iface) if self.iface else network.get_ip()
            try:
                bindIp = ip if ip and ip != '127.0.0.1' else '0.0.0.0'
                mreq = socket.inet_aton(self.group) + socket.inet_aton(bindIp)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                joined[0] = True
                if rebind:
                    # every 5 s while the master is silent: log the first few, then once a minute
                    self._rejoins += 1
                    if self._rejoins <= 3 or time.time() - self._rejoinLogAt > 60:
                        self._rejoinLogAt = time.time()
                        self.log('multicast group re-joined on ' + (ip or '0.0.0.0') + ' (fresh socket, #%d)' % self._rejoins)
                elif noted[0]:
                    self.log('multicast group joined on ' + (ip or '0.0.0.0') + ' (late: interface was not up at start)')
                lastErr[0] = None
            except OSError as e:
                err = getattr(e, 'errno', None)
                if err == 98:                                 # EADDRINUSE: membership already present
                    joined[0] = True
                else:
                    if not noted[0] or err != lastErr[0]:     # log the first failure and every change of errno
                        noted[0] = True
                        self.log('multicast join failed (' + str(e) + '): retrying every 2 s')
                    lastErr[0] = err
            lastTry[0] = time.time()

        join()
        sock.settimeout(0.25)

        self._openCsv()
        self.log('slave: chasing wall clock on port', self.port)

        extraBase = None    # (pos, atLocal, dur, seq, cs) of the last chase-eligible packet

        while not self.stopped.is_set():

            if not joined[0] and time.time() - lastTry[0] > 2.0:
                # ENODEV/EADDRNOTAVAIL = the interface is not up yet: retry on the same socket;
                # anything else (ENOBUFS: the membership list is full) needs a fresh one
                join(rebind=lastErr[0] not in (None, 19, 99))

            # Staleness: master silent beyond the extrapolation budget ->
            # freewheel at speed 1.0, keep listening
            now = time.time()
            if self._lockedName and now - self._lastAccept > self.extrapolate:
                onModel = extraBase is not None and now - self._lastAccept < self.modelMax
                if not self._freewheeling:
                    self._freewheeling = True
                    self._silentSince = self._lastAccept
                    if onModel:
                        self._modelCheck = extraBase
                        self.log(colored('master clock silent (' + self._lockedName + ') : chasing its model', 'yellow'))
                    else:
                        extraBase = None
                        if self.drifter:
                            self.drifter.release()
                        self.log(colored('master clock silent (' + self._lockedName + ') : freewheeling', 'yellow'))
                elif extraBase is not None and not onModel:
                    extraBase = None
                    self._modelCheck = None
                    if self.drifter:
                        self.drifter.release()
                    self.log(colored('master silent for %d h: model retired, freewheeling' % (self.modelMax // 3600), 'yellow'))
                # another master heard consistently while ours is silent -> switch
                if self._candName and now - self._candSince > 1.0 and now - self._candLast < self.staleness:
                    self.log(colored('switching wall clock master: ' + self._lockedName + ' -> ' + self._candName, 'red'))
                    self._lockOn(self._candName)

            try:
                data, addr = sock.recvfrom(1500)
            except socket.timeout:
                # Silent for 5 s while we believe we are joined: the membership may be gone (a
                # driver reload or interface re-creation drops IGMP state silently — kouagou03
                # sat unchased for two days with its socket bound and no group, 2026-09-18).
                # Re-join every 5 s; an already-present membership answers EADDRINUSE, harmless.
                if joined[0] and time.time() - lastTry[0] > 5.0 and time.time() - self._lastAccept > 5.0:
                    joined[0] = False
                    join(rebind=True)
                # Delivery gap: keep servoing on the extrapolated clock
                # until the freewheel budget runs out.
                # (only for a player that plays: a slave stopped by the master's zyre 'stop' must not
                # be restarted by its own model)
                if extraBase and self.drifter and time.time() - self._lastAccept > 0.2 \
                        and self.player.isPlaying():
                    bpos, batLocal, bdur, bseq, bcs, bwrap = extraBase
                    clock = self._modelClock(extraBase)
                    if bdur > 3:
                        clock = clock % bdur
                    if self._followIdx and not self._sameDur and self._myDur > 3 and clock >= self._myDur - 0.05:
                        continue                # past our shorter file: the packet path holds us
                    res = self.drifter.tick(clock, bwrap)
                    if res:
                        res['seq'] = bseq
                        res['cs'] = bcs
                        res['model'] = self._freewheeling
                        self._telemetry(res)
                        self.emit('drift', res)
                continue
            except OSError:
                continue

            try:
                pkt = json.loads(data.decode())
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(pkt, dict) or pkt.get('v') != 1:
                continue

            name = pkt.get('n')
            if not name or name == self._myName:
                continue

            # Master lock-on / arbitration
            if self.masterName and name != self.masterName:
                continue
            if not self._lockedName:
                self._lockOn(name)
            elif name != self._lockedName:
                if self._candName != name:
                    self._candName = name
                    self._candSince = time.time()
                self._candLast = time.time()
                self._quietLog('ignoring second wall clock master: ' + name)
                continue

            # Seq: drop reordered/stale packets (wrap window accepts a restarted master) and the
            # duplicate of a packet heard on both multicast and broadcast
            s = pkt.get('s', 0)
            if self._lastSeq is not None:
                behind = (self._lastSeq - s) & 0xffffffff
                # (a master silent for 2 s and back with a low seq restarted: take it at once
                # instead of dropping it until its seq passes ours again)
                if behind < 1000 and time.time() - self._lastAccept < 2.0:
                    continue
            self._lastSeq = s

            self._lastAccept = time.time()
            self.hLastAccept = self._lastAccept
            self.hMasterPlaying = bool(pkt.get('p', False))
            self._rejoins = 0
            self._pkt.add(pkt.get('tx', pkt.get('at', 0)), int(self._lastAccept * PRECISION))
            extraBase = None    # re-set below only if this packet is chase-eligible
            if self._freewheeling:
                self._freewheeling = False
                self._backAfter = time.time() - getattr(self, '_silentSince', time.time())
                if not getattr(self, '_modelCheck', None):
                    self.log('master clock is back:', name, 'after %.0f s' % self._backAfter)
            self._candName = None

            if not self.drifter:
                continue

            # Clockshift readiness: the zyre TimeClient needs its first
            # sampling round against the master peer (~2-8s after JOIN).
            # Once latched, keep using it: refresh rounds retain the last
            # good clockshift value while resampling.
            peer = self._zyrePeer(name)
            if not peer:
                self._quietLog('waiting for zyre discovery of ' + name)
                # The master's clock is heard, so the link is up — only discovery is missing. A master
                # rebooted or swapped under running slaves leaves it that way for good (LACROIX,
                # 2026-09-15): after a minute ask zyre to rebuild its node, and again every minute.
                now = time.time()
                if not self._noPeerSince:
                    self._noPeerSince = now
                elif now - self._noPeerSince > 60.0:
                    self._noPeerSince = now
                    z = self.hplayer.interface('zyre')
                    if z and hasattr(z, 'requestRebuild'):
                        self.log('master clock heard for 60 s without a zyre peer -> asking zyre to rebuild its node')
                        z.requestRebuild('wallclock: ' + name + ' heard for 60 s, no peer')
                # no peer: the packets alone carry a clock (below) — a missing zyre peer no
                # longer means a slave that stops chasing
            else:
                self._noPeerSince = None
                self._rearmClockSync(peer, getattr(peer, 'timeclient', None), name)

            cs, src = self._pickShift(peer)
            if src != self.hCsSource:
                if src:
                    self.log('clock shift from', src, 'for', name, '(' + str(cs) + 'us)')
                self.hCsSource = src
            if cs is None:
                self._quietLog('waiting for clock sync with ' + name)
                self.drifter.release()
                continue

            # Loop ownership announced by the master: mirror it live, so a master that hands
            # its loop to the playlist (several cues, loop gap) never leaves a slave wrapping
            # seamlessly on its own — and the other way round.
            l = bool(pkt.get('l', 1))
            if l != self._masterSeamless:
                self._masterSeamless = l
                self.log('master loops ' + ('seamlessly (mpv)' if l else 'through its playlist') + ' -> mirroring')
                # playlist loop too: under a playlist-owned loop our file must END and stay
                # ended (the master's next play broadcast restarts us), not wrap to index 0
                self.hplayer.settings.set('loop', 2 if l else 0)
                if self.player and self.player.isPlaying():
                    self.player._applyOneLoop(self.oneLoop())
                    self._loopApplied = self.oneLoop()

            # Master not playing
            if not pkt.get('p', False):
                self.drifter.release()
                continue

            m = pkt.get('m') or ''
            mdur = pkt.get('dur', 0) or 0
            midx = media_index_of(m)
            mine = self.player.status('media') if self.player else None
            mine = os.path.basename(mine) if mine else ''
            try:
                mydur = float(self.player.status('duration') or 0) if self.player else 0.0
            except (TypeError, ValueError):
                mydur = 0.0

            # Estimate master position at local now:
            # packet timestamp -> local clock (zyre clockshift), then extrapolate.
            # Delivery delay/jitter cancels out by construction.
            atLocal = pkt.get('at', 0) - cs
            clock = pkt.get('pos', 0.0) + (time.time() * PRECISION - atLocal) / PRECISION
            if mdur > 3:
                clock = clock % mdur
            if getattr(self, '_modelCheck', None):
                # how far the model had drifted over the outage: the number that says "invisible"
                mc = self._modelClock(self._modelCheck)
                err = clock - mc
                if mdur > 3:
                    err = ((err + mdur / 2) % mdur) - mdur / 2
                self.log('master clock is back:', name, 'after %.0f s, model was off by %+.0f ms' % (getattr(self, '_backAfter', 0), err * 1000))
                self._modelCheck = None

            if midx and self.player:
                # ── Cue mode: the master plays NN_ -> we play OUR NN_ file and chase its
                # position. No NN_ here -> stay dark. Ours shorter -> end, hold, wait for
                # the master to loop or move on. Ours longer -> the master's wrap seeks us back.
                if self._followIdx != midx:
                    self._followIdx = midx
                    self._holdEnd = False
                    self._myDur = 0.0
                    self._sameDur = True
                    self._loopApplied = None
                    if self.drifter.onStalled is not self._indexStalled:
                        self._legacyStalled = self.drifter.onStalled
                        self.drifter.onStalled = self._indexStalled
                    if media_index_of(mine) != midx:
                        self._startCue(midx, 'master plays ' + m)
                        continue
                    # already on this cue (boot self-start): let it come up, the stall hook covers a real stall
                if self._noMedia == midx:
                    # Keep looking: media arrives while the cue is playing (an http2 upload
                    # replaces the file — it is absent for a moment, S04-24-P stayed dark
                    # for an hour on 2026-09-10 because only a cue change re-checked).
                    if time.time() - self._noMediaAt > 5.0:
                        self._noMediaAt = time.time()
                        if self._startCue(midx, 'media appeared'):
                            continue
                    self.drifter.release()
                    continue
                if self.player.isPlaying() and mydur > 3:
                    self._myDur = mydur
                if self._myDur > 3:
                    self._sameDur = bool(mdur > 3 and abs(self._myDur - mdur) <= self.durTolerance)
                    want = self.oneLoop()
                    if want != self._loopApplied and self.player.isPlaying():
                        self.player._applyOneLoop(want)      # lengths differ / master not seamless: our file must end
                        self._loopApplied = want
                    if not self._sameDur and clock >= self._myDur - 0.05:
                        if not self._holdEnd:
                            self._holdEnd = True
                            self.log('cue %d: our file ends at %.1fs, master is at %.1fs -> stopped, waiting for it' % (midx, self._myDur, clock))
                            if self.player.isPlaying():
                                self.player.stop()
                        self.drifter.release()
                        continue
                    if self._holdEnd:
                        self._holdEnd = False
                        self._startCue(midx, 'master back inside our file (%.1fs)' % clock)
                        continue
                if self.player.isPlaying() and media_index_of(mine) != midx:
                    self._startCue(midx, 'own playlist moved to ' + mine)
                    continue
                wrapDur = mdur if self._sameDur else 0      # wrap-aware diff only on one shared length
            else:
                # ── Un-numbered master media: same file, or a different file of the same
                # length (one content per screen, same cut), is a timeline we chase; a file
                # of another length is not (never chase file A's clock on file B's timeline).
                if self._followIdx:
                    self._followIdx = 0
                    self._holdEnd = False
                    self._noMedia = 0
                    if self.drifter.onStalled is self._indexStalled:
                        self.drifter.onStalled = self._legacyStalled
                if m and mine and mine != m:
                    if mdur > 3 and mydur > 3 and abs(mydur - mdur) <= self.durTolerance:
                        if (m, mine) not in self._diffNoted:       # once per file pair, not every 5 s
                            self._diffNoted.add((m, mine))
                            self.log('media differs (' + m + ' / ' + mine + ') but same duration -> chasing')
                    else:
                        self.hMismatch = time.time()
                        self._quietLog('media mismatch: master plays ' + m + ' / self plays ' + mine + ' -> not chasing')
                        self.drifter.release()
                        continue
                wrapDur = mdur

            # A stopped slave whose master is inside the last 2 s of its file is not stalled:
            # its own file ended a few frames early. Under a playlist-owned loop the master
            # will broadcast the restart (or wrap to a new cue); a self-start here would play
            # the tail of the set alone (TAUPAKI loop-gap bench, 2026-09-10).
            if not self.player.isPlaying() and mdur > 3 and clock > mdur - 2.0:
                self.drifter.release()
                continue

            extraBase = (pkt.get('pos', 0.0), atLocal, mdur, s, cs, wrapDur)   # chase-eligible: gaps extrapolate from here
            res = self.drifter.tick(clock, wrapDur)
            if res:
                res['seq'] = s
                res['cs'] = cs
                self._telemetry(res)
                self.emit('drift', res)

        if self._csvFile:
            self._csvFile.close()
        sock.close()

    #
    # Interface thread
    #

    def listen(self):
        if not self.player:
            self.log('no player to sync: wallclock interface idle')
            self.stopped.wait()
            return

        self.log('interface ready (' + ('master' if self.master else 'slave') + ')')
        if self.master:
            self._runMaster()
        else:
            self._runSlave()
        self.log('done.')
