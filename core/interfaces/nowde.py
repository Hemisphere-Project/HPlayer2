from .base import BaseInterface
from ..engine.drifter import Drifter
import importlib
import os
import re
import threading
import time
from typing import Optional, Sequence
from termcolor import colored

mido = None
_MIDO_IMPORT_ERROR = None
try:
    mido = importlib.import_module("mido")
except ImportError as err:
    _MIDO_IMPORT_ERROR = err

Timecode = None
_TIMECODE_IMPORT_ERROR = None
try:
    _timecode_module = importlib.import_module("timecode")
    Timecode = getattr(_timecode_module, "Timecode", None)
except ImportError as err:
    _TIMECODE_IMPORT_ERROR = err

_PatternType = type(re.compile(""))


#
#  NOWDE — ESP32-S3 sync node on USB-MIDI (github.com/Hemisphere-Project/Nowde)
#
#  Two legs, one interface. The node tells us which one to run (HELLO carries
#  its role since Nowde v2), or the profile forces it with mode=.
#
#  SLAVE leg (Nowde v1.2+, AnnaTV since 2025): the node drives THIS player.
#    CC#100 = media index (0 = stop, N = play the file prefixed N_ / 0N_ / 00N_)
#    MTC quarter-frames / full-frame = position -> Drifter chase-lock servo
#
#  MASTER leg (Nowde v2, Biennale 2026): THIS player drives the node, which
#  relays to every slave on the mesh. We speak the exact MillluBridge SysEx:
#    MEDIA_SYNC @10 Hz {layer, index, position ms, state}
#    QUERY_CONFIG handshake, QUERY_RUNNING_STATE poll (slave table -> nowde.receivers)
#  Only the INDEX travels: what a slave plays for index 7 is its own media folder.
#
#  Protocol reference: docs/PROTOCOL.md in the Nowde repo.
#

# ---- SysEx 0x7D wire helpers (byte-exact with MillluBridge Bridge/src/midi) ----

SYSEX_MANUFACTURER_ID = 0x7D
CMD_QUERY_CONFIG = 0x01
CMD_QUERY_RUNNING_STATE = 0x03
CMD_SET_ROLE = 0x08
CMD_SET_LOCAL_LAYER = 0x09
CMD_MEDIA_SYNC = 0x10
CMD_CHANGE_RECEIVER_LAYER = 0x11
CMD_HELLO = 0x20
CMD_CONFIG_STATE = 0x21
CMD_RUNNING_STATE = 0x22
CMD_ERROR_REPORT = 0x30

ROLE_NAMES = {0: 'slave', 1: 'master', 2: 'legacy'}
BOARD_NAMES = {0: 'unknown', 1: 'devkit', 2: 'atoms3', 3: 'atoms3-lite'}
ERROR_NAMES = {0x01: 'CONFIG_INVALID', 0x02: 'SYSEX_PARSE_ERROR', 0x03: 'ESPNOW_SEND_FAILED',
               0x04: 'MESH_CLOCK_LOST_SYNC', 0x05: 'RECEIVER_TIMEOUT', 0xFF: 'UNKNOWN'}
RESET_REASONS = {1: 'POWERON', 3: 'SW', 4: 'PANIC', 5: 'INT_WDT', 6: 'TASK_WDT', 7: 'WDT',
                 8: 'DEEPSLEEP', 9: 'BROWNOUT', 10: 'SDIO', 12: 'USB', 15: 'JTAG'}


def encode7(raw):
    """8-bit -> 7-bit: every run of 7 bytes becomes 8 (MSB byte first)."""
    out = []
    i = 0
    while i < len(raw):
        chunk = raw[i:i + 7]
        msb = 0
        for j, b in enumerate(chunk):
            if b & 0x80:
                msb |= (1 << j)
        out.append(msb)
        out.extend(b & 0x7F for b in chunk)
        i += 7
    return out


def decode7(enc):
    """7-bit -> 8-bit, inverse of encode7."""
    out = []
    i = 0
    while i < len(enc):
        msb = enc[i]
        i += 1
        chunk = enc[i:i + 7]
        for j, b in enumerate(chunk):
            out.append(b | 0x80 if msb & (1 << j) else b)
        i += 7
    return out


