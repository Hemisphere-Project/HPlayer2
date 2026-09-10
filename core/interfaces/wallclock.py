from .base import BaseInterface
from ..engine import network
from ..engine.drifter import Drifter
from termcolor import colored
import socket
import json
import time
import os
import re

PRECISION = 1000000     # us - same clock base as the zyre TimeClient


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
#
class WallclockInterface (BaseInterface):

    def __init__(self, hplayer, netiface=None, master=False, player=None,
                    port=3737, group='239.192.0.37', rate=20, unicast=False,
                    masterName=None, staleness=1.0, extrapolate=4.0,
                    driftLog='/data/var/wallclock-drift.csv', durTolerance=1.0):

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
        self.driftLog = driftLog
        # A different file of the SAME duration (± s) is a legitimate timeline to chase:
        # one content per screen, all cut to one length (the LEA fleet, 2026-09-10).
        self.durTolerance = durTolerance
        self._diffNoted = set()

        self._myName = network.get_hostname()

        # Player to track / drive
        players = hplayer.players()
        self.player = player if player else (players[0] if players else None)

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
            self._lastQuiet = {}
            self._ring = []
            self._lastSummary = time.time()
            self._csvFile = None
            # Cue following (numbered media): the master's NN_ prefix is the cue, every
            # slave plays its OWN NN_ file — the wired twin of the Nowde CC#100 contract.
            self._followIdx = 0         # cue currently followed (0 = master plays un-numbered media)
            self._noMedia = 0           # cue we have no file for (stay stopped until it changes)
            self._holdEnd = False       # our file is shorter: ended, waiting for the master to loop/change
            self._myDur = 0.0           # duration of our current cue file (kept while stopped)
            self._sameDur = True        # our file and the master's share one length (seamless loop ok)
            self._loopApplied = None    # last loop mode we pushed to the player (None = profile's choice)
            self._cueStartedAt = 0.0    # when we last started a cue (a start is not a stall for 3 s)
            self._legacyStalled = None  # the profile's stall hook, restored when leaving cue mode

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

    #
    # Cue following (slave): numbered media, one file per cue per player
    #

    def oneLoop(self):
        """Should mpv loop our file seamlessly? Yes unless we follow a cue whose master
        file has another length: then our file must END (shorter: stop and wait for the
        master; longer: the master's wrap seeks us back) instead of wrapping on its own."""
        return self._followIdx == 0 or self._sameDur

    def _startCue(self, idx, why):
        pattern = index_pattern(idx)
        files = self.hplayer.files.listFiles(pattern)
        if not files:
            if self._noMedia != idx:
                self._noMedia = idx
                self.log(colored('cue %d: no %s media here -> stopped, waiting for another cue' % (idx, pattern), 'yellow'))
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

        extraBase = None    # (pos, atLocal, dur, seq, cs) of the last chase-eligible packet

        while not self.stopped.is_set():

            # Staleness: master silent beyond the extrapolation budget ->
            # freewheel at speed 1.0, keep listening
            now = time.time()
            if self._lockedName and now - self._lastAccept > self.extrapolate:
                if not self._freewheeling:
                    self._freewheeling = True
                    extraBase = None
                    if self.drifter:
                        self.drifter.release()
                    self.log(colored('master clock silent (' + self._lockedName + ') : freewheeling', 'yellow'))
                # another master heard consistently while ours is silent -> switch
                if self._candName and now - self._candSince > 1.0 and now - self._candLast < self.staleness:
                    self.log(colored('switching wall clock master: ' + self._lockedName + ' -> ' + self._candName, 'red'))
                    self._lockOn(self._candName)

            try:
                data, addr = sock.recvfrom(1500)
            except socket.timeout:
                # Delivery gap: keep servoing on the extrapolated clock
                # until the freewheel budget runs out.
                if extraBase and self.drifter and not self._freewheeling \
                        and time.time() - self._lastAccept > 0.2:
                    bpos, batLocal, bdur, bseq, bcs, bwrap = extraBase
                    clock = bpos + (time.time() * PRECISION - batLocal) / PRECISION
                    if bdur > 3:
                        clock = clock % bdur
                    if self._followIdx and not self._sameDur and self._myDur > 3 and clock >= self._myDur - 0.05:
                        continue                # past our shorter file: the packet path holds us
                    res = self.drifter.tick(clock, bwrap)
                    if res:
                        res['seq'] = bseq
                        res['cs'] = bcs
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

            # Seq: drop reordered/stale packets (wrap window accepts a restarted master)
            s = pkt.get('s', 0)
            if self._lastSeq is not None:
                behind = (self._lastSeq - s) & 0xffffffff
                if 0 < behind < 1000:
                    continue
            self._lastSeq = s

            self._lastAccept = time.time()
            extraBase = None    # re-set below only if this packet is chase-eligible
            if self._freewheeling:
                self._freewheeling = False
                self.log('master clock is back:', name)
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
                self.drifter.release()
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
                    self.drifter.release()
                    continue

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
            cs = peer.clockshift()
            atLocal = pkt.get('at', 0) - cs
            clock = pkt.get('pos', 0.0) + (time.time() * PRECISION - atLocal) / PRECISION
            if mdur > 3:
                clock = clock % mdur

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
                    self.drifter.release()
                    continue
                if self.player.isPlaying() and mydur > 3:
                    self._myDur = mydur
                if self._myDur > 3:
                    self._sameDur = bool(mdur > 3 and abs(self._myDur - mdur) <= self.durTolerance)
                    if self._sameDur != self._loopApplied and self.player.isPlaying():
                        self.player._applyOneLoop(self._sameDur)     # lengths differ: our file must end
                        self._loopApplied = self._sameDur
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
                        self._quietLog('media mismatch: master plays ' + m + ' / self plays ' + mine + ' -> not chasing')
                        self.drifter.release()
                        continue
                wrapDur = mdur

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
