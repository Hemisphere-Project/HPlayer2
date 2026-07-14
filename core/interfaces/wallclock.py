from .base import BaseInterface
from ..engine import network
from ..engine.chaser import Chaser
from termcolor import colored
import socket
import json
import time
import os

PRECISION = 1000000     # us - same clock base as the zyre TimeClient

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
#  Slaves chase the estimated master position with the Chaser speed servo.
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
#
class WallclockInterface (BaseInterface):

    def __init__(self, hplayer, netiface=None, master=False, player=None,
                    port=3737, group='239.192.0.37', rate=20, unicast=False,
                    masterName=None, staleness=1.0,
                    driftLog='/data/var/wallclock-drift.csv'):

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
        self.driftLog = driftLog

        self._myName = network.get_hostname()

        # Player to track / drive
        players = hplayer.players()
        self.player = player if player else (players[0] if players else None)

        if self.master:
            self.chaser = None
            # Latch (pos, at) pairs from the player status events; the send
            # loop reads the latch at its own rate. No extrapolation here:
            # raw samples out, slaves extrapolate. Single-reference tuple:
            # written by the event thread, read by the send loop.
            self._latch = None
            if self.player:
                self.hplayer.on(self.player.name + '.status')(self._onPlayerStatus)
        else:
            self.chaser = Chaser(self.player, log=self.log) if self.player else None
            self._lockedName = None
            self._lastSeq = None
            self._lastAccept = 0
            self._freewheeling = False
            self._candName = None
            self._candSince = 0
            self._candLast = 0
            self._csClient = None
            self._csReady = False
            self._lastQuiet = {}
            self._ring = []
            self._lastSummary = time.time()
            self._csvFile = None

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
        ip = network.get_ip(self.iface) if self.iface else network.get_ip()
        if ip and ip != '127.0.0.1':
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
            except OSError:
                self.log('could not pin multicast egress to', self.iface)

        dest = 'unicast to zyre peers' if self.unicast else self.group
        self.log('master clock: emitting on', dest, 'port', self.port, 'at', self.rate, 'Hz')

        interval = 1.0 / self.rate
        seq = 0

        while not self.stopped.is_set():
            self.stopped.wait(interval)

            latch = self._latch
            # player silent (stopped / paused): latch goes stale, stop emitting
            if latch is None or (time.time() * PRECISION - latch[1]) > PRECISION:
                continue
            pos, at = latch

            media = self.player.status('media')
            dur = self.player.status('duration')
            pkt = {
                'v': 1,
                'n': self._myName,
                's': seq,
                'at': at,
                'pos': pos,
                'dur': round(float(dur), 2) if dur else 0,
                'm': os.path.basename(media) if media else '',
                'p': bool(self.player.isPlaying())
            }
            data = json.dumps(pkt).encode()

            try:
                if self.unicast:
                    for pip in self._peerIps():
                        sock.sendto(data, (pip, self.port))
                else:
                    sock.sendto(data, (self.group, self.port))
                seq = (seq + 1) & 0xffffffff
            except OSError as e:
                self.log('send error:', e)

        sock.close()

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
        if self.chaser:
            self.chaser.arm()
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

        if self._csvFile:
            try:
                self._csvFile.write('%d,%d,%.1f,%.2f,%d,%d,%d\n' % (
                    int(time.time() * 1000), res['seq'], res['diff'] * 1000,
                    res['speed'], res['locked'], res['jumped'], res['cs']))
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
            self.log('drift 60s:',
                        'p50=' + str(round(p50, 1)) + 'ms',
                        'p95=' + str(round(p95, 1)) + 'ms',
                        'max=' + str(round(diffs[-1], 1)) + 'ms',
                        'locked=' + str(round(locked)) + '%',
                        'jumps=' + str(jumps))
            self._ring = []

    def _runSlave(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.port))
        ip = network.get_ip(self.iface) if self.iface else network.get_ip()
        try:
            bindIp = ip if ip and ip != '127.0.0.1' else '0.0.0.0'
            mreq = socket.inet_aton(self.group) + socket.inet_aton(bindIp)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError as e:
            self.log('multicast join failed (unicast mode still works):', e)
        sock.settimeout(0.25)

        self._openCsv()
        self.log('slave: chasing wall clock on port', self.port)

        while not self.stopped.is_set():

            # Staleness: master silent -> freewheel at speed 1.0, keep listening
            now = time.time()
            if self._lockedName and now - self._lastAccept > self.staleness:
                if not self._freewheeling:
                    self._freewheeling = True
                    if self.chaser:
                        self.chaser.release()
                    self.log(colored('master clock silent (' + self._lockedName + ') : freewheeling', 'yellow'))
                # another master heard consistently while ours is silent -> switch
                if self._candName and now - self._candSince > 1.0 and now - self._candLast < self.staleness:
                    self.log(colored('switching wall clock master: ' + self._lockedName + ' -> ' + self._candName, 'red'))
                    self._lockOn(self._candName)

            try:
                data, addr = sock.recvfrom(1500)
            except socket.timeout:
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

            # Seq: drop reordered/stale packets (wrap window accepts a restarted master)
            s = pkt.get('s', 0)
            if self._lastSeq is not None:
                behind = (self._lastSeq - s) & 0xffffffff
                if 0 < behind < 1000:
                    continue
            self._lastSeq = s

            self._lastAccept = time.time()
            if self._freewheeling:
                self._freewheeling = False
                self.log('master clock is back:', name)
            self._candName = None

            if not self.chaser:
                continue

            # Clockshift readiness: the zyre TimeClient needs its first
            # sampling round against the master peer (~2-8s after JOIN).
            # Once latched, keep using it: refresh rounds retain the last
            # good clockshift value while resampling.
            peer = self._zyrePeer(name)
            if not peer:
                self._quietLog('waiting for zyre discovery of ' + name)
                self.chaser.release()
                continue
            tc = getattr(peer, 'timeclient', None)
            if tc is not self._csClient:
                self._csClient = tc
                self._csReady = False
            if not self._csReady:
                if tc and getattr(tc, 'status', 0) == 1:
                    self._csReady = True
                    self.log('clock sync ready with', name, '( shift ' + str(peer.clockshift()) + 'us )')
                else:
                    self._quietLog('waiting for clock sync with ' + name)
                    self.chaser.release()
                    continue

            # Master not playing
            if not pkt.get('p', False):
                self.chaser.release()
                continue

            # Media mismatch guard: never chase file A's clock on file B's timeline
            m = pkt.get('m') or ''
            if m and self.player:
                mine = self.player.status('media')
                mine = os.path.basename(mine) if mine else ''
                if mine and mine != m:
                    self._quietLog('media mismatch: master plays ' + m + ' / self plays ' + mine + ' -> not chasing')
                    self.chaser.release()
                    continue

            # Estimate master position at local now:
            # packet timestamp -> local clock (zyre clockshift), then extrapolate.
            # Delivery delay/jitter cancels out by construction.
            cs = peer.clockshift()
            atLocal = pkt.get('at', 0) - cs
            clock = pkt.get('pos', 0.0) + (time.time() * PRECISION - atLocal) / PRECISION
            dur = pkt.get('dur', 0) or 0
            if dur > 3:
                clock = clock % dur

            res = self.chaser.tick(clock, dur)
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
