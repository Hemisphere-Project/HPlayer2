from .base import BaseInterface
from termcolor import colored
import threading
import socket
import json
import time
import os

#
#  HEALTH: watch a synced player's process, zyre and wallclock, and heal it by itself
#
#  Why (KOUAGOU, 2026-09-18..25): every sync failure so far was a process that stayed up but
#  stopped doing its job — a TimeClient that never came back (60 h unsynced), a master whose
#  clock went silent while mpv kept playing (5 h), a slave deaf to a live master. systemd only
#  restarts a process that EXITS. This interface looks at what the process DOES, climbs a ladder
#  (cheap repairs first), and as the last rung exits at the film's loop point so systemd
#  (Restart=always) brings back a clean app with a blink nobody sees mid-shot.
#
#  Ladder, per condition (thresholds below):
#    thread starvation (`can't start new thread` anywhere)  -> restart at the loop boundary
#    thread count over budget                               -> restart at the loop boundary
#    zyre: no peer at all for 10 min                         -> rebuild the node (every 10 min)
#    slave: master heard playing, not locked for 10 min      -> restart at the loop boundary
#    master: mpv plays, no clock sent for 60 s                -> restart at mpv's loop point
#    zyre node actor died                                     -> rebuilt in place by zyre itself
#    slave: master silent 10 min while its zyre peer lives   -> rebuild zyre (never a restart:
#                                        the slave chases its model of the master meanwhile)
#  Restart budget: 3 per rolling hour, 10 per day, kept in /run (survives our own restart).
#

STATE = '/run/hplayer2-health.json'

# ── thread-starvation guard: count every `can't start new thread`, whoever hit it ──────────
_starved = {'count': 0, 'last': 0.0}
_origStart = threading.Thread.start


def _guardedStart(self, *a, **k):
    try:
        return _origStart(self, *a, **k)
    except RuntimeError as e:
        if "can't start new thread" in str(e):
            _starved['count'] += 1
            _starved['last'] = time.time()
        raise


if getattr(threading.Thread.start, '__name__', '') != '_guardedStart':
    threading.Thread.start = _guardedStart


def mpv_get(path, props, timeout=0.5):
    """Read mpv properties on a FRESH IPC connection — independent of the player's own view of
    mpv, which is what froze on Kouagou01-64 (2026-09-25 01:26: HPlayer2 logged `stopped` at a
    loop point, mpv kept playing, the clock stopped)."""
    out = {}
    if not path:
        return out
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        f = s.makefile('rb')
        for i, prop in enumerate(props):
            s.sendall(json.dumps({"command": ["get_property", prop], "request_id": 3700 + i}).encode() + b"\n")
            while True:
                o = json.loads(f.readline())
                if o.get('request_id') == 3700 + i:
                    out[prop] = o.get('data') if o.get('error') == 'success' else None
                    break
    except (OSError, ValueError):
        pass
    finally:
        try:
            s.close()
        except OSError:
            pass
    return out


def thread_count():
    try:
        return len(os.listdir('/proc/self/task'))
    except OSError:
        return threading.active_count()


def sd_notify(msg):
    addr = os.environ.get('NOTIFY_SOCKET')
    if not addr:
        return
    if addr.startswith('@'):
        addr = '\0' + addr[1:]
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.connect(addr)
        s.sendall(msg.encode())
        s.close()
    except OSError:
        pass


