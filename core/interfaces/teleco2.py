from .serialbase import SerialBase
from core.engine import network

import os
import re
import sys
import json
import time
import socket
import selectors
import threading
import subprocess
import unicodedata

"""
TELECO2 PROTOCOL v1  --  USB remote link (M5Stack CoreS3 firmware: extra/arduino/teleco2_cores3)

Transport: USB CDC serial, 115200 nominal, LF-terminated lines both ways, UTF-8.
Line cap 512 bytes (host truncates strings to guarantee it, device discards oversize to next LF).
Host silently drops unknown RX lines (tolerates ESP32 boot spew), device ignores unknown "t".

HOST -> DEVICE : NDJSON, one object per line, typed by "t"
  {"t":"hello","proto":1,"name":"<hostname>","ip":"..."}        on connect / device hello / getall
  {"t":"st","pl":0|1|2,"med":"<basename>","i":3,"n":12,"pos":42,"dur":180}
        pl: 0 stopped / 1 playing / 2 paused -- pushed max 2Hz, immediate on transitions
        i is -1 when no track is selected
  {"t":"vol","v":80,"mute":0,"loop":-1}                         on settings change
  {"t":"list","g":7,"n":42,"i":0,"items":["track01",...]}       chunks of 8, cap 200 items
        g: generation, device resets its list when g changes    on playlist change
  {"t":"peers","n":13,"i":0,"items":[{"nm":"anna01","lk":3,"me":1},...]}
        lk: zyre link 0 GONE / 1 SILENT / 2 EVASIVE / 3 OK      chunks of 6, coalesced 1s
  {"t":"net","ssid":"Pi-sync","rssi":72,"ip":"..."}             every 2s = keepalive
  {"t":"bye"}                                                   player shutting down

DEVICE -> HOST : plain text  CMD [intarg]
  hello <proto> [fw] on boot + every 3s while no host line for >8s (doubles as dump request)
                     fw: firmware version (absent on fw<=1, parsed as 0)
  getall             request full dump
  prev / next / playpause / stop / playindex <i> / volup / voldown

AUTO-FLASH (policy: any off-version remote is flashed on sight, erasure assumed)
  The repo ships a merged flash image dist/teleco2_cores3-v<N>.bin (see
  extra/arduino/teleco2_cores3/src/version.h for the build recipe). When a device
  hello announces fw != N and esptool is installed, the host closes the link and
  reflashes the remote at 0x0 over the ROM USB-Serial/JTAG CDC (buttonless, survives
  any firmware state), then lets the normal hotplug rescan pick the device back up.
  One attempt per port per session; a failed flash leaves the ROM CDC alive but the
  device silent (no hello) -> replug or flash manually.

Device declares the link stale after 8s without a valid host line (net's 2s cadence = 4 missed).

THE 303a:1001 COLLISION (USB only)
  The default filter matches the generic Espressif ROM-CDC id, which the radar box
  (extra/arduino/radar_ld2450) shares. Under that default the port is only ours once
  the device proves it: a valid command, a hello carrying fw, or a bare `hello 1`
  repeated (the radar box prints one bare `hello 1` on boot -- never flash on that).
  A radar frame line, or no hello within HELLO_WAIT, rejects the port: SerialBase
  re-scans excluding it until it is unplugged. A per-player `teleco2-filter` setting
  (keyed on the USB serial string, SER=<chip MAC>) or a filter passed by the profile
  is trusted instead: no probing, and a silent device gets the dump anyway. A TCP
  session is proven by the protocol (it answered our "here"): never probed.

ADDITIONS for fw >= 6 (additive: a v5 remote never sends them, a v5 player drops them unread)
  hello <proto> <fw> <chipid>   the chip id lets a player drop a TCP session of a remote that is
                                now plugged into its USB (one remote, one transport)
  hb                            heartbeat, every 1 s (TCP; harmless on USB)
  bat <pct> <chg>               battery %, charging 0|1, every 30 s -> the player's log

NETWORK TRANSPORT (hplayer2#t-090, netport=3740): the same protocol v1 lines over TCP, for a
remote on its battery. One selector thread serves both:
  UDP <probeport> (3739)  remote broadcasts  "find <proto> <fw> <chipid>"
                          player answers (unicast) {"t":"here","nm":..,"port":3740,"lead":0|1,
                          "rssi":..,"fw":..}   lead = this player emits the clock (wallclock)
  TCP <netport> (3740)    one Teleco2Session per connection, Nagle off; the host's "net" every
                          1 s is its heartbeat, the remote's "hb" every 1 s is the remote's; a
                          session silent for NET_DEAD s is closed (half-open links)
  No auto-flash over TCP (esptool needs the USB port). Never anything on the wallclock port.
"""