def build_media_sync(layer, index, position_ms, playing):
    """MEDIA_SYNC payload (without F0/F7): 7D 10 layer(16) index(1) pos(5) state(1) = 25 bytes."""
    layer_bytes = (str(layer)[:16] + '\x00' * 16)[:16].encode('ascii', errors='replace')
    index = max(0, min(127, int(index)))
    position_ms = max(0, int(position_ms)) & 0xFFFFFFFF
    pos_raw = [(position_ms >> 24) & 0xFF, (position_ms >> 16) & 0xFF,
               (position_ms >> 8) & 0xFF, position_ms & 0xFF]
    return ([SYSEX_MANUFACTURER_ID, CMD_MEDIA_SYNC] + list(layer_bytes) + [index]
            + encode7(pos_raw) + [1 if playing else 0])


def build_change_receiver_layer(mac, layer):
    """mac: 6 ints. Payload: 7D 11 mac(7) layer(19)."""
    layer_bytes = list((str(layer)[:16] + '\x00' * 16)[:16].encode('ascii', errors='replace'))
    return [SYSEX_MANUFACTURER_ID, CMD_CHANGE_RECEIVER_LAYER] + encode7(list(mac)) + encode7(layer_bytes)


def build_simple(cmd, *args):
    return [SYSEX_MANUFACTURER_ID, cmd] + list(args)


def parse_hello(d):
    """d = payload after the command byte. Returns dict or None."""
    if len(d) < 16:
        return None
    version = bytes(decode7(d[0:10])[:8]).decode('ascii', errors='ignore').rstrip('\x00')
    up = decode7(d[10:15])
    uptime = (up[0] << 24) | (up[1] << 16) | (up[2] << 8) | up[3]
    reason = d[15]
    info = {'version': version, 'uptime': uptime,
            'boot_reason': RESET_REASONS.get(reason, 'UNKNOWN_%d' % reason)}
    if len(d) >= 18:                       # v2 trailer
        info['role'] = ROLE_NAMES.get(d[16], 'unknown')
        info['board'] = BOARD_NAMES.get(d[17], 'unknown')
    return info


def parse_config_state(d):
    if len(d) < 3:
        return None
    info = {'rf_sim': bool(d[0]), 'rf_sim_delay': (d[1] << 7) | d[2]}
    if len(d) >= 6:                        # v2 trailer
        info['role'] = ROLE_NAMES.get(d[3], 'unknown')
        info['board'] = BOARD_NAMES.get(d[4], 'unknown')
        n = d[5]
        info['layer'] = bytes(d[6:6 + n]).decode('ascii', errors='ignore')
    return info


def parse_running_state(d):
    """One chunk. Returns (meta, [receiver dicts])."""
    if len(d) < 10:
        return None, []
    up = decode7(d[0:5])
    meta = {'uptime': (up[0] << 24) | (up[1] << 16) | (up[2] << 8) | up[3],
            'synced': bool(d[5]), 'total': d[6], 'chunk': d[7], 'chunks': d[8]}
    n = d[9]
    receivers = []
    idx = 10
    for _ in range(n):
        if idx + 42 > len(d):
            break
        r = decode7(d[idx:idx + 42])
        idx += 42
        if len(r) < 36:
            break
        mac = r[0:6]
        receivers.append({
            'mac': ':'.join('%02X' % b for b in mac), 'mac_bytes': mac,
            'layer': bytes(r[6:22]).decode('ascii', errors='ignore').rstrip('\x00'),
            'version': bytes(r[22:30]).decode('ascii', errors='ignore').rstrip('\x00'),
            'last_seen': (r[30] << 24) | (r[31] << 16) | (r[32] << 8) | r[33],
            'index': r[35],
        })
    return meta, receivers


def media_index_of(path):
    """Numeric prefix of a media file name -> 1..127, else 0."""
    if not path:
        return 0
    m = re.match(r'^0*(\d{1,3})_', os.path.basename(str(path)))
    if not m:
        return 0
    n = int(m.group(1))
    return n if 1 <= n <= 127 else 0


