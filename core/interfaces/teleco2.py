from .serialbase import SerialBase
from core.engine import network

import os
import json
import time
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
  hello <proto>      on boot + every 3s while no host line for >8s (doubles as dump request)
  getall             request full dump
  prev / next / playpause / stop / playindex <i> / volup / voldown

Device declares the link stale after 8s without a valid host line (net's 2s cadence = 4 missed).
"""

PROTO           = 1

MEDIA_MAXLEN    = 48
NAME_MAXLEN     = 16
LIST_MAXITEMS   = 200
LIST_CHUNK      = 8
PEERS_CHUNK     = 6

ST_PERIOD       = 0.5       # min interval between st pushes (2Hz)
PEERS_PERIOD    = 1.0       # coalesce peers table updates
NET_PERIOD      = 2.0       # net poll + keepalive


class Teleco2Interface(SerialBase):

    def  __init__(self, hplayer, local=False, netiface='wlan0', filter="HPlayer2|303a:1001"):
        super().__init__(hplayer, "Teleco2", filter)
        self.local = local          # True: execute commands on this player (autoBind)
                                    # False: emit 'remote-*' events, profile decides (parc broadcast)
        self.netiface = netiface

        self._stDirty = False
        self._stLast = 0
        self._stSent = None
        self._volDirty = False
        self._listDirty = False
        self._listGen = 0
        self._peersDirty = False
        self._peersLast = 0
        self._netLast = 0

        self.bind()

    #
    # PLAYER -> flags (handlers stay O(1), all serial work happens in tick())
    #

    def bind(self):

        @self.hplayer.on('status')
        def status(ev, *args):
            self._stDirty = True

        @self.hplayer.on('*.playing')
        @self.hplayer.on('*.paused')
        @self.hplayer.on('*.resumed')
        @self.hplayer.on('*.stopped')
        @self.hplayer.on('*.media-end')
        def transition(ev, *args):
            self._stDirty = True
            self._stLast = 0        # bypass throttle

        @self.hplayer.on('playlist.updated')
        def plist(ev, *args):
            self._listGen = (self._listGen + 1) % 100
            self._listDirty = True

        @self.hplayer.on('settings.updated')
        def setts(ev, *args):
            self._volDirty = True

        @self.hplayer.on('zyre.peer.link')
        def peerlink(ev, *args):
            self._peersDirty = True

        @self.hplayer.on('app-closing')
        def closing(ev, *args):
            self.send('{"t":"bye"}')

    #
    # DEVICE -> commands
    #

    CMDS = ('prev', 'next', 'playpause', 'stop', 'playindex', 'volup', 'voldown')

    def onLine(self, line):
        parts = line.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ('hello', 'getall'):
            self.fullDump()
        elif cmd in self.CMDS:
            try:
                args = [int(a) for a in args]
            except ValueError:
                return self.log("bad args:", line)
            if self.local:
                self._execLocal(cmd, *args)
            else:
                self.emit('remote-' + cmd, *args)
        # else: not for us (boot spew, debug prints..) -> drop

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
    # HOST -> state stream
    #

    def onConnect(self):
        self.fullDump()

    def fullDump(self):
        now = time.time()
        self.send(json.dumps({'t': 'hello', 'proto': PROTO,
                              'name': network.get_hostname(),
                              'ip': network.get_ip(self.netiface)}, separators=(',', ':')))
        self.send(self._volMsg())
        self._stSent = self._stMsg()
        self.send(self._stSent)
        self.send(self._netMsg())
        self._sendList()
        self._sendPeers()
        self._stDirty = self._volDirty = self._listDirty = self._peersDirty = False
        self._stLast = self._peersLast = self._netLast = now

    def tick(self):
        now = time.time()

        if self._stDirty and now - self._stLast >= ST_PERIOD:
            self._stDirty = False
            self._stLast = now
            msg = self._stMsg()
            if msg != self._stSent:
                self._stSent = msg
                self.send(msg)

        if self._volDirty:
            self._volDirty = False
            self.send(self._volMsg())

        if self._listDirty:
            self._listDirty = False
            self._sendList()

        if self._peersDirty and now - self._peersLast >= PEERS_PERIOD:
            self._peersDirty = False
            self._peersLast = now
            self._sendPeers()

        if now - self._netLast >= NET_PERIOD:       # also the keepalive: always send
            self._netLast = now
            self.send(self._netMsg())

    #
    # message builders
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

    def _sendList(self):
        items = self.hplayer.playlist.export()
        names = [self._medname(m) for m in items[:LIST_MAXITEMS]]
        if not names:
            self.send(json.dumps({'t': 'list', 'g': self._listGen, 'n': 0, 'i': 0, 'items': []},
                                 separators=(',', ':')))
            return
        for o in range(0, len(names), LIST_CHUNK):
            self.send(json.dumps({'t': 'list', 'g': self._listGen, 'n': len(items), 'i': o,
                                  'items': names[o:o + LIST_CHUNK]}, separators=(',', ':')))

    def _sendPeers(self):
        z = self.hplayer.interface('zyre')
        if not z:
            self.send(json.dumps({'t': 'peers', 'n': 0, 'i': 0, 'items': []}, separators=(',', ':')))
            return
        peers = []
        for p in list(z.peersList().values()):
            peers.append({'nm': self._fold(p.name)[:NAME_MAXLEN],
                          'lk': p.link,
                          'me': 1 if p.ip == '127.0.0.1' else 0})     # self is booked with localhost ip
        peers.sort(key=lambda p: (1 - p['me'], p['nm']))              # self first, then by name
        for o in range(0, len(peers), PEERS_CHUNK):
            self.send(json.dumps({'t': 'peers', 'n': z.activeCount(), 'i': o,
                                  'items': peers[o:o + PEERS_CHUNK]}, separators=(',', ':')))