PROTO           = 1

DEFAULT_FILTER  = "HPlayer2|303a:1001"
HELLO_WAIT      = 15        # s, probing: a host-less remote beacons by 8s stale + 3s period
DUMP_WAIT       = 10        # s, a trusted link (explicit filter, or tcp): silence -> dump anyway
RADAR_FRAME     = re.compile(r'T(\s+-?\d+,-?\d+,-?\d+)*$')

MEDIA_MAXLEN    = 48
NAME_MAXLEN     = 16
LIST_MAXITEMS   = 200
LIST_CHUNK      = 8
PEERS_CHUNK     = 6

ST_PERIOD       = 0.5       # min interval between st pushes (2Hz)
PEERS_PERIOD    = 1.0       # coalesce peers table updates
NET_PERIOD      = 2.0       # net poll + keepalive (USB)
NET_PERIOD_TCP  = 1.0       # net poll + heartbeat (TCP): the remote declares it dead at 3 s
NET_DEAD        = 3.5       # TCP session without a line from the remote for this long: closed
NET_OUTMAX      = 65536     # TCP session send backlog cap: a remote that stopped reading is dropped
BAT_LOG_STEP    = 10        # log the remote's battery when it moved this many points


class Teleco2Session():
    """Protocol v1 to ONE remote over ONE transport ('usb' or 'tcp'): its dirty flags, its
    throttles, its dump. The interface marks every session dirty on player events and builds the
    messages (shared, stateless); each session decides when to push on its own link."""

    def __init__(self, itf, transport, send, netPeriod=NET_PERIOD, peer=''):
        self.itf = itf
        self.transport = transport
        self._send = send
        self.netPeriod = netPeriod
        self.peer = peer                # 'ip:port' (tcp), for the log
        self.chipid = None              # announced by fw >= 6 in its hello
        self.fw = None
        self.bat = None                 # last battery % logged
        self.chg = None
        self.lastRx = time.time()
        self.closing = False            # tcp: close at the next loop turn

        self._stDirty = False
        self._stLast = 0
        self._stSent = None
        self._volDirty = False
        self._listDirty = False
        self._peersDirty = False
        self._peersLast = 0
        self._netLast = 0
        self._helloWait = None          # connect-time silence window (see onConnect)
        self._probing = False           # usb, matched on the generic default filter: not ours until proven
        self._bareHellos = 0            # fw-less hellos seen on this link while probing

    def send(self, line):
        self._send(line)

    def log(self, *a):
        self.itf.log(*((('[' + self.peer + ']',) if self.peer else ()) + a))

    #
    # DEVICE -> commands
    #

    def onLine(self, line):
        self.lastRx = time.time()
        parts = line.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        if self.transport == 'usb' and RADAR_FRAME.match(line):
            self.itf.rejectPort("radar frames")     # a radar box on the shared id, never a remote
            return

        if cmd in ('hello', 'getall'):
            if cmd == 'hello':
                try:
                    proto = int(args[0]) if args else 0
                    fw = int(args[1]) if len(args) > 1 else 0
                except ValueError:
                    proto, fw = 0, 0
                chip = args[2] if len(args) > 2 else None
                self.fw = fw
                self.log("device hello: proto", proto, "fw", fw, *(('chip', chip) if chip else ()),
                         *(('over', self.transport) if self.transport != 'usb' else ()))
                if self._probing and len(args) < 2:
                    self._bareHellos += 1
                    if self._bareHellos < 2:
                        return      # the radar box says this once on boot: wait for the beacon
                self._probing = False
                if chip:
                    self.chipid = chip
                    self.itf._chipSeen(self, chip)
                if self.transport == 'usb' and self.itf._fwCheck(fw):
                    return          # link dropped for reflash, device will be back
                if self.closing:
                    return          # a tcp session of a remote that is on our USB now
            self._probing = False
            self.fullDump()
        elif cmd == 'hb':
            pass                    # heartbeat: lastRx is all it carries
        elif cmd == 'bat':
            self._bat(args)
        elif cmd in self.itf.CMDS:
            try:
                args = [int(a) for a in args]
            except ValueError:
                return self.log("bad args:", line)
            self._probing = False
            if self.itf.local:
                self.itf._execLocal(cmd, *args)
            else:
                self.itf.emit('remote-' + cmd, *args)
        # else: not for us (boot spew, debug prints..) -> drop

    def _bat(self, args):
        try:
            pct = int(args[0])
            chg = int(args[1]) if len(args) > 1 else 0
        except (ValueError, IndexError):
            return
        if self.bat is None or abs(pct - self.bat) >= BAT_LOG_STEP or chg != self.chg:
            self.bat, self.chg = pct, chg
            self.log('remote battery %d%%%s (%s)' % (pct, ' charging' if chg else '',
                                                     self.chipid or self.transport))

    #
    # HOST -> state stream
    #

    def onConnect(self):
        # stay silent until the device introduces itself: its hello carries the
        # firmware version (auto-flash check). A plugged device beacons within 3s
        # once stale. Silence: a USB port matched on the generic default is rejected
        # after HELLO_WAIT, any other link gets the dump after DUMP_WAIT (tick fallback).
        self._helloWait = time.time()
        self._probing = self.transport == 'usb' and self.itf.filter == DEFAULT_FILTER
        self._bareHellos = 0

    def onDisconnect(self):
        self._helloWait = None      # don't let the dump fallback race a dropped link

    def fullDump(self):
        self._helloWait = None
        itf = self.itf
        now = time.time()
        self.send(json.dumps({'t': 'hello', 'proto': PROTO,
                              'name': network.get_hostname(),
                              'ip': network.get_ip(itf.netiface)}, separators=(',', ':')))
        self.send(itf._volMsg())
        self._stSent = itf._stMsg()
        self.send(self._stSent)
        self.send(itf._netMsg())
        itf._sendList(self.send)
        itf._sendPeers(self.send)
        self._stDirty = self._volDirty = self._listDirty = self._peersDirty = False
        self._stLast = self._peersLast = self._netLast = now

    def tick(self):
        if self._helloWait:
            wait = HELLO_WAIT if self._probing else DUMP_WAIT
            if time.time() - self._helloWait > wait:
                if self._probing:
                    self.itf.rejectPort("no teleco2 hello in %ds" % wait)
                else:
                    self.log("no hello from device, dumping anyway")
                    self.fullDump()
            return
        itf = self.itf
        now = time.time()

        if self._stDirty and now - self._stLast >= ST_PERIOD:
            self._stDirty = False
            self._stLast = now
            msg = itf._stMsg()
            if msg != self._stSent:
                self._stSent = msg
                self.send(msg)

        if self._volDirty:
            self._volDirty = False
            self.send(itf._volMsg())

        if self._listDirty:
            self._listDirty = False
            itf._sendList(self.send)

        if self._peersDirty and now - self._peersLast >= PEERS_PERIOD:
            self._peersDirty = False
            self._peersLast = now
            itf._sendPeers(self.send)

        if now - self._netLast >= self.netPeriod:   # also the keepalive: always send
            self._netLast = now
            self.send(itf._netMsg())