class NowdeInterface(BaseInterface):

    PORT_LOOKUP_INTERVAL = 5.0
    CONNECTION_CHECK_INTERVAL = 2.0  # Check connection health every 2 seconds
    SYNC_INTERVAL = 0.1              # master: MEDIA_SYNC cadence
    SYNC_IDLE_INTERVAL = 1.0         # master: cadence while stopped
    POLL_INTERVAL = 1.0              # master: QUERY_RUNNING_STATE
    PROBE_INTERVAL = 2.0             # slave/auto: keepalive + role probe (silent on v1.2 nodes)
    PROBE_TIMEOUT = 6.0              # auto: no HELLO after this -> assume a legacy (v1.2) slave node

    DEFAULTS = {
        'nowde-layer':         'hplayer2',  # master: layer we sync on
        'nowde-index-default': 0,           # master: index sent for un-numbered media (0 = slaves stop)
        'nowde-jumpfix':       500,         # slave: seek-latency compensation ms (300 RockPro64, ~1000 laptop)
        'nowde-dance':         False,       # slave: Drifter smart-join instead of blind seeks
    }

    def __init__(self, hplayer, player=None, port_name=None, max_retry=0, mode='auto'):
        if _MIDO_IMPORT_ERROR:
            raise RuntimeError("mido is required for NowdeInterface") from _MIDO_IMPORT_ERROR
        if mido is None:
            raise RuntimeError("mido is unavailable for NowdeInterface")
        if _TIMECODE_IMPORT_ERROR:
            raise RuntimeError("timecode is required for NowdeInterface") from _TIMECODE_IMPORT_ERROR
        if Timecode is None:
            raise RuntimeError("timecode is unavailable for NowdeInterface")
        super().__init__(hplayer, "NOWDE")

        self.logQuietEvents.extend(['qf', 'ff', 'status', 'receivers'])  # high-rate, UI only

        # seed persistent, http2-editable tunables (must exist before settings.load())
        for k, v in self.DEFAULTS.items():
            hplayer.settings._settings.setdefault(k, v)

        self.port = None
        self.out = None
        self.port_filter = port_name if port_name is not None else re.compile(r"^Nowde")
        self.max_retry = max_retry
        self._resolved_port_name: Optional[str] = None

        # create a global accumulator for quarter_frames
        self.quarter_frames = [0, 0, 0, 0, 0, 0, 0, 0]

        # Player control
        self.player = player
        if self.player is None:
            plist = hplayer.players() if callable(hplayer.players) else hplayer.players
            plist = list(plist.values()) if isinstance(plist, dict) else list(plist)
            self.player = plist[0] if plist else None

        # Role: 'auto' waits for the node's HELLO; 'master' / 'slave' are forced
        if mode not in ('auto', 'master', 'slave'):
            raise RuntimeError("NowdeInterface mode must be auto, master or slave")
        self.mode = mode
        self.role = None if mode == 'auto' else mode
        self.node = {}                  # last HELLO / CONFIG_STATE
        self.receivers = []             # master: slave table from RUNNING_STATE
        self.mesh_synced = False
        self._connected_at = 0.0
        self._lastSyncSend = 0.0
        self._lastPoll = 0.0
        self._lastProbe = 0.0
        self._lastStatus = 0.0
        self._lastSent = None           # (index, playing) of the last MEDIA_SYNC
        self._assigned = set()          # macs we already re-layered

        # Slave sync state (the chase-lock servo lives in the shared Drifter)
        self.jumpFix = 500       # seek-latency compensation (300ms RockPro64 on loop, 1000ms laptop)
        self.isStopped = False   # Flag to ignore MTC when stopped
        self.lastCC = None       # Track last CC#100 value to avoid redundant commands
        self.lastPattern = None  # Remember last pattern for auto-restart on loop

        # Chase-lock servo: the shared Drifter (ported from this very tracker).
        # nowde keeps the legacy asymmetric seek tolerance — ramp speed to catch
        # up when behind (up to 10s), hard-seek only when >2s ahead.
        self.drifter = Drifter(self.player, log=self.log, jumpFix=self.jumpFix,
                               seekLateThreshold=10) if self.player else None
        if self.drifter:
            self.drifter.onStalled = self._restart_on_loop

        # Bind to our own events
        self.hplayer.on('nowde.qf')(self.handle_timecode)
        self.hplayer.on('osc.time')(self.handle_timecode)

        # Master leg: push a MEDIA_SYNC on player edges, not just on the 10 Hz tick
        if self.player:
            pname = self.player.name.lower()
            for ev in ('playing', 'stopped', 'paused', 'resumed', 'seekedto'):
                self.hplayer.on(pname + '.' + ev)(self._on_player_edge)

    # ------------------------------------------------------------------ role

    def isMaster(self):
        return self.role == 'master'

    def isSlave(self):
        return self.role == 'slave'

    def isLinked(self):
        return self.port is not None

    def _set_role(self, role, source):
        if role == 'legacy':
            role = 'slave'
        if role not in ('master', 'slave'):
            return
        if self.role == role:
            return
        self.role = role
        self.log(colored(f"role: {role.upper()} ({source})", 'cyan'))
        self.emit('role', role)
        if role == 'master' and self.out:
            self._handshake()

    def _cfg(self, key):
        try:
            v = self.hplayer.settings.get(key)
        except Exception:
            v = None
        return self.DEFAULTS[key] if v is None else v

    # ------------------------------------------------------------------ MIDI out

    def _send(self, payload):
        """payload = bytes between F0 and F7."""
        if not self.out:
            return False
        try:
            self.out.send(mido.Message('sysex', data=payload))
            return True
        except Exception as err:
            self.log(colored(f"send failed: {err}", 'red'))
            return False

    def _handshake(self):
        # QUERY_CONFIG: the Bridge handshake. On a v1.2 node this is what turns it into
        # a sender, on a v2 master it just answers HELLO + CONFIG_STATE.
        self._send(build_simple(CMD_QUERY_CONFIG))

    def _probe(self):
        # QUERY_RUNNING_STATE: silent on a v1.2 receiver (keeps it a receiver), answered
        # with HELLO by a v2 node that has not heard from us for a while, and with the
        # slave table by a sender. Doubles as the host-link keepalive the node's LED shows.
        self._send(build_simple(CMD_QUERY_RUNNING_STATE))

    def set_node_role(self, role):
        """Store a role on the node (v2): 'master', 'slave' or 'auto'."""
        code = {'slave': 0, 'master': 1, 'auto': 0x7F}.get(role)
        if code is None:
            return False
        return self._send(build_simple(CMD_SET_ROLE, code))

    def set_node_layer(self, layer):
        """Set the node's own subscribed layer (v2)."""
        return self._send(build_simple(CMD_SET_LOCAL_LAYER, *list(str(layer)[:15].encode('ascii', errors='replace'))))

    # ------------------------------------------------------------------ master leg

    def _media_state(self):
        """(index, position_ms, playing) of the bound player, as the mesh sees it."""
        if not self.player:
            return 0, 0, False
        st = self.player.status()
        media = st.get('media')
        playing = bool(st.get('isPlaying')) and not bool(st.get('isPaused'))
        index = media_index_of(media) if media else 0
        if media and index == 0:
            try:
                index = max(0, min(127, int(self._cfg('nowde-index-default'))))
            except (TypeError, ValueError):
                index = 0
        if index == 0:
            playing = False
        try:
            position_ms = int(float(st.get('time') or 0) * 1000)
        except (TypeError, ValueError):
            position_ms = 0
        return index, position_ms, playing

    def _master_send(self, force=False):
        if not self.isMaster() or not self.out:
            return
        index, position_ms, playing = self._media_state()
        now = time.time()
        interval = self.SYNC_INTERVAL if playing else self.SYNC_IDLE_INTERVAL
        changed = (index, playing) != self._lastSent
        if not (force or changed or now - self._lastSyncSend >= interval):
            return
        if self._send(build_media_sync(self._cfg('nowde-layer'), index, position_ms, playing)):
            self._lastSyncSend = now
            if changed:
                self.log(f"MEDIA_SYNC layer={self._cfg('nowde-layer')} index={index} state={'playing' if playing else 'stopped'}")
                self._lastSent = (index, playing)

    def _on_player_edge(self, ev, *args):
        if self.isMaster():
            self._master_send(force=True)

    def _auto_assign_layers(self):
        """v1.2 slaves ship on layer '-': give them ours so they follow (v2 slaves use '*')."""
        layer = str(self._cfg('nowde-layer'))
        for r in self.receivers:
            if r['layer'] == '-' and r['mac'] not in self._assigned:
                self.log(f"assigning layer '{layer}' to slave {r['mac']} (v{r['version']})")
                self._send(build_change_receiver_layer(r['mac_bytes'], layer))
                self._assigned.add(r['mac'])

    # ------------------------------------------------------------------ SysEx in

    def _handle_sysex(self, data):
        """data = mido sysex payload (no F0/F7). Only our manufacturer id lands here."""
        if len(data) < 2:
            return
        cmd = data[1]
        d = list(data[2:])
        if cmd == CMD_HELLO:
            info = parse_hello(d)
            if not info:
                return
            self.node.update(info)
            self.log(f"HELLO v{info['version']} up={info['uptime']}ms boot={info['boot_reason']}"
                     + (f" role={info['role']} board={info['board']}" if 'role' in info else " (v1 node)"))
            self.emit('hello', info)
            if self.mode == 'auto' and 'role' in info:
                self._set_role(info['role'], 'HELLO')
            if self.isMaster():
                self._lastSent = None           # node rebooted or (re)appeared: resend state
                self._assigned.clear()
                if info.get('uptime', 0) < 5000:
                    self._handshake()
        elif cmd == CMD_CONFIG_STATE:
            info = parse_config_state(d)
            if info:
                self.node.update(info)
        elif cmd == CMD_RUNNING_STATE:
            meta, receivers = parse_running_state(d)
            if meta is None:
                return
            self.mesh_synced = meta['synced']
            if meta['chunk'] == 0:
                self._chunkbuf = []
            buf = getattr(self, '_chunkbuf', [])
            buf.extend(receivers)
            self._chunkbuf = buf
            if meta['chunk'] >= meta['chunks'] - 1:
                self.receivers = list(buf)
                self.emit('receivers', self.receivers)
                self._auto_assign_layers()
        elif cmd == CMD_ERROR_REPORT:
            if len(d) >= 2:
                code = d[0]
                ctx = ' '.join('%02X' % b for b in d[2:2 + d[1]])
                self.log(colored(f"node error {ERROR_NAMES.get(code, hex(code))} {ctx}", 'yellow'))
                self.emit('error', ERROR_NAMES.get(code, hex(code)), ctx)

    # ------------------------------------------------------------------ status

    def _push_status(self):
        now = time.time()
        if now - self._lastStatus < 1.0:
            return
        self._lastStatus = now
        index, position_ms, playing = self._media_state() if self.isMaster() else (self.lastCC or 0, 0, not self.isStopped)
        self.emit('status', {
            'linked': self.isLinked(), 'role': self.role, 'port': self._resolved_port_name,
            'node': {k: v for k, v in self.node.items() if k in ('version', 'role', 'board', 'layer')},
            'mesh_synced': self.mesh_synced, 'slaves': len(self.receivers),
            'layer': self._cfg('nowde-layer') if self.isMaster() else self.node.get('layer'),
            'index': index, 'playing': playing,
        })

    # ------------------------------------------------------------------ threads

    def _emitter_loop(self):
        """Master: MEDIA_SYNC + table poll. Slave/auto: role probe + keepalive."""
        while not self.stopped.is_set():
            try:
                if self.out:
                    now = time.time()
                    if self.isMaster():
                        self._master_send()
                        if now - self._lastPoll >= self.POLL_INTERVAL:
                            self._lastPoll = now
                            self._probe()
                    else:
                        if now - self._lastProbe >= self.PROBE_INTERVAL:
                            self._lastProbe = now
                            self._probe()
                        if (self.mode == 'auto' and self.role is None
                                and now - self._connected_at > self.PROBE_TIMEOUT):
                            self._set_role('slave', 'no HELLO, assuming v1 node')
                    self._push_status()
            except Exception as err:
                self.log(colored(f"emitter error: {err}", 'red'))
            self.stopped.wait(0.02)

    # MTC receiver THREAD
    def listen(self):
        self.log(f"starting listener (mode={self.mode}) with auto-reconnect")
        threading.Thread(target=self._emitter_loop, name='nowde-emitter', daemon=True).start()

        def clbck(message):
            # Wait for app to be running before handling MIDI
            if not self.hplayer.appRunning:
                return

            if message.type == 'quarter_frame':
                self.quarter_frames[message.frame_type] = message.frame_value
                if message.frame_type == 7:
                    tc = mtc_decode_quarter_frames(self.quarter_frames)
                    self.emit('qf', tc)
            elif message.type == 'sysex':
                data = message.data
                if len(data) >= 2 and data[0] == SYSEX_MANUFACTURER_ID:
                    self._handle_sysex(data)
                elif len(data) == 8 and data[0:4] == (127, 127, 1, 1):
                    tc = mtc_decode(data[4:])
                    self.emit('ff', tc)
            elif message.type == 'control_change':
                if message.control == 100 and not self.isMaster():
                    self.handle_media_selection(message.value)
            # 'start' / 'stop' real-time messages from v2 nodes: CC#100 already carries the
            # transition, nothing to do here.

        # Main reconnection loop
        while not self.stopped.is_set():
            try:
                target_port = self._wait_for_port()
                if not target_port:
                    if self.max_retry > 0:
                        self.log(f"no MIDI input matching {self._port_filter_label()} found; stopping")
                        break
                    else:
                        self.log(f"no MIDI input found, retrying...")
                        self.stopped.wait(self.PORT_LOOKUP_INTERVAL)
                        continue

                self.log(f"connecting to '{target_port}'")
                try:
                    self.port = mido.open_input(target_port, callback=clbck)
                    self._resolved_port_name = target_port
                    self.log(f"successfully connected to '{target_port}'")
                except OSError as err:
                    self.log(f"failed to open '{target_port}': {err}")
                    self.port = None
                    self._resolved_port_name = None
                    self.stopped.wait(self.PORT_LOOKUP_INTERVAL)
                    continue

                # Matching output (same device): needed by the master leg, harmless otherwise
                out_name = self._resolve_port_from(mido.get_output_names())
                if out_name:
                    try:
                        self.out = mido.open_output(out_name)
                    except OSError as err:
                        self.log(f"output '{out_name}' unavailable: {err}")
                        self.out = None
                else:
                    self.out = None
                self._connected_at = time.time()
                self._lastSent = None
                self.emit('linked', target_port)
                if self.out:
                    if self.mode == 'master':
                        self._handshake()
                    else:
                        self._probe()

                # Monitor connection health
                while not self.stopped.is_set() and self.port is not None:
                    # Check if port still exists in available ports
                    available_ports = mido.get_input_names()
                    if target_port not in available_ports:
                        self.log(colored(f"WARNING: MIDI port '{target_port}' disconnected!", 'red'))
                        break

                    # Wait before next check
                    self.stopped.wait(self.CONNECTION_CHECK_INTERVAL)

                # Clean up disconnected port
                self._close_ports()
                self.emit('unlinked')

                # If we're not stopping, this was a disconnect - try to reconnect
                if not self.stopped.is_set():
                    self.log(colored("attempting to reconnect...", 'yellow'))
                    self.stopped.wait(self.PORT_LOOKUP_INTERVAL)

            except Exception as err:
                self.log(colored(f"listener error: {err}", 'red'))
                self._close_ports()

                # Retry on error unless stopping
                if not self.stopped.is_set():
                    self.log("retrying after error...")
                    self.stopped.wait(self.PORT_LOOKUP_INTERVAL)

        # Final cleanup
        self._close_ports()
        self.log("listener stopped")

    def _close_ports(self):
        for attr in ('port', 'out'):
            p = getattr(self, attr)
            if p is not None:
                try:
                    p.close()
                except Exception as close_err:
                    self.log(f"error closing {attr}: {close_err}")
                setattr(self, attr, None)
        self._resolved_port_name = None
        self.receivers = []
        self.mesh_synced = False
        if self.mode == 'auto':
            self.role = None        # the next node may be another role

    def _wait_for_port(self) -> Optional[str]:
        attempts = 0

        while not self.stopped.is_set():
            available = mido.get_input_names()
            match = self._resolve_port_from(available)
            if match:
                return match

            attempts += 1
            ports_display = ", ".join(available) if available else "none"
            total = self.max_retry if self.max_retry else "inf"
            self.log(f"retry {attempts}/{total}: waiting for MIDI input {self._port_filter_label()} (available: {ports_display})")

            if self.max_retry and attempts >= self.max_retry:
                break

            self.stopped.wait(self.PORT_LOOKUP_INTERVAL)

        return None

    def _resolve_port_from(self, candidates: Sequence[str]) -> Optional[str]:
        for candidate in candidates:
            if self._matches_port(candidate):
                return candidate
        return None

    def _matches_port(self, name: str) -> bool:
        if self.port_filter is None:
            return True
        if isinstance(self.port_filter, _PatternType):
            return bool(self.port_filter.search(name))
        return str(self.port_filter) == name

    def _port_filter_label(self) -> str:
        if self.port_filter is None:
            return "any port"
        if isinstance(self.port_filter, _PatternType):
            return f"pattern '{self.port_filter.pattern}'"
        return f"'{self.port_filter}'"

    # ------------------------------------------------------------------ slave leg

    def handle_media_selection(self, cc_value):
        """Handle CC#100 for media selection"""
        # Only process if CC value changed
        if cc_value == self.lastCC:
            return

        self.lastCC = cc_value

        if cc_value == 0:
            # Stop playback
            self.log("CC#100=0: Stopping playback")
            if self.player:
                self.player.stop()
            self.isStopped = True
            self.lastPattern = None  # Clear pattern when stopped
        else:
            # Build pattern with zero-padding support using glob-style wildcard
            # The pattern uses regex alternation with glob wildcards
            # For single digit: match X_*, 0X_*, or 00X_*
            # For double digit: match XX_* or 0XX_*
            # For triple digit: match XXX_*
            if cc_value < 10:
                pattern = f"(00{cc_value}_*|0{cc_value}_*|{cc_value}_*)"
            elif cc_value < 100:
                pattern = f"(0{cc_value}_*|{cc_value}_*)"
            else:
                pattern = f"{cc_value}_*"

            self.log(f"CC#100={cc_value}: Playing media matching pattern: {pattern}")

            # Try to play the media
            self.hplayer.playlist.play(pattern)
            if self.hplayer.playlist.size() > 0:
                self.isStopped = False
                if self.drifter:
                    # live tunables (http2-editable) applied at every media start
                    try:
                        self.drifter.jumpFix = int(self._cfg('nowde-jumpfix'))
                    except (TypeError, ValueError):
                        pass
                    self.drifter.danceMode = bool(self._cfg('nowde-dance'))
                    self.drifter.arm()  # reset the servo grace for the new media
                self.lastPattern = pattern  # Remember this pattern
            else:
                self.log(colored(f"WARNING: No media found for CC#100={cc_value} (pattern: {pattern})", 'yellow'))
                if self.player:
                    self.player.stop()
                self.isStopped = True
                self.lastPattern = None

    def handle_timecode(self, ev, *args):
        """Feed the external MTC/OSC clock to the shared chase-lock servo."""
        if self.player is None or self.drifter is None:
            return

        # The master leg owns the player: its own clock is the reference
        if self.isMaster():
            return

        # Ignore MTC when explicitly stopped via CC#100=0
        if self.isStopped:
            return

        if ev == 'nowde.qf':
            clock = round(args[0].float, 2)   # Timecode -> seconds
        else:
            clock = round(float(args[0]), 2)  # osc.time -> seconds

        self.drifter.tick(clock)

    def _restart_on_loop(self):
        """Drifter stall hook: the local video ended while the master clock
        keeps running -> restart the remembered pattern (timecode-loop restart)."""
        if self.lastPattern is None or self.isStopped:
            return
        self.log(f"Video ended, restarting with pattern: {self.lastPattern}")
        self.hplayer.playlist.play(self.lastPattern)
        if self.hplayer.playlist.size() == 0:
            self.log(colored(f"WARNING: Pattern {self.lastPattern} no longer matches any files", 'yellow'))