class HealthInterface (BaseInterface):

    TICK = 5.0
    THREAD_MAX = 120                # 27 on a healthy biennale player
    NOPEER_REBUILD = 600.0
    UNLOCKED_RESTART = 600.0
    CLOCK_SILENT_RESTART = 60.0
    MPV_CHECK_EVERY = 30.0
    SILENT_REPAIR = 600.0
    SUMMARY_EVERY = 600.0
    RESTARTS_PER_HOUR = 3
    RESTARTS_PER_DAY = 10
    BOUNDARY_MAX_WAIT = 1200.0      # never wait longer than this for a loop point

    def __init__(self, hplayer, restart=True):
        super().__init__(hplayer, "HEALTH")
        self.restartAllowed = restart
        self.startedAt = time.time()
        self._pending = None            # (reason, requestedAt)
        self._starvedSeen = 0
        self._noPeerSince = None
        self._lastNodeRebuild = 0.0
        self._silentRepaired = False
        self._lastSummary = time.time()
        self._flapMark = (0, time.time())
        self._budgetNoted = 0.0
        self._mpvLast = None            # (time-pos, when) of the previous master check

    # ── helpers ────────────────────────────────────────────────────────────────────────
    def _player(self):
        ps = self.hplayer.players()
        return ps[0] if ps else None

    def _node(self):
        z = self.hplayer.interface('zyre')
        return getattr(z, 'node', None) if z else None

    def _loadState(self):
        try:
            with open(STATE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {'restarts': []}

    def _saveState(self, st):
        try:
            tmp = STATE + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(st, f)
            os.replace(tmp, STATE)
        except OSError:
            pass

    def _budgetOk(self):
        now = time.time()
        r = [t for t in self._loadState().get('restarts', []) if now - t < 86400]
        return (sum(1 for t in r if now - t < 3600) < self.RESTARTS_PER_HOUR
                and len(r) < self.RESTARTS_PER_DAY)

    def requestRestart(self, reason):
        """Exit at the next loop point (systemd restarts us). Idempotent; first reason wins."""
        if not self.restartAllowed or self._pending:
            return
        if not self._budgetOk():
            if time.time() - self._budgetNoted > 600:
                self._budgetNoted = time.time()
                self.log(colored('would restart (' + reason + ') but the restart budget is spent: staying up', 'red'))
            return
        self._pending = (reason, time.time())
        self.log(colored('restart scheduled at the next loop point: ' + reason, 'yellow'))

    def _atBoundary(self):
        p = self._player()
        # mpv's own position first: the player's view may be the frozen part
        m = mpv_get(getattr(p, '_mpv_socketpath', None), ('time-pos', 'duration', 'core-idle')) if p else {}
        if m.get('time-pos') is not None and m.get('duration'):
            if m.get('core-idle'):
                return True
            pos, dur = float(m['time-pos']), float(m['duration'])
            return dur <= 3 or pos >= dur - 0.6
        if not p or not p.isPlaying():
            return True
        try:
            pos = float(p.position() or 0)
        except (TypeError, ValueError):
            pos = 0.0
        try:
            dur = float(p.status('duration') or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if dur <= 3:
            return True
        return pos >= dur - 0.6

    def _doRestart(self, reason):
        st = self._loadState()
        now = time.time()
        st['restarts'] = [t for t in st.get('restarts', []) if now - t < 86400] + [now]
        st['last'] = {'at': now, 'reason': reason}
        self._saveState(st)
        self.log(colored('RESTARTING HPlayer2 (systemd brings it back): ' + reason, 'red'))
        self.hplayer.request_shutdown(exit_code=1, force_delay=10.0)

    def _rebuildZyre(self, why):
        z = self.hplayer.interface('zyre')
        if z and hasattr(z, 'requestRebuild'):
            self._lastNodeRebuild = time.time()
            self.log('asking zyre to rebuild its node:', why)
            z.requestRebuild('health: ' + why)

    # ── checks ─────────────────────────────────────────────────────────────────────────
    def _check(self):
        now = time.time()
        up = now - self.startedAt

        # 1. thread starvation / budget
        if _starved['count'] > self._starvedSeen:
            n = _starved['count'] - self._starvedSeen
            self._starvedSeen = _starved['count']
            self.log(colored("thread starvation: %d `can't start new thread` (threads now %d)" % (n, thread_count()), 'red'))
            self.requestRestart('thread starvation')
        tc = thread_count()
        if tc > self.THREAD_MAX:
            self.requestRestart('%d threads (budget %d)' % (tc, self.THREAD_MAX))

        # 2. zyre isolation
        node = self._node()
        peers = []
        if node:
            try:
                me = getattr(node, 'uuid', None)
                peers = [p for k, p in list(node.book.items()) if k != me and p.active]
            except Exception:
                peers = []
            if peers:
                self._noPeerSince = None
            elif self._noPeerSince is None:
                self._noPeerSince = now
            elif now - self._noPeerSince > self.NOPEER_REBUILD and now - self._lastNodeRebuild > self.NOPEER_REBUILD:
                self._rebuildZyre('no peer for %d min' % ((now - self._noPeerSince) // 60))

        # 3. wallclock
        wc = self.hplayer.interface('wallclock')
        if wc and up > 60:
            if getattr(wc, 'master', False):
                # mpv plays but no clock left for 60 s: the player's view of mpv is stuck
                if now - wc.hLastClockSend > self.CLOCK_SILENT_RESTART and \
                        (self._mpvLast is None or now - self._mpvLast[1] >= self.MPV_CHECK_EVERY):
                    m = mpv_get(getattr(self._player(), '_mpv_socketpath', None), ('time-pos', 'core-idle'))
                    pos = m.get('time-pos')
                    last = self._mpvLast
                    self._mpvLast = (pos, now)
                    if pos is not None and not m.get('core-idle') and last and last[0] is not None and pos != last[0]:
                        self.requestRestart('mpv plays but no clock sent for %d s' % (now - wc.hLastClockSend))
            else:
                heard = now - wc.hLastAccept < 10
                wantLock = heard and wc.hMasterPlaying and not getattr(wc, '_noMedia', 0) \
                    and not getattr(wc, '_holdEnd', False) and now - getattr(wc, 'hMismatch', 0) > 30
                unlocked = now - max(wc.hLastLocked, self.startedAt)
                if wantLock and unlocked > self.UNLOCKED_RESTART:
                    self.requestRestart('master heard playing, not locked for %d min' % (unlocked // 60))

                # Master unheard: repair the cheap parts, NEVER restart — the slave is chasing its
                # model of the master through the outage, and a restarted slave has no model.
                silent = now - max(wc.hLastAccept, self.startedAt)
                masterPeer = wc._lockedName and node and node.peerByName(wc._lockedName)
                if masterPeer and silent > self.SILENT_REPAIR:
                    if not self._silentRepaired:
                        self._silentRepaired = True
                        self._rebuildZyre('master %s alive on zyre, its clock unheard for %d min' % (wc._lockedName, silent // 60))
                elif silent < 60:
                    self._silentRepaired = False

        # 4. summary (one line per 10 min: what an audit greps first)
        if now - self._lastSummary >= self.SUMMARY_EVERY:
            self._lastSummary = now
            fl = ''
            if node:
                ev = node.enters + node.exits
                last, at = self._flapMark
                fl = ' zyre-flaps=%d/%dmin' % (max(0, ev - last), (now - at) // 60)
                self._flapMark = (ev, now)
            w = ''
            if wc:
                if getattr(wc, 'master', False):
                    w = ' clock-sent=%ds-ago' % (now - wc.hLastSend)
                else:
                    w = ' heard=%ds-ago locked=%ds-ago cs=%s' % (now - wc.hLastAccept, now - wc.hLastLocked, wc.hCsSource)
            self.log('summary: threads=%d peers=%d starved=%d%s%s' % (tc, len(peers), _starved['count'], fl, w))

    # ── loop ───────────────────────────────────────────────────────────────────────────
    def listen(self):
        last = self._loadState().get('last')
        if last and time.time() - last.get('at', 0) < 3600:
            self.log('previous self-restart %d s ago: %s' % (time.time() - last['at'], last.get('reason')))
        self.log('watching (threads %d)' % thread_count())
        wd = os.environ.get('WATCHDOG_USEC')
        nextCheck = 0.0
        while not self.stopped.is_set():
            now = time.time()
            if now >= nextCheck:
                nextCheck = now + self.TICK
                try:
                    self._check()
                except Exception as e:
                    self.log('check error:', e)
                if wd:
                    sd_notify('WATCHDOG=1')
            if self._pending:
                reason, at = self._pending
                if self._atBoundary() or now - at > self.BOUNDARY_MAX_WAIT:
                    self._doRestart(reason)
                    self._pending = None
                    self.stopped.wait(15)
                    continue
                self.stopped.wait(0.1)
            else:
                self.stopped.wait(1.0)