class Teleco2Interface(SerialBase):

    def  __init__(self, hplayer, local=False, netiface='wlan0', filter=DEFAULT_FILTER,
                  netport=None, probeport=3739):
        super().__init__(hplayer, "Teleco2", filter)
        # persistent per-player override, must exist before settings.load()
        hplayer.settings._settings.setdefault('teleco2-filter', '')
        self.local = local          # True: execute commands on this player (autoBind)
                                    # False: emit 'remote-*' events, profile decides (parc broadcast)
        self.netiface = netiface
        self.netport = netport      # TCP port for remotes on WiFi (None: USB only, as before fw 6)
        self.probeport = probeport  # UDP discovery port (answers "find" with "here")

        self._listGen = 0
        self.usb = Teleco2Session(self, 'usb', self.send)
        self._net = []              # TCP sessions (the net thread owns the list)
        self._netLock = threading.Lock()
        self._netThread = None

        # embedded firmware: highest dist/teleco2_cores3-v<N>.bin wins
        self._fwBin = None
        self._fwExpected = 0
        self._flashTried = {}       # port -> attempts (1 max per session)
        distdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', '..', 'extra', 'arduino', 'teleco2_cores3', 'dist')
        try:
            for f in os.listdir(distdir):
                m = re.match(r'teleco2_cores3-v(\d+)\.bin$', f)
                if m and int(m.group(1)) > self._fwExpected:
                    self._fwExpected = int(m.group(1))
                    self._fwBin = os.path.join(distdir, f)
        except OSError:
            pass

        self.bind()

    # The scan loop reads .filter on every pass: a 'teleco2-filter' setting in the
    # /data cfg pins this player to one remote by its USB serial string.
    @property
    def filter(self):
        try:
            custom = self.hplayer.settings.get('teleco2-filter')
        except Exception:
            custom = None
        return custom if custom else self._filter

    @filter.setter
    def filter(self, value):
        self._filter = value

    def sessions(self):
        with self._netLock:
            return [self.usb] + list(self._net)

    #
    # PLAYER -> flags (handlers stay O(1), all link work happens in the sessions' tick())
    #

    def bind(self):

        @self.hplayer.on('status')
        def status(ev, *args):
            for s in self.sessions():
                s._stDirty = True

        @self.hplayer.on('*.playing')
        @self.hplayer.on('*.paused')
        @self.hplayer.on('*.resumed')
        @self.hplayer.on('*.stopped')
        @self.hplayer.on('*.media-end')
        def transition(ev, *args):
            for s in self.sessions():
                s._stDirty = True
                s._stLast = 0       # bypass throttle

        @self.hplayer.on('playlist.updated')
        def plist(ev, *args):
            self._listGen = (self._listGen + 1) % 100
            for s in self.sessions():
                s._listDirty = True

        @self.hplayer.on('settings.updated')
        def setts(ev, *args):
            for s in self.sessions():
                s._volDirty = True

        @self.hplayer.on('zyre.peer.link')
        def peerlink(ev, *args):
            for s in self.sessions():
                s._peersDirty = True

        @self.hplayer.on('app-closing')
        def closing(ev, *args):
            for s in self.sessions():
                s.send('{"t":"bye"}')

    #
    # USB transport (SerialBase pump) -> its session, unchanged behaviour
    #

    CMDS = ('prev', 'next', 'playpause', 'stop', 'playindex', 'volup', 'voldown')

    def onLine(self, line):
        self.usb.onLine(line)

    def onConnect(self):
        self.usb.onConnect()

    def onDisconnect(self):
        self.usb.onDisconnect()
        self.usb.chipid = None

    def fullDump(self):
        self.usb.fullDump()

    def tick(self):
        self.usb.tick()

    def _chipSeen(self, session, chip):
        """A hello named its chip. On USB: any TCP session of that same remote is a ghost (it
        switched to USB, WiFi off) -> close it. Over TCP while USB holds it: refuse."""
        if session is self.usb:
            with self._netLock:
                ghosts = [n for n in self._net if n.chipid == chip]
            for n in ghosts:
                n.log('remote', chip, 'is on our USB now: closing its TCP session')
                n.closing = True
        elif self.usb.chipid == chip and self.connected():
            session.log('remote', chip, 'is on our USB: TCP session refused')
            session.closing = True

    #
    # AUTO-FLASH: off-version remote -> reflash from the embedded dist image (USB only)
    #

    def _fwCheck(self, fw):
        """called on device hello; returns True if a reflash was initiated
        (link is closed, hotplug rescan will pick the device back up)"""
        if not self._fwBin:
            return False
        if fw == self._fwExpected:
            return False

        port = self.port
        if self._flashTried.get(port, 0) >= 1:
            return False        # already tried this session: run with the old remote

        # esptool present? (checked before dropping a working link)
        probe = subprocess.run([sys.executable, '-m', 'esptool', 'version'],
                               capture_output=True)
        if probe.returncode != 0:
            self.log("device fw", fw, "!= expected", self._fwExpected,
                     "but esptool is not installed: auto-flash disabled")
            self._fwBin = None
            return False

        self._flashTried[port] = self._flashTried.get(port, 0) + 1
        self.usb._helloWait = None  # dump fallback must not fire across the flash
        self.log("device fw", fw, "!= expected", self._fwExpected,
                 "-> auto-flash", os.path.basename(self._fwBin), "on", port)
        try:
            self.serial.close()     # free the port; pump will see the broken link and rescan
        except Exception:
            pass
        try:
            r = subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32s3',
                                '--port', port, '--baud', '921600',
                                'write_flash', '0x0', self._fwBin],
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                self.log("auto-flash done, device rebooting")
            else:
                self.log("auto-flash FAILED:", (r.stdout + r.stderr).strip()[-300:])
        except Exception as e:
            self.log("auto-flash error:", e)
        return True

    def _execLocal(self, cmd, *args):
        if cmd == 'playpause':      # autoBind 'playpause' means play-paused, roll the toggle
            p = self.hplayer.activePlayer()
            if p.isPaused():
                self.emit('resume')
            elif p.isPlaying():
                self.emit('pause')
            else:
                self.emit('play')
        elif cmd == 'volup':
            self.emit('volinc')
        elif cmd == 'voldown':
            self.emit('voldec')
        else:
            self.emit(cmd, *args)

    #
    # NETWORK transport (fw >= 6, netport): UDP discovery + one TCP session per remote
    #

    def start(self):
        super().start()
        if self.netport and not self._netThread:
            self._netThread = threading.Thread(target=self._netLoop, name='teleco2-net', daemon=True)
            self._netThread.start()

    def _hereMsg(self):
        wc = self.hplayer.interface('wallclock')
        try:
            lead = 1 if wc and wc.isLeader() else 0
        except Exception:
            lead = 0
        try:
            rssi = int(network.get_rssi(self.netiface) or 0)
        except (TypeError, ValueError):
            rssi = 0
        return json.dumps({'t': 'here', 'nm': self._fold(network.get_hostname())[:NAME_MAXLEN],
                           'port': self.netport, 'lead': lead, 'rssi': rssi,
                           'fw': self._fwExpected}, separators=(',', ':'))

    def _netLoop(self):
        sel = selectors.DefaultSelector()
        srv = udp = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('', self.netport))
            srv.listen(4)
            srv.setblocking(False)
            sel.register(srv, selectors.EVENT_READ, 'srv')
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp.bind(('', self.probeport))
            udp.setblocking(False)
            sel.register(udp, selectors.EVENT_READ, 'udp')
        except OSError as e:
            self.log('network remote: cannot listen (tcp %s / udp %s):' % (self.netport, self.probeport), e)
            for x in (srv, udp):
                if x:
                    x.close()
            return
        self.log('network remote: tcp', self.netport, '+ discovery udp', self.probeport)

        conns = {}                  # session -> [socket, rx bytes, tx bytearray, tx lock]

        def close(sess, why):
            c = conns.pop(sess, None)
            if c:
                try:
                    sel.unregister(c[0])
                except (KeyError, ValueError):
                    pass
                try:
                    c[0].close()
                except OSError:
                    pass
            with self._netLock:
                if sess in self._net:
                    self._net.remove(sess)
            sess.log('remote session closed:', why)

        def flush(sess):
            c = conns.get(sess)
            if not c:
                return
            with c[3]:
                if not c[2]:
                    return
                try:
                    n = c[0].send(bytes(c[2]))
                    del c[2][:n]
                except (BlockingIOError, InterruptedError):
                    pass
                except OSError as e:
                    c[2].clear()
                    sess.closing = 'send: %s' % e
                    return
                if len(c[2]) > NET_OUTMAX:
                    c[2].clear()
                    sess.closing = 'not reading (backlog over %d B)' % NET_OUTMAX

        try:
            while self.isRunning():
                for key, mask in sel.select(0.1):
                    if key.data == 'srv':
                        try:
                            sock, addr = srv.accept()
                        except OSError:
                            continue
                        sock.setblocking(False)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        c = [sock, b'', bytearray(), threading.Lock()]

                        def tx(line, c=c):
                            with c[3]:
                                c[2] += (line + '\n').encode('utf-8')
                        sess = Teleco2Session(self, 'tcp', tx, netPeriod=NET_PERIOD_TCP,
                                              peer='%s:%d' % addr)
                        conns[sess] = c
                        sel.register(sock, selectors.EVENT_READ, sess)
                        with self._netLock:
                            self._net.append(sess)
                        sess.log('remote connected over tcp')
                        sess.onConnect()
                    elif key.data == 'udp':
                        try:
                            data, addr = udp.recvfrom(512)
                        except OSError:
                            continue
                        words = data.decode('utf-8', 'replace').split()
                        if words and words[0] == 'find':
                            try:
                                udp.sendto(self._hereMsg().encode(), addr)
                            except OSError:
                                pass
                    else:
                        sess = key.data
                        c = conns.get(sess)
                        if not c:
                            continue
                        try:
                            data = c[0].recv(4096)
                        except (BlockingIOError, InterruptedError):
                            continue
                        except OSError as e:
                            close(sess, 'recv: %s' % e)
                            continue
                        if not data:
                            close(sess, 'remote hung up')
                            continue
                        c[1] += data
                        while b'\n' in c[1]:
                            raw, c[1] = c[1].split(b'\n', 1)
                            line = raw.decode('utf-8', 'replace').strip('\r')
                            if line:
                                try:
                                    sess.onLine(line)
                                except Exception as e:
                                    sess.log('onLine error:', e, '|', line)
                        if len(c[1]) > 4096:
                            c[1] = b''      # no newline in 4 KB: noise, not protocol

                now = time.time()
                for sess in list(conns):
                    if sess.closing:
                        flush(sess)
                        close(sess, sess.closing if isinstance(sess.closing, str) else 'closing')
                        continue
                    if now - sess.lastRx > NET_DEAD:
                        close(sess, 'silent %.1f s (half-open or gone)' % (now - sess.lastRx))
                        continue
                    try:
                        sess.tick()
                    except Exception as e:
                        sess.log('tick error:', e)
                    flush(sess)
        finally:
            for sess in list(conns):
                flush(sess)         # the "bye" queued by app-closing
                close(sess, 'player stopping')
            for x in (srv, udp):
                try:
                    sel.unregister(x)
                except (KeyError, ValueError):
                    pass
                x.close()
            sel.close()

    #
    # message builders (shared by every session)
    #

    def _fold(self, txt):       # ascii-fold so the firmware keeps a plain font
        return unicodedata.normalize('NFKD', txt).encode('ascii', 'ignore').decode('ascii')

    def _medname(self, path):
        return self._fold(os.path.splitext(os.path.basename(path))[0])[:MEDIA_MAXLEN]

    def _stMsg(self):
        s = self.hplayer.activePlayer().status()
        pl = 2 if s['isPaused'] else 1 if s['isPlaying'] else 0
        return json.dumps({'t': 'st', 'pl': pl,
                           'med': self._medname(s['media']) if s['media'] else '',
                           'i': self.hplayer.playlist.index(),
                           'n': self.hplayer.playlist.size(),
                           'pos': int(round(s['time'] or 0)),
                           'dur': int(round(s['duration'] or 0))}, separators=(',', ':'))

    def _volMsg(self):
        st = self.hplayer.settings
        return json.dumps({'t': 'vol', 'v': st.get('volume'),
                           'mute': 1 if st.get('mute') else 0,
                           'loop': st.get('loop')}, separators=(',', ':'))

    def _netMsg(self):
        rssi = network.get_rssi(self.netiface)
        return json.dumps({'t': 'net', 'ssid': network.get_essid(self.netiface),
                           'rssi': 5 * round(rssi / 5),
                           'ip': network.get_ip(self.netiface)}, separators=(',', ':'))

    def _sendList(self, send=None):
        send = send or self.send
        items = self.hplayer.playlist.export()
        names = [self._medname(m) for m in items[:LIST_MAXITEMS]]
        if not names:
            send(json.dumps({'t': 'list', 'g': self._listGen, 'n': 0, 'i': 0, 'items': []},
                            separators=(',', ':')))
            return
        for o in range(0, len(names), LIST_CHUNK):
            send(json.dumps({'t': 'list', 'g': self._listGen, 'n': len(items), 'i': o,
                             'items': names[o:o + LIST_CHUNK]}, separators=(',', ':')))

    def _sendPeers(self, send=None):
        send = send or self.send
        z = self.hplayer.interface('zyre')
        if not z:
            send(json.dumps({'t': 'peers', 'n': 0, 'i': 0, 'items': []}, separators=(',', ':')))
            return
        peers = []
        for p in list(z.peersList().values()):
            peers.append({'nm': self._fold(p.name)[:NAME_MAXLEN],
                          'lk': p.link,
                          'me': 1 if p.ip == '127.0.0.1' else 0})     # self is booked with localhost ip
        peers.sort(key=lambda p: (1 - p['me'], p['nm']))              # self first, then by name
        for o in range(0, len(peers), PEERS_CHUNK):
            send(json.dumps({'t': 'peers', 'n': z.activeCount(), 'i': o,
                             'items': peers[o:o + PEERS_CHUNK]}, separators=(',', ':')))