##### MTC TOOLS imported from
##### https://github.com/jeffmikels/timecode_tools

def bitstring_to_bytes(s, bytecount=1, byteorder='big'):
    return int(s, 2).to_bytes(bytecount, byteorder)

# binary big-endian
def bbe(n, bits=8):
    # terminal condition
    retval = ''
    if n == 0:
        retval = '0'
    else:
        retval = bbe(n//2, None) + str(n%2)
    if bits is None:
        return retval
    else:
        return (('0'*bits) + retval)[-bits:]


# binary, little-endian
def ble(n, bits=8):
    # terminal condition
    retval = ''
    if n == 0:
        retval = '0'
    else:
        retval = str(n%2) + ble(n//2, None)
    if bits is None:
        return retval
    else:
        return (retval + ('0'*bits))[0:bits]

def cint(n, bytecount=2):
    return int(n).to_bytes(bytecount, byteorder='little')

def units_tens(n):
    return n % 10, int(n/10)

##
## LTC functions
##
# GENERATE BINARY-CODED DATA FOR LTC
# ACCORDING TO https://en.wikipedia.org/wiki/Linear_timecode
# everything is encoded little endian
# so to encode the number 3 with four bits, we have 1100
def ltc_encode(timecode, as_string=False):
    LTC = ''
    HLP = ''
    hrs, mins, secs, frs = timecode.frames_to_tc(timecode.frames)
    frame_units, frame_tens = units_tens(frs)
    secs_units, secs_tens = units_tens(secs)
    mins_units, mins_tens = units_tens(mins)
    hrs_units, hrs_tens = units_tens(hrs)

    #frames units / user bits field 1 / frames tens
    LTC += ble(frame_units,4) + '0000' + ble(frame_tens,2)
    HLP += '---{u}____-{t}'.format(u=frame_units, t=frame_tens)

    #drop frame / color frame / user bits field 2
    LTC += '00'+'0000'
    HLP += '__'+'____'

    #secs units / user bits field 3 / secs tens
    LTC += ble(secs_units,4) + '0000' + ble(secs_tens,3)
    HLP += '---{u}____--{t}'.format(u=secs_units, t=secs_tens)

    # bit 27 flag / user bits field 4
    LTC += '0' + '0000'
    HLP += '_' + '____'

    #mins units / user bits field 5 / mins tens
    LTC += ble(mins_units,4) + '0000' + ble(mins_tens,3)
    HLP += '---{u}____--{t}'.format(u=mins_units, t=mins_tens)

    # bit 43 flag / user bits field 6
    LTC += '0' + '0000'
    HLP += '_' + '____'

    #hrs units / user bits field 7 / hrs tens
    LTC += ble(hrs_units,4) + '0000' + ble(hrs_tens,2)
    HLP += '---{u}____--{t}'.format(u=hrs_units, t=hrs_tens)

    # bit 58 clock flag / bit 59 flag / user bits field 8
    LTC += '0' + '0' + '0000'
    HLP += '_' + '_' + '____'

    # sync word
    LTC += '0011111111111101'
    HLP += '################'
    if as_string:
        return LTC
    else:
        return bitstring_to_bytes(LTC, bytecount=10)


##
## MTC functions
##
def mtc_encode(timecode, as_string=False):
    # MIDI bytes are little-endian
    # Byte 0
    #   0rrhhhhh: Rate (0–3) and hour (0–23).
    #   rr = 000: 24 frames/s
    #   rr = 001: 25 frames/s
    #   rr = 010: 29.97 frames/s (SMPTE drop-frame timecode)
    #   rr = 011: 30 frames/s
    # Byte 1
    #   00mmmmmm: Minute (0–59)
    # Byte 2
    #   00ssssss: Second (0–59)
    # Byte 3
    #   000fffff: Frame (0–29, or less at lower frame rates)
    hrs, mins, secs, frs = timecode.frames_to_tc(timecode.frames)
    framerate = timecode.framerate
    rateflags = {
        '24':    0,
        '25':    1,
        '29.97': 2,
        '30':    3
    }
    rateflag = rateflags[framerate] * 32  # multiply by 32, because the rate flag starts at bit 6

    # print('{:8} {:8} {:8} {:8}'.format(hrs, mins, secs, frs))
    if as_string:
        b0 = bbe(rateflag + hrs, 8)
        b1 = bbe(mins)
        b2 = bbe(secs)
        b3 = bbe(frs)
        # print('{:8} {:8} {:8} {:8}'.format(b0, b1, b2, b3))
        return b0+b1+b2+b3
    else:
        b = bytearray([rateflag + hrs, mins, secs, frs])
        # debug_string = '    0x{:02}     0x{:02}     0x{:02}     0x{:02}'
        # debug_array  = [ord(b[0]), ord(b[1]), ord(b[2]), ord(b[3])]
        # print(debug_string.format(debug_array))
        return b

# convert a bytearray back to timecode
def mtc_decode(mtc_bytes):
    rhh, mins, secs, frs = mtc_bytes
    rateflag = rhh >> 5
    hrs      = rhh & 31
    fps = ['24','25','29.97','30'][rateflag]
    total_frames = int(frs + float(fps) * (secs + mins * 60 + hrs * 60 * 60))
    return Timecode(fps, frames=total_frames)

def mtc_full_frame(timecode):
    # if sending this to a MIDI device, remember that MIDI is generally little endian
    # but the full frame timecode bytes are big endian
    mtc_bytes = mtc_encode(timecode)
    # mtc full frame has a special header and ignores the rate flag
    return bytearray([0xf0, 0x7f, 0x7f, 0x01, 0x01]) + mtc_bytes + bytearray([0xf7])

def mtc_decode_full_frame(full_frame_bytes):
    mtc_bytes = full_frame_bytes[5:-1]
    return mtc_decode(mtc_bytes)

def mtc_quarter_frame(timecode, piece=0):
    # there are 8 different mtc_quarter frame pieces
    # see https://en.wikipedia.org/wiki/MIDI_timecode
    # and https://web.archive.org/web/20120212181214/http://home.roadrunner.com/~jgglatt/tech/mtc.htm
    # these are little-endian bytes
    # piece 0 : 0xF1 0000 ffff frame
    mtc_bytes = mtc_encode(timecode)
    this_byte = mtc_bytes[3 - piece//2]   #the order of pieces is the reverse of the mtc_encode
    if piece % 2 == 0:
        # even pieces get the low nibble
        nibble = this_byte & 15
    else:
        # odd pieces get the high nibble
        nibble = this_byte >> 4
    return bytearray([0xf1, piece * 16 + nibble])

def mtc_decode_quarter_frames(frame_pieces):
    mtc_bytes = bytearray(4)
    if len(frame_pieces) < 8:
        return None
    for piece in range(8):
        mtc_index = 3 - piece//2    # quarter frame pieces are in reverse order of mtc_encode
        this_frame = frame_pieces[piece]
        if this_frame is bytearray or this_frame is list:
            this_frame = this_frame[1]
        data = this_frame & 15      # ignore the frame_piece marker bits
        if piece % 2 == 0:
            # 'even' pieces came from the low nibble
            # and the first piece is 0, so it's even
            mtc_bytes[mtc_index] += data
        else:
            # 'odd' pieces came from the high nibble
            mtc_bytes[mtc_index] += data * 16
    return mtc_decode(mtc_bytes)
